#!/usr/bin/env python3
"""
tests/run_smoke_tests.py
Suite de Smoke Tests (Pruebas de Humo) de ultra-alta velocidad para Ryu AI Telephony.
Ejecuta validaciones locales sin consumir saldo de telefonía ni tocar APIs externas:
1. Validación sintáctica estricta de todos los archivos Python del proyecto (py_compile).
2. Simulación determinista completa de la máquina de estados finitos de pedidos (order_fsm.py).
3. Verificación de integridad de contratos y especificaciones arquitectónicas (test_specs.py).
"""

import sys
import os
import py_compile
from pathlib import Path

# Soporte UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_syntax_check() -> bool:
    """Valida la sintaxis de todos los archivos .py del proyecto."""
    print("=" * 70)
    print("1. VALIDACION SINTACTICA DE CODIGO PYTHON (PY_COMPILE)")
    print("=" * 70)
    
    ignored_dirs = {
        ".git", ".github", "__pycache__", "venv", ".venv", "env",
        "node_modules", "scratch", ".system_generated", "build", "dist"
    }

    py_files = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in ignored_dirs for part in path.parts):
            continue
        py_files.append(path)

    py_files.sort()
    print(f"Total de archivos Python detectados para compilacion: {len(py_files)}")
    
    errors = []
    for py_file in py_files:
        rel_path = py_file.relative_to(PROJECT_ROOT)
        try:
            py_compile.compile(str(py_file), doraise=True)
            print(f"  [SINTAXIS OK] {rel_path}")
        except py_compile.PyCompileError as e:
            print(f"  [ERROR DE SINTAXIS] {rel_path}: {e}")
            errors.append((rel_path, str(e)))

    if errors:
        print(f"Se encontraron {len(errors)} archivos con errores de sintaxis:")
        for path, err in errors:
            print(f"   - {path}: {err}")
        return False

    print(f"Todos los {len(py_files)} archivos Python compilan correctamente sin errores sintacticos.\n")
    return True


