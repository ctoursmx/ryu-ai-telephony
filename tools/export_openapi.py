#!/usr/bin/env python3
"""
tools/export_openapi.py
Exportador automatizado de la especificación OpenAPI 3.1 para el ecosistema Ryu AI Telephony.
Genera docs/specs/openapi.json y docs/specs/openapi.yaml a partir de la app FastAPI en vivo.
"""

import sys
import os
from pathlib import Path
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from server_telephony_ryu import app


def export_specs():
    specs_dir = PROJECT_ROOT / "docs" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)

    print("Obteniendo esquema OpenAPI desde FastAPI...")
    openapi_schema = app.openapi()

    json_path = specs_dir / "openapi.json"
    yaml_path = specs_dir / "openapi.yaml"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    json_size_kb = json_path.stat().st_size / 1024

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    yaml_size_kb = yaml_path.stat().st_size / 1024

    total_paths = len(openapi_schema.get("paths", {}))
    total_operations = sum(len(methods) for methods in openapi_schema.get("paths", {}).values())
    tags = [t.get("name") for t in openapi_schema.get("tags", [])]

    print("=" * 60)
    print("ESPECIFICACION OPENAPI EXPORTADA EXITOSAMENTE")
    print("=" * 60)
    print(f"Version OpenAPI : {openapi_schema.get('openapi')}")
    print(f"Titulo API      : {openapi_schema.get('info', {}).get('title')}")
    print(f"Version API     : {openapi_schema.get('info', {}).get('version')}")
    print(f"Rutas (Paths)   : {total_paths}")
    print(f"Operaciones     : {total_operations}")
    print(f"Etiquetas ({len(tags)}): {', '.join(tags)}")
    print(f"Archivo JSON    : {json_path.relative_to(PROJECT_ROOT)} ({json_size_kb:.1f} KB)")
    print(f"Archivo YAML    : {yaml_path.relative_to(PROJECT_ROOT)} ({yaml_size_kb:.1f} KB)")
    print("=" * 60)


if __name__ == "__main__":
    export_specs()
