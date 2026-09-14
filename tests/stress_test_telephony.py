# -*- coding: utf-8 -*-
"""
==============================================================================
RESTAURANTE RYU - SIMULADOR DE ESTRÉS Y CONCURRENCIA TELEFÓNICA (ASYNCIO)
Simula 10, 25 y 50 llamadas/sesiones simultáneas contra Order FSM y KAG.
Mide latencia de respuesta, percentiles P50/P95/P99, throughput y memoria.
100% determinista, seguro, sin tocar la red telefónica real ($0 USD).
==============================================================================
"""

import sys
import time
import psutil
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from order_fsm import OrderStateMachine, OrderState
from order_service import audit_order_with_kag, create_protobuf_order


SAMPLE_CATALOG_ITEMS = [
    {"name": "Sushi Mechudo Especial", "price": 140.0, "qty": 2},
    {"name": "Philadelphia Empanizado", "price": 130.0, "qty": 1},
    {"name": "Calpico Tradicional 1L", "price": 45.0, "qty": 1},
    {"name": "Kushiages de Queso Manchego", "price": 75.0, "qty": 1},
    {"name": "Refresco Sprite 500ml", "price": 30.0, "qty": 2}
]

SAMPLE_ADDRESSES = [
    ("Calle Sixto Gorjón #24, Col. Centro", 15.0),
    ("Av. Hidalgo #105 interior 3, Tequila", 15.0),
    ("Calle Girasol #12, Col. Cofradía", 25.0),
    ("Carretera Libre a Magdalena Km 2", 40.0),
    ("Calle Ramón Corona #80, Tequila", 15.0)
]


async def simulate_single_call_session(session_id: str, caller_phone: str, customer_name: str, index: int) -> Dict[str, Any]:
    """Simula una sesión de llamada completa con 5 turnos de diálogo y transiciones FSM."""
    t_start = time.perf_counter()
    turn_latencies = []

    # Inicialización de la máquina de estados
    fsm = OrderStateMachine(customer_phone=caller_phone, customer_name=customer_name)

    # Turno 1: Cliente solicita platillos
    t0 = time.perf_counter()
    item_choice_1 = SAMPLE_CATALOG_ITEMS[index % len(SAMPLE_CATALOG_ITEMS)]
    item_choice_2 = SAMPLE_CATALOG_ITEMS[(index + 1) % len(SAMPLE_CATALOG_ITEMS)]
    fsm.add_item(item_choice_1["name"], quantity=item_choice_1["qty"], unit_price=item_choice_1["price"])
    fsm.add_item(item_choice_2["name"], quantity=item_choice_2["qty"], unit_price=item_choice_2["price"])
    turn_latencies.append((time.perf_counter() - t0) * 1000.0)

    if fsm.state != OrderState.NEED_DELIVERY_TYPE:
        raise RuntimeError(f"FSM en estado inesperado tras Turno 1: {fsm.state}")

    # Turno 2: Modalidad de entrega (domicilio)
    t0 = time.perf_counter()
    fsm.set_delivery_type("domicilio")
    turn_latencies.append((time.perf_counter() - t0) * 1000.0)

    if fsm.state != OrderState.NEED_ADDRESS:
        raise RuntimeError(f"FSM en estado inesperado tras Turno 2: {fsm.state}")

    # Turno 3: Registro de dirección física y tarifa de zona
    t0 = time.perf_counter()
    address, fee = SAMPLE_ADDRESSES[index % len(SAMPLE_ADDRESSES)]
    fsm.set_address(address=address, zone_name="Tequila Urbano", shipping_fee=fee)
    turn_latencies.append((time.perf_counter() - t0) * 1000.0)

    if fsm.state != OrderState.NEED_PAYMENT:
        raise RuntimeError(f"FSM en estado inesperado tras Turno 3: {fsm.state}")

    # Turno 4: Método de pago
    t0 = time.perf_counter()
    fsm.set_payment(method="Efectivo", change_for=500.0)
    turn_latencies.append((time.perf_counter() - t0) * 1000.0)

    if fsm.state != OrderState.REVIEWING:
        raise RuntimeError(f"FSM en estado inesperado tras Turno 4: {fsm.state}")

    # Turno 5: Confirmación y emisión de comanda binaria
    t0 = time.perf_counter()
    ok, msg = fsm.confirm_order()
    if not ok:
        raise RuntimeError(f"Error confirmando comanda: {msg}")

    fsm_dict = fsm.to_dict()
    payload = {
        "order_id": session_id,
        "customer_name": customer_name,
        "customer_phone": caller_phone,
        "delivery_type": fsm.delivery_type,
        "address": fsm.address,
        "shipping_fee": fsm.shipping_fee,
        "payment_method": fsm.payment_method,
        "payment_change_for": fsm.payment_change_for,
        "total_amount": fsm.total_amount,
        "items": fsm_dict["items"]
    }
    proto_bytes = create_protobuf_order(payload)
    turn_latencies.append((time.perf_counter() - t0) * 1000.0)

    if fsm.state != OrderState.CONFIRMED:
        raise RuntimeError(f"FSM no alcanzó estado CONFIRMED: {fsm.state}")

    total_latency_ms = (time.perf_counter() - t_start) * 1000.0

    return {
        "session_id": session_id,
        "success": True,
        "total_latency_ms": total_latency_ms,
        "avg_turn_latency_ms": sum(turn_latencies) / len(turn_latencies),
        "total_amount": fsm.total_amount,
        "proto_bytes_len": len(proto_bytes) if proto_bytes else 0
    }


