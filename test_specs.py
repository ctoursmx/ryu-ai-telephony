#!/usr/bin/env python3
"""
test_specs.py
Suite de verificación automatizada para la arquitectura ADR y especificaciones Open Spec.
Verifica:
1. Integridad y formato MADR de todos los registros ADR en docs/adr/
2. Validez sintáctica y consistencia de openapi.json y openapi.yaml
3. Validez de telephony-spec.yaml y order-contract-spec.yaml
4. Integridad del endpoint dinámico /api/openapi.yaml en FastAPI
"""

import sys
import unittest
import json
import re
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from tools.adr import parse_adr_metadata, get_all_adrs, cmd_audit, ADR_DIR


class TestADRIntegrity(unittest.TestCase):
    """Verifica que todos los ADR cumplan con el estándar Markdown Architectural Decision Record."""

    def test_adr_directory_and_template_exist(self):
        self.assertTrue(ADR_DIR.exists(), "El directorio docs/adr no existe.")
        template_path = ADR_DIR / "template.md"
        self.assertTrue(template_path.exists(), "La plantilla docs/adr/template.md no existe.")
        readme_path = ADR_DIR / "README.md"
        self.assertTrue(readme_path.exists(), "El índice docs/adr/README.md no existe.")

    def test_foundational_adrs_exist(self):
        adrs = get_all_adrs()
        self.assertGreaterEqual(len(adrs), 8, f"Se esperaban al menos 8 ADRs, se encontraron {len(adrs)}.")

    def test_adr_audit_passes(self):
        class DummyArgs:
            pass
        res = cmd_audit(DummyArgs())
        self.assertEqual(res, 0, "cmd_audit falló con errores de consistencia en los ADRs.")

    def test_adr_structure_and_sections(self):
        required_sections = ["Contexto", "Decisión", "Consecuencias"]
        adrs = get_all_adrs()
        for adr_path in adrs:
            meta = parse_adr_metadata(adr_path)
            self.assertIsNotNone(meta, f"No se pudo parsear {adr_path.name}")
            self.assertTrue(meta["id"].startswith("ADR-"), f"El ID debe comenzar con ADR-")
            self.assertIn(meta["status"], ["Aceptado", "Aceptada", "Propuesto", "Propuesta", "Reemplazado", "Reemplazada", "Deprecado", "Deprecada"],
                          f"Estado inválido '{meta['status']}' en {adr_path.name}")
            content = adr_path.read_text(encoding="utf-8")
            for sec in required_sections:
                self.assertTrue(re.search(rf"##.*{sec}", content, re.IGNORECASE),
                                f"Falta sección con '{sec}' en {adr_path.name}")


class TestOpenSpecIntegrity(unittest.TestCase):
    """Verifica la integridad de las especificaciones OpenAPI y Open Spec."""

    def setUp(self):
        self.specs_dir = PROJECT_ROOT / "docs" / "specs"

    def test_specs_files_exist(self):
        expected_files = [
            "openapi.json",
            "openapi.yaml",
            "telephony-spec.yaml",
            "order-contract-spec.yaml",
            "README.md"
        ]
        for fname in expected_files:
            target = self.specs_dir / fname
            self.assertTrue(target.exists(), f"Falta el archivo de especificación {fname}")
            self.assertGreater(target.stat().st_size, 100, f"El archivo {fname} parece estar vacío o truncado")

    def test_openapi_json_and_yaml_syntax(self):
        json_path = self.specs_dir / "openapi.json"
        yaml_path = self.specs_dir / "openapi.yaml"

        with open(json_path, "r", encoding="utf-8") as f:
            data_json = json.load(f)

        with open(yaml_path, "r", encoding="utf-8") as f:
            data_yaml = yaml.safe_load(f)

        self.assertEqual(data_json.get("openapi"), "3.1.0")
        self.assertEqual(data_yaml.get("openapi"), "3.1.0")
        self.assertEqual(data_json.get("info", {}).get("version"), "2.1.0")
        self.assertEqual(data_yaml.get("info", {}).get("version"), "2.1.0")

        # Verificar rutas críticas del sistema
        critical_paths = [
            "/api/auth/login",
            "/api/auth/check",
            "/api/state",
            "/api/stock/ingredient",
            "/api/stock/dish",
            "/api/promotions",
            "/api/delivery-settings",
            "/api/voice-studio/manifest",
            "/api/voice-studio/upload",
            "/api/pos/orders/pending",
            "/api/kitchen-prompt-preview",
            "/api/openapi.yaml"
        ]
        for path in critical_paths:
            self.assertIn(path, data_json.get("paths", {}), f"Ruta {path} no encontrada en openapi.json")
            self.assertIn(path, data_yaml.get("paths", {}), f"Ruta {path} no encontrada en openapi.yaml")

    def test_telephony_spec_content(self):
        spec_path = self.specs_dir / "telephony-spec.yaml"
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)

        self.assertIn("trunk_provider", spec)
        self.assertEqual(spec["trunk_provider"]["name"], "Zadarma")
        self.assertEqual(spec["trunk_provider"]["sip_port"], 5060)
        self.assertIn("audio_pipeline", spec)
        self.assertEqual(spec["audio_pipeline"]["telephony_codec"]["sample_rate_hz"], 8000)
        self.assertEqual(spec["audio_pipeline"]["telephony_codec"]["frame_payload_bytes"], 160)
        self.assertEqual(spec["audio_pipeline"]["transcription_layer"]["compute_type"], "int8")
        self.assertIn("call_state_machine", spec)

    def test_order_contract_spec_content(self):
        spec_path = self.specs_dir / "order-contract-spec.yaml"
        with open(spec_path, "r", encoding="utf-8") as f:
            contract = yaml.safe_load(f)

        self.assertIn("schema_definition", contract)
        schema = contract["schema_definition"]
        required_fields = schema.get("required", [])
        for field in ["order_id", "created_at", "customer", "items", "financials", "status"]:
            self.assertIn(field, required_fields)
        self.assertIn("business_invariants", contract)
        invariants = contract["business_invariants"]
        self.assertGreaterEqual(len(invariants), 4)

    def test_fastapi_live_openapi_endpoint(self):
        from server_telephony_ryu import app
        schema = app.openapi()
        self.assertEqual(schema.get("openapi"), "3.1.0")
        self.assertIn("/api/openapi.yaml", schema.get("paths", {}))
        self.assertIn("/docs", ["/docs", app.docs_url])


if __name__ == "__main__":
    unittest.main(verbosity=2)