def run_order_fsm_smoke_test() -> bool:
    """Verifica el flujo determinista de la máquina de estados de pedidos (Order FSM)."""
    print("=" * 70)
    print("2. SMOKE TEST DETERMINISTA DE MAQUINA DE ESTADOS (ORDER FSM)")
    print("=" * 70)

    try:
        from order_fsm import OrderStateMachine, OrderState
    except ImportError as e:
        print(f"Error importando order_fsm: {e}")
        return False

    fsm = OrderStateMachine(customer_phone="+523385261250", customer_name="Carlos Santana (Smoke Test)")

    # Paso 1: Estado Inicial
    print("Paso 1: Verificando estado inicial...")
    if fsm.state != OrderState.IDLE:
        print(f"Estado inicial incorrecto: esperado IDLE, recibido {fsm.state}")
        return False
    print(f"  Estado inicial confirmado: {fsm.state.value}")

    # Paso 2: Agregar platillos al carrito
    print("Paso 2: Agregando platillos al pedido...")
    item1 = fsm.add_item("California Especial", quantity=2, unit_price=120.0, notes="sin cebollin", station="Barra Sushi")
    item2 = fsm.add_item("Refresco Sprite", quantity=1, unit_price=35.0, notes="bien frio", station="Bebidas")
    
    if fsm.state != OrderState.NEED_DELIVERY_TYPE:
        print(f"Estado tras agregar productos incorrecto: esperado NEED_DELIVERY_TYPE, recibido {fsm.state}")
        return False
    if fsm.items_subtotal != 275.0:
        print(f"Subtotal incorrecto: esperado 275.0, recibido {fsm.items_subtotal}")
        return False
    print(f"  Platillos agregados. Subtotal calculado: ${fsm.items_subtotal:.2f} MXN")
    print(f"  Estado actual: {fsm.state.value}")

    # Paso 3: Especificar modalidad de entrega (Domicilio)
    print("Paso 3: Seleccionando modalidad de entrega a domicilio...")
    fsm.set_delivery_type("servicio a domicilio")
    if fsm.state != OrderState.NEED_ADDRESS:
        print(f"Estado tras definir domicilio incorrecto: esperado NEED_ADDRESS, recibido {fsm.state}")
        return False
    print(f"  Modalidad domicilio configurada. Estado actual: {fsm.state.value}")

    # Paso 4: Capturar dirección de entrega y zona
    print("Paso 4: Registrando direccion fisica y tarifa de reparto...")
    fsm.set_address("Calle Sixto Gorjon #24, Col. Centro", zone_name="Tequila Centro", shipping_fee=15.0)
    if fsm.state != OrderState.NEED_PAYMENT:
        print(f"Estado tras capturar direccion incorrecto: esperado NEED_PAYMENT, recibido {fsm.state}")
        return False
    print(f"  Direccion registrada: '{fsm.address}' (Tarifa envio: ${fsm.shipping_fee:.2f} MXN)")
    print(f"  Estado actual: {fsm.state.value}")

    # Paso 5: Definir método de pago y cambio
    print("Paso 5: Pactando metodo de pago (Efectivo con billete de $500)...")
    fsm.set_payment("Efectivo", change_for=500.0)
    if fsm.state != OrderState.REVIEWING:
        print(f"Estado tras definir pago incorrecto: esperado REVIEWING, recibido {fsm.state}")
        return False
    if not fsm.can_confirm:
        print(f"can_confirm deberia ser True, pero faltan: {fsm.missing_fields}")
        return False
    if fsm.total_amount != 290.0:
        print(f"Total calculado incorrecto: esperado 290.0, recibido {fsm.total_amount}")
        return False
    print(f"  Pago pactado. Total global: ${fsm.total_amount:.2f} MXN")
    print(f"  Estado actual: {fsm.state.value}")

    # Paso 6: Resumen determinista para confirmación verbal
    summary = fsm.generate_review_summary()
    print(f"  Resumen generado para la voz del bot:\n     {summary}")
    if "290" not in summary or "Sixto Gorjon" not in summary:
        print("El resumen verbal omitio datos clave de la orden")
        return False

    # Paso 7: Confirmación explícita del cliente
    print("Paso 6: Confirmando orden tras visto bueno del cliente...")
    success, msg = fsm.confirm_order()
    if not success or fsm.state != OrderState.CONFIRMED:
        print(f"Fallo confirmacion de orden: {msg}")
        return False
    print(f"  Comanda confirmada satisfactoriamente. Estado final: {fsm.state.value}")

    # Paso 8: Validación de exportación a diccionario para Telegram / POS
    order_dict = fsm.to_dict()
    if order_dict["state"] != "CONFIRMED" or len(order_dict["items"]) != 2:
        print("to_dict() genero un payload invalido")
        return False
    print(f"  Payload estructurado verificado: {order_dict['total_amount']} MXN, {len(order_dict['items'])} items.")
    print("Smoke Test de Order FSM completado con 100% de exito.\n")
    return True


def run_specs_smoke_test() -> bool:
    """Verifica que los ADRs y especificaciones Open Spec mantengan integridad absoluta."""
    print("=" * 70)
    print("3. VERIFICACION DE ESPECIFICACIONES (ADR & OPEN SPEC)")
    print("=" * 70)
    import unittest
    suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"), pattern="test_specs.py")
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if not result.wasSuccessful():
        print("Fallaron las pruebas de especificaciones Open Spec / ADR.")
        return False
    print("Todas las especificaciones y contratos arquitectonicos estan integros.\n")
    return True


def main():
    print("#" * 70)
    print("EJECUTANDO RYU SMOKE TESTS (VERIFICACION RAPIDA)")
    print("#" * 70 + "\n")

    step1_ok = run_syntax_check()
    step2_ok = run_order_fsm_smoke_test()
    step3_ok = run_specs_smoke_test()

    print("=" * 70)
    if step1_ok and step2_ok and step3_ok:
        print("TODOS LOS SMOKE TESTS PASARON EXITOSAMENTE (SISTEMA SALUDABLE)")
        print("=" * 70 + "\n")
        return 0
    else:
        print("AL MENOS UNA PRUEBA DE HUMO FALLO. REVISA LOS LOGS SUPERIORES.")
        print("=" * 70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