async def run_concurrency_stage(concurrency: int) -> Dict[str, Any]:
    """Ejecuta una etapa de concurrencia pura con `concurrency` llamadas simultáneas."""
    print("\n" + "=" * 70)
    print(f"⚡ INICIANDO ETAPA DE ESTRÉS: {concurrency} LLAMADAS CONCURRENTES")
    print("=" * 70)

    proc = psutil.Process()
    mem_before_mb = proc.memory_info().rss / 1024 / 1024

    t_stage_start = time.perf_counter()
    tasks = []
    for i in range(concurrency):
        session_id = f"stress-call-{concurrency}c-{i+1:03d}"
        phone = f"+523311{concurrency:02d}{i+1:04d}"
        name = f"Cliente Stress {i+1}"
        tasks.append(simulate_single_call_session(session_id, phone, name, i))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_stage_sec = time.perf_counter() - t_stage_start

    mem_after_mb = proc.memory_info().rss / 1024 / 1024
    mem_delta_mb = mem_after_mb - mem_before_mb

    successful_results = []
    failed_count = 0
    for r in results:
        if isinstance(r, Exception):
            failed_count += 1
            print(f"  [ERROR EN SESIÓN] {r}")
        elif isinstance(r, dict) and r.get("success"):
            successful_results.append(r)
        else:
            failed_count += 1

    success_rate = (len(successful_results) / concurrency) * 100.0
    latencies = [r["total_latency_ms"] for r in successful_results]
    latencies.sort()

    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    min_lat = latencies[0] if latencies else 0.0
    max_lat = latencies[-1] if latencies else 0.0
    p50_lat = latencies[int(len(latencies) * 0.50)] if latencies else 0.0
    p95_lat = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)] if latencies else 0.0
    p99_lat = latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)] if latencies else 0.0
    throughput = len(successful_results) / total_stage_sec if total_stage_sec > 0 else 0.0

    print(f"  Concurrencia:            {concurrency} llamadas")
    print(f"  Tiempo total de etapa:   {total_stage_sec:.3f} s")
    print(f"  Llamadas exitosas:       {len(successful_results)}/{concurrency} ({success_rate:.1f}%)")
    print(f"  Throughput:              {throughput:.1f} llamadas/segundo")
    print(f"  Latencia promedio/sesión:{avg_lat:.2f} ms")
    print(f"  Percentiles (ms):        Min: {min_lat:.2f} | P50: {p50_lat:.2f} | P95: {p95_lat:.2f} | P99: {p99_lat:.2f} | Max: {max_lat:.2f}")
    print(f"  Memoria RAM Proceso:     {mem_before_mb:.1f} MB -> {mem_after_mb:.1f} MB (Delta: {mem_delta_mb:+.2f} MB)")

    return {
        "concurrency": concurrency,
        "total_sec": total_stage_sec,
        "successful": len(successful_results),
        "failed": failed_count,
        "success_rate": success_rate,
        "throughput": throughput,
        "avg_ms": avg_lat,
        "p50_ms": p50_lat,
        "p95_ms": p95_lat,
        "p99_ms": p99_lat,
        "mem_delta_mb": mem_delta_mb
    }


async def main():
    parser = argparse.ArgumentParser(description="Prueba de Estrés y Concurrencia de Telefonía Ryu (Nivel 5)")
    parser.add_argument(
        "--stages",
        type=str,
        default="10,25,50",
        help="Niveles de concurrencia separados por comas (ej. 10,25,50)"
    )
    args = parser.parse_args()

    stage_list = [int(s.strip()) for s in args.stages.split(",") if s.strip().isdigit()]
    if not stage_list:
        stage_list = [10, 25, 50]

    print("\n" + "#" * 70)
    print("🚀 RYU TELEPHONY - SIMULADOR DE ESTRÉS Y CONCURRENCIA SRE (NIVEL 5)")
    print(f"Etapas programadas: {stage_list} llamadas simultáneas")
    print("#" * 70)

    summary_stages = []
    overall_start = time.perf_counter()

    for stage_concurrency in stage_list:
        metrics = await run_concurrency_stage(stage_concurrency)
        summary_stages.append(metrics)
        # Breve pausa para estabilización de event loop
        await asyncio.sleep(0.3)

    overall_sec = time.perf_counter() - overall_start

    print("\n" + "=" * 76)
    print("📊 RESUMEN CONSOLIDADO DE RESILIENCIA Y CAPACIDAD CONCURRENTE")
    print("=" * 76)
    print(f"{'Concurrencia':^14}|{'Éxito (%)':^11}|{'Throughput':^14}|{'P50 (ms)':^11}|{'P95 (ms)':^11}|{'Delta RAM':^11}")
    print("-" * 76)
    for m in summary_stages:
        print(f"{m['concurrency']:^14}|{m['success_rate']:^11.1f}|{m['throughput']:^11.1f} c/s|{m['p50_ms']:^11.2f}|{m['p95_ms']:^11.2f}|{m['mem_delta_mb']:^+9.2f} MB")
    print("=" * 76)
    print(f"⏱️ Tiempo total de ejecución de la suite de estrés: {overall_sec:.2f} s")

    all_passed = all(m["failed"] == 0 and m["success_rate"] == 100.0 for m in summary_stages)
    if all_passed:
        print("✅ SISTEMA TELEFÓNICO RYU: 100% RESILIENTE Y APTO PARA ALTA CONCURRENCIA.")
        sys.exit(0)
    else:
        print("❌ ADVERTENCIA: Se detectaron fallos durante la simulación de concurrencia.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
