"""
======================================================================
RESTAURANTE RYU - SUITE DE PRUEBAS AUTOMATIZADAS
Validación de Protobuf, Base de Datos AGE/Local, KAG Anti-Alucinación y Autoaprendizaje
======================================================================
"""

import os
import sys
import unittest
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


from proto_service import ProtoService
import proto.ryu_order_pb2 as order_pb
import proto.ryu_kag_pb2 as kag_pb
from kag_engine import kag_engine
from db.graph_db import db_manager

class TestRyuArchitecture(unittest.TestCase):

    def test_01_protobuf_serialization(self):
        """Valida que una orden se serialice a binario Protobuf y se recupere intacta."""
        raw_order = {
            "order_id": "RYU-TEST-999",
            "session_id": "sess_unit_test",
            "customer_phone": "+523385261250",
            "customer_name": "Josué Cabrales",
            "delivery_type": "domicilio",
            "address": "Calle Girasol #3, Interior 5, Colonia Cofradía",
            "zone_name": "Tequila Urbano",
            "shipping_fee": 15.0,
            "payment_method": "efectivo",
            "payment_change_for": 500.0,
            "items": [
                {
                    "item_id": "jp_sush_01",
                    "name": "Sushi Empanizado",
                    "unit_price": 95.0,
                    "quantity": 2,
                    "notes": "sin ajonjolí"
                },
                {
                    "item_id": "snk_combo_01",
                    "name": "Pa Que Compartas",
                    "unit_price": 210.0,
                    "quantity": 1,
                    "notes": "alitas bbq y boneless mango habanero",
                    "is_combo_included": False
                }
            ],
            "items_subtotal": 400.0,
            "total_amount": 415.0
        }

        # Serialización binaria
        proto_bytes = ProtoService.serialize_order_to_bytes(raw_order)
        self.assertIsInstance(proto_bytes, bytes)
        self.assertGreater(len(proto_bytes), 50)

        # Deserialización y verificación de campos
        deserialized = ProtoService.deserialize_order_from_bytes(proto_bytes)
        self.assertEqual(deserialized["order_id"], "RYU-TEST-999")
        self.assertEqual(deserialized["customer_name"], "Josué Cabrales")
        self.assertEqual(float(deserialized["total_amount"]), 415.0)
        self.assertEqual(len(deserialized["items"]), 2)
        self.assertEqual(deserialized["payment"]["method"], "EFECTIVO")
        self.assertEqual(float(deserialized["payment"]["change_due"]), 85.0) # 500 - 415 = 85
        print("✅ Test 01 - Protobuf Serialization: PASSED (Tamaño binario:", len(proto_bytes), "bytes)")

    def test_02_kag_phonetic_normalization(self):
        """Verifica que el motor KAG normalice errores fonéticos de llamadas telefónicas."""
        user_speech = "hola buenas tardes me da un sucho y una soñada por favor a costradía"
        normalized, replacements = kag_engine.normalize_user_text(user_speech)
        
        self.assertIn("Sushi", normalized)
        self.assertIn("Lasaña", normalized)
        self.assertIn("Colonia Cofradía", normalized)
        print("✅ Test 02 - KAG Normalization: PASSED (Normalizado:", normalized, ")")

    def test_03_kag_ground_truth_retrieval(self):
        """Valida que se extraigan los hechos inmutables de precios y tarifas desde el grafo."""
        normalized_text = "quiero un Sushi Empanizado y enviar a Aguacatillo"
        facts = kag_engine.retrieve_ground_truth_facts(normalized_text)

        matched_names = [d["name"] for d in facts["matched_dishes"]]
        self.assertIn("Sushi Empanizado", matched_names)
        self.assertEqual(facts["shipping_fee"], 30.0) # Tarifa de Aguacatillo
        self.assertEqual(facts["matched_zone"]["name"], "Aguacatillo")

        # Generación de prompt KAG
        prompt_block = kag_engine.generate_kag_context_prompt(facts)
        self.assertIn("[HECHOS VERIFICADOS POR EL GRAFO DE CONOCIMIENTO", prompt_block)
        self.assertIn("Sushi Empanizado: $95 MXN", prompt_block)
        self.assertIn("Aguacatillo ($30 MXN tarifa especial foránea)", prompt_block)
        print("✅ Test 03 - KAG Ground Truth Retrieval: PASSED")

    def test_04_kag_anti_hallucination_guardrail(self):
        """Valida que el guardián de KAG detecte y corrija precios alucinados por el LLM."""
        facts = {
            "matched_dishes": [
                {"name": "Sushi Empanizado", "price": 95.0},
                {"name": "Lasagna Tradicional", "price": 150.0}
            ],
            "shipping_fee": 15.0
        }

        # Simulación de respuesta con alucinación de precios ($140 y $210 en lugar de $95 y $150)
        hallucinated_response = "Con gusto, tu Sushi Empanizado son $140 pesos y tu Lasagna Tradicional son $210 pesos."
        corrected_response, v_result = kag_engine.audit_and_correct_response(hallucinated_response, facts)

        self.assertTrue(v_result.price_corrected)
        self.assertIn("$95", corrected_response)
        self.assertIn("$150", corrected_response)
        self.assertNotIn("$140", corrected_response)
        self.assertNotIn("$210", corrected_response)
        print("✅ Test 04 - KAG Anti-Hallucination Guardrail: PASSED")
        print("   Texto con Alucinación:", hallucinated_response)
        print("   Texto Corregido por KAG:", corrected_response)

    def test_05_kag_autoaprendizaje_continuous_learning(self):
        """Prueba que el motor KAG aprenda una nueva corrección o alias en caliente."""
        session_id = "sess_learn_test"
        phone = "+523385261250"
        
        # El cliente dice algo con una palabra regional o apodo nuevo
        user_utterance = "no, quise decir sushi california"
        event = kag_engine.learn_from_interaction(session_id, phone, user_utterance, "")
        
        self.assertIsNotNone(event)
        self.assertEqual(event["target_canonical_entity"], "Sushi California")
        self.assertIn("sushi california", kag_engine.aliases_cache)
        print("✅ Test 05 - KAG Autoaprendizaje / Self-Learning: PASSED")

    def test_06_database_persistence(self):
        """Verifica que las órdenes y perfiles de cliente se persistan correctamente."""
        order_dict = {
            "order_id": "RYU-DB-001",
            "customer_phone": "+523385261250",
            "customer_name": "Josué Cabrales",
            "total_amount": 250.0,
            "shipping_fee": 15.0,
            "status": "EN_COCINA"
        }
        proto_bytes = ProtoService.serialize_order_to_bytes(order_dict)
        saved = db_manager.save_order(order_dict, proto_bytes)
        self.assertTrue(saved)

        # Recuperar perfil de cliente
        profile = db_manager.get_customer_profile("+523385261250")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Josué Cabrales")
        self.assertGreaterEqual(profile["total_orders"], 1)
        print("✅ Test 06 - Database Persistence & Profile Recall: PASSED")

if __name__ == "__main__":
    unittest.main()
