# -*- coding: utf-8 -*-
"""
======================================================================
TEST SUITE: PUENTE SOFT RESTAURANT & COMANDAS DE ALTA PRIORIDAD IA
Pruebas de formateo de tickets, inyección SQL Server, cola offline y despacho
======================================================================
"""

import os
import sys
import json
import sqlite3
import unittest
from datetime import datetime

# Asegurar encoding UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from soft_restaurant_bridge import (
    generate_ai_priority_ticket,
    generate_station_ticket,
    dispatch_order,
    get_config,
    SoftRestaurantSQLBridge
)


class TestSoftRestaurantBridge(unittest.TestCase):

    def setUp(self):
        self.sample_order = {
            "order_id": "RYU-TEST-999",
            "session_id": "test-session-abc",
            "customer_phone": "3385261250",
            "customer_name": "Don Roberto Gómez",
            "delivery_type": "domicilio",
            "address": "Av. Hidalgo #45, Centro",
            "references": "Portón negro junto a la farmacia",
            "payment_method": "Efectivo",
            "payment_change_for": 500.0,
            "items_subtotal": 290.0,
            "shipping_fee": 15.0,
            "total_amount": 305.0,
            "is_future_order": False,
            "scheduled_time": "",
            "items": [
                {
                    "name": "Sushi Tocayo Roll",
                    "quantity": 2,
                    "unit_price": 115.0,
                    "station": "sushi_bar",
                    "notes": "Sin ajonjolí por favor"
                },
                {
                    "name": "Lasagna Tradicional",
                    "quantity": 1,
                    "unit_price": 60.0,
                    "station": "italian_kitchen",
                    "notes": "Bien caliente"
                }
            ]
        }

    def test_01_generate_ai_priority_ticket_contains_required_banners(self):
        """Verifica que la comanda especial de prioridad contenga los banners y alertas obligatorias."""
        ticket = generate_ai_priority_ticket(self.sample_order)

        self.assertIn("¡¡ATENCIÓN COCINA - ALTA PRIORIDAD!!", ticket)
        self.assertIn("PEDIDO DE INTELIGENCIA ARTIFICIAL", ticket)
        self.assertIn("DAR PRIORIDAD MÁXIMA EN COCINA", ticket)
        self.assertIn("TIEMPO PROMETIDO: 40 a 50 minutos", ticket)
        self.assertIn("Don Roberto Gómez", ticket)
        self.assertIn("3385261250", ticket)
        self.assertIn("Av. Hidalgo #45, Centro", ticket)
        self.assertIn("Sushi Tocayo Roll", ticket)
        self.assertIn("Lasagna Tradicional", ticket)
        self.assertIn("TOTAL COBRAR: $305.00 MXN", ticket)
        self.assertIn("PAGA CON:     $500.00 (Cambio: $195.00)", ticket)
        self.assertIn("TICKET VALIDADO Y AUDITADO POR IA", ticket)
        print("\n✅ Test 01 Exitoso: Comanda de Prioridad IA incluye todos los elementos requeridos.")

    def test_02_generate_station_tickets(self):
        """Verifica que las comandas por estación filtren únicamente los platillos de dicha cocina."""
        sushi_items = [self.sample_order["items"][0]]
        ticket_sushi = generate_station_ticket("Barra Sushi", self.sample_order, sushi_items)

        self.assertIn("BARRA SUSHI", ticket_sushi.upper())
        self.assertIn("RYU-TEST-999", ticket_sushi)
        self.assertIn("2x    Sushi Tocayo Roll", ticket_sushi)
        self.assertIn("Sin ajonjolí por favor", ticket_sushi)
        self.assertNotIn("Lasagna Tradicional", ticket_sushi)

        italian_items = [self.sample_order["items"][1]]
        ticket_italian = generate_station_ticket("Cocina Italiana", self.sample_order, italian_items)
        self.assertIn("COCINA ITALIANA", ticket_italian.upper())
        self.assertIn("1x    Lasagna Tradicional", ticket_italian)
        self.assertNotIn("Sushi Tocayo Roll", ticket_italian)
        print("✅ Test 02 Exitoso: Comandas por estación filtradas correctamente.")

    def test_03_offline_queue_resilience(self):
        """Verifica que si SQL Server está offline, el pedido se encola en SQLite sin fallar."""
        bridge = SoftRestaurantSQLBridge()
        success, msg = bridge.inject_order_and_deduct_inventory(self.sample_order)

        # En entorno sin SQL Server activo, success es False y encola en SQLite
        db_path = os.path.join(os.path.dirname(__file__), "db", "soft_restaurant_offline_queue.db")
        self.assertTrue(os.path.exists(db_path))

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT folio_ryu, payload_json, status FROM pending_orders WHERE folio_ryu = ?", (self.sample_order["order_id"],))
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "RYU-TEST-999")
        self.assertIn(row[2], ["QUEUED_OFFLINE", "PROCESSED"])

        payload = json.loads(row[1])
        self.assertEqual(payload["customer_name"], "Don Roberto Gómez")
        print("✅ Test 03 Exitoso: Resiliencia de cola offline SQLite verificada.")

    def test_04_dispatch_order_simulation_mode(self):
        """Verifica el despacho completo en modo simulación (sin intentar sockets TCP físicos)."""
        # Temporalmente activar modo file_simulation
        bridge_cfg = get_config()
        orig_mode = bridge_cfg.get("mode")
        bridge_cfg["mode"] = "file_simulation"
        
        # Guardar temporalmente o mockear get_config en soft_restaurant_bridge
        import soft_restaurant_bridge
        original_get_config = soft_restaurant_bridge.get_config
        soft_restaurant_bridge.get_config = lambda: {
            **bridge_cfg,
            "mode": "file_simulation",
            "priority_alert_settings": {
                "enabled": True,
                "promised_delivery_time": "40 a 50 minutos",
                "print_to_all_stations": True,
                "expediter_printer_key": "expediter"
            }
        }

        try:
            results = dispatch_order(self.sample_order)
            self.assertEqual(results["order_id"], "RYU-TEST-999")
            self.assertIn("sushi_bar", results["stations_printed"])
            self.assertIn("italian_kitchen", results["stations_printed"])
            self.assertEqual(results["stations_printed"]["sushi_bar"]["status"], "simulated")
            self.assertEqual(results["stations_printed"]["italian_kitchen"]["status"], "simulated")
            self.assertIsInstance(results["priority_ticket_printed"], list)
            self.assertTrue(len(results["priority_ticket_printed"]) >= 1)
            print("✅ Test 04 Exitoso: Despacho completo en modo simulación validado.")
        finally:
            soft_restaurant_bridge.get_config = original_get_config

    def test_05_sql_script_syntax_and_structure(self):
        """Verifica que el archivo T-SQL contenga las tablas, SPs y lógica de descuento de inventario."""
        sql_path = os.path.join(os.path.dirname(__file__), "db", "soft_restaurant_integration.sql")
        self.assertTrue(os.path.exists(sql_path))

        with open(sql_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        self.assertIn("CREATE TABLE ryu_pedidos_ia", sql_content)
        self.assertIn("CREATE TABLE ryu_pedidos_ia_detalle", sql_content)
        self.assertIn("sp_Ryu_RegistrarPedidoIA", sql_content)
        self.assertIn("sp_Ryu_DescontarInventarioItem", sql_content)
        self.assertIn("inventario_descontado", sql_content)
        self.assertIn("existencias", sql_content)
        self.assertIn("kardex", sql_content)
        print("✅ Test 05 Exitoso: Script T-SQL de Soft Restaurant validado estructuralmente.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
