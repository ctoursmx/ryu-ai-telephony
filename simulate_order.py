import json
import os
import sys
from datetime import datetime

# Asegurar encoding UTF-8 en consolas Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
from order_service import get_active_menus, format_telegram_ticket

def run_simulation():
    print("=========================================================")
    print("      SIMULADOR DE SISTEMA DE PEDIDOS - RYU TEQUILA      ")
    print("=========================================================\n")
    
    # 1. Test de Horarios Simulados
    test_cases = [
        ("Lunes 2:00 PM (14:00)", datetime(2026, 9, 7, 14, 0)),
        ("Viernes 3:00 PM (15:00)", datetime(2026, 9, 11, 15, 0)),
        ("Sábado 8:30 PM (20:30)", datetime(2026, 9, 12, 20, 30)),
        ("Miércoles 10:00 PM (22:00)", datetime(2026, 9, 9, 22, 0)),
        ("Domingo 10:00 AM (Cerrado)", datetime(2026, 9, 13, 10, 0))
    ]
    
    print("--- 1. EVALUACIÓN DE DISPONIBILIDAD DE MENÚS POR HORARIO ---")
    for label, dt in test_cases:
        res = get_active_menus(dt)
        menus = []
        if res['available_menus']['japanese']: menus.append("Japonés (1pm-11pm)")
        if res['available_menus']['italian']: menus.append("Italiano (Vie-Dom 1pm-7pm)")
        if res['available_menus']['snacks']: menus.append("Snacks (7pm-11pm)")
        status_str = ", ".join(menus) if menus else "CERRADO"
        print(f" • {label:30} -> {status_str}")
        
    print("\n--- 2. AUDITORÍA FACTUAL KAG (ANTI-ALUCINACIÓN) ---")

    mock_order = {
        "order_id": "RYU-204",
        "customer_name": "Ana Martínez",
        "customer_phone": "3741141405",
        "delivery_type": "domicilio",
        "address": "Calle Hidalgo #12, Col. Cofradía, Tequila",
        "references": "Casa de 2 pisos con cancel negro",
        "payment_method": "Efectivo",
        "payment_change_for": 500,
        "items": [
            { "name": "Lasagna Tradicional", "price": 180, "quantity": 1 }, # Precio inflado/alucinado para probar KAG
            { "name": "Sushi Cheese Explosion", "price": 135, "quantity": 1 },
            { "name": "Refresco (500ml)", "price": 35, "quantity": 1 }
        ]
    }
    from order_service import audit_order_with_kag, create_protobuf_order
    mock_order = audit_order_with_kag(mock_order)

    print("\n--- 3. EJEMPLO DE COMANDA GENERADA PARA TELEGRAM ---")
    ticket = format_telegram_ticket(mock_order)
    print(ticket)

    print("\n--- 4. SERIALIZACIÓN PROTOCOL BUFFERS (COMPACTACIÓN BINARIA) ---")
    proto_bytes = create_protobuf_order(mock_order)
    if proto_bytes:
        print(f" • Payload Protobuf generado: {len(proto_bytes)} bytes.")
        from proto_service import ProtoService
        rec = ProtoService.deserialize_order_from_bytes(proto_bytes)
        print(f" • Deserialización verificada: Orden #{rec.get('order_id')} de {rec.get('customer_name')} por ${rec.get('total_amount')} MXN.")
    print("\n=========================================================")

if __name__ == '__main__':
    run_simulation()

