#!/usr/bin/env python3
"""
tools/adr.py
Herramienta de línea de comandos para la gestión de Architecture Decision Records (ADRs) en Ryu.
Comandos:
  python tools/adr.py list             # Lista todos los ADRs y su estado
  python tools/adr.py new "<Título>"   # Genera un nuevo ADR a partir de template.md
  python tools/adr.py audit            # Audita formato, integridad y consistencia del índice
"""

import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

# Garantizar compatibilidad con emojis en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT_DIR / "docs" / "adr"
TEMPLATE_FILE = ADR_DIR / "template.md"
INDEX_FILE = ADR_DIR / "README.md"


def get_all_adrs():
    """Retorna una lista ordenada de archivos ADR existentes."""
    if not ADR_DIR.exists():
        return []
    adr_files = sorted([f for f in ADR_DIR.glob("*.md") if re.match(r"^\d{4}-.*\.md$", f.name)])
    return adr_files


def parse_adr_metadata(file_path: Path) -> dict:
    """Extrae metadatos (ID, Título, Estado, Fecha) de un archivo ADR."""
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    title = lines[0].lstrip("# ").strip() if lines else file_path.stem
    m_id = re.match(r"^(\d{4})", file_path.name)
    num_str = m_id.group(1) if m_id else "0000"

    status = "Desconocido"
    date_str = ""
    for line in lines[:15]:
        if "Estado" in line:
            m_stat = re.search(r"\*\*Estado\*\*:\s*`?([^`*\r\n]+)`?", line)
            if m_stat:
                status = m_stat.group(1).strip()
        if "Fecha" in line:
            m_date = re.search(r"\*\*Fecha\*\*:\s*([0-9-]+)", line)
            if m_date:
                date_str = m_date.group(1).strip()

    return {
        "id": f"ADR-{num_str}",
        "number": int(num_str),
        "filename": file_path.name,
        "title": title,
        "status": status,
        "date": date_str,
        "path": file_path
    }


def cmd_list(args):
    """Lista todos los ADRs en formato tabla de consola."""
    adrs = [parse_adr_metadata(f) for f in get_all_adrs()]
    if not adrs:
        print("No se encontraron registros ADR en docs/adr/.")
        return 0

    print("\n" + "=" * 80)
    print(f"{'ID':<10} {'ESTADO':<15} {'FECHA':<12} {'TÍTULO'}")
    print("=" * 80)
    for a in adrs:
        print(f"{a['id']:<10} {a['status']:<15} {a['date']:<12} {a['title'][:40]}")
    print("=" * 80)
    print(f"Total: {len(adrs)} decisiones registradas.\n")
    return 0


def slugify(text: str) -> str:
    """Convierte un título a formato kebab-case amigable para nombre de archivo."""
    text = text.lower()
    text = re.sub(r"[áäàâ]", "a", text)
    text = re.sub(r"[éëèê]", "e", text)
    text = re.sub(r"[íïìî]", "i", text)
    text = re.sub(r"[óöòô]", "o", text)
    text = re.sub(r"[úüùû]", "u", text)
    text = re.sub(r"[ñ]", "n", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def cmd_new(args):
    """Crea un nuevo archivo ADR basado en la plantilla."""
    title = args.title.strip()
    if not title:
        print("Error: Debes proporcionar un título para el nuevo ADR.")
        return 1

    adrs = [parse_adr_metadata(f) for f in get_all_adrs()]
    next_num = (max([a["number"] for a in adrs]) + 1) if adrs else 1
    num_str = f"{next_num:04d}"
    slug = slugify(title)
    filename = f"{num_str}-{slug}.md"
    new_path = ADR_DIR / filename

    if not TEMPLATE_FILE.exists():
        print(f"Error: La plantilla {TEMPLATE_FILE} no existe.")
        return 1

    template_content = TEMPLATE_FILE.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    # Reemplazar encabezado
    header_repl = f"# ADR-{num_str}: {title}\n\n* **Estado**: `Propuesta`\n* **Fecha**: {today}"
    new_content = re.sub(
        r"^# \[Número.*?\n\n\* \*\*Estado\*\*.*?\n\* \*\*Fecha\*\*.*?",
        header_repl,
        template_content,
        flags=re.DOTALL
    )

    new_path.write_text(new_content, encoding="utf-8")
    print(f"✅ Nuevo ADR creado exitosamente: docs/adr/{filename}")
    print(f"👉 Edita el archivo para documentar el contexto, opciones y consecuencias.")
    return 0


def cmd_audit(args):
    """Verifica la consistencia técnica de todos los ADRs y el índice README.md."""
    print("🔍 Auditando Registros de Decisión Arquitectónica (ADR)...")
    errors = []
    adrs = get_all_adrs()

    if not adrs:
        errors.append("No hay archivos ADR en docs/adr/.")

    if not INDEX_FILE.exists():
        errors.append("Falta el archivo índice docs/adr/README.md.")
    else:
        index_content = INDEX_FILE.read_text(encoding="utf-8")
        for f in adrs:
            if f.name not in index_content:
                errors.append(f"El archivo {f.name} no está enlazado en docs/adr/README.md.")

    for f in adrs:
        meta = parse_adr_metadata(f)
        if meta["status"] in ["Desconocido", ""]:
            errors.append(f"El archivo {f.name} no especifica un Estado válido.")
        if not meta["date"]:
            errors.append(f"El archivo {f.name} no especifica una Fecha válida.")

    if errors:
        print("\n❌ Se encontraron problemas en los ADRs:")
        for err in errors:
            print(f"  - {err}")
        return 1
    else:
        print(f"\n✅ Todos los {len(adrs)} ADRs son consistentes, válidos y están indexados correctamente.")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Gestor de Architecture Decision Records (ADR) para Ryu")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="Lista todos los ADRs registrados")
    p_list.set_defaults(func=cmd_list)

    # new
    p_new = subparsers.add_parser("new", help="Crea un nuevo ADR")
    p_new.add_argument("title", help="Título breve de la decisión arquitectónica")
    p_new.set_defaults(func=cmd_new)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audita la consistencia y formato de los ADRs")
    p_audit.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
