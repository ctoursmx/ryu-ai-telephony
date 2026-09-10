"""
Genera el script SQL para sembrar el grafo de Apache AGE en PostgreSQL
"""
import json
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
menu_path = os.path.join(base_dir, "menu_ryu.json")
out_sql = os.path.join(base_dir, "db", "seed_age_graph.sql")

with open(menu_path, "r", encoding="utf-8") as f:
    data = json.load(f)

lines = [
    "LOAD 'age';",
    'SET search_path = ag_catalog, "$user", public;',
    ""
]

# Zonas
zones = data.get("service_policies", {}).get("delivery_rules", {}).get("special_remote_zones", [])
for z in zones:
    z_id = z.get("zone_id", "").replace("'", "")
    name = z.get("name", "").replace("'", "")
    fee = float(z.get("fee", 0.0))
    lines.append(f"SELECT * FROM cypher('ryu_knowledge_graph', $$ MERGE (z:Zone {{id: '{z_id}', name: '{name}', fee: {fee}, is_rural: true}}) RETURN z $$) as (v agtype);")

# Menus y Platillos
menus = data.get("menu", {})
for mtype, subcats in menus.items():
    if not isinstance(subcats, dict):
        continue
    for subcat, items in subcats.items():
        if not isinstance(items, list):
            continue
        lines.append(f"SELECT * FROM cypher('ryu_knowledge_graph', $$ MERGE (c:Category {{name: '{subcat.upper()}', menu: '{mtype.upper()}'}}) RETURN c $$) as (v agtype);")
        for item in items:
            dish_id = item.get("id", "").replace("'", "")
            name = item.get("name", "").replace("'", "")
            price = float(item.get("price", 0.0))
            is_combo = "combo" in name.lower() or "paquete" in name.lower() or "caja" in name.lower()
            lines.append(f"SELECT * FROM cypher('ryu_knowledge_graph', $$ MERGE (d:Dish {{id: '{dish_id}', name: '{name}', price: {price}, is_combo: {str(is_combo).lower()}}}) RETURN d $$) as (v agtype);")

with open(out_sql, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Generado seed_age_graph.sql con {len(lines)} sentencias Cypher.")
