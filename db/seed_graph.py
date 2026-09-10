"""
======================================================================
RESTAURANTE RYU - SEMBRADOR DEL GRAFO DE CONOCIMIENTO (APACHE AGE + KAG)
Convierte el menú oficial y políticas en nodos y relaciones de grafos
======================================================================
"""

import os
import json
import logging
from pathlib import Path
from db.graph_db import db_manager, GRAPH_NAME

logger = logging.getLogger("RyuGraphSeeder")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

MENU_PATH = Path(__file__).parent.parent / "menu_ryu.json"

# Alias fonéticos y errores de transcripción comunes en Tequila, Jalisco
INITIAL_PHONETIC_ALIASES = [
    ("sucho", "Sushi", "DISH"),
    ("suchi", "Sushi", "DISH"),
    ("sucesos", "Sushi", "DISH"),
    ("dos sucesos", "Sushi", "DISH"),
    ("proguesa", "Hamburguesa", "DISH"),
    ("la proguesa", "Hamburguesa", "DISH"),
    ("soñada", "Lasaña", "DISH"),
    ("la soñada", "Lasaña", "DISH"),
    ("petit chigni", "Fettuccine", "DISH"),
    ("petuchini", "Fettuccine", "DISH"),
    ("petuccini", "Fettuccine", "DISH"),
    ("gubua", "Boba", "INGREDIENT"),
    ("todas italianas", "Sodas Italianas", "CATEGORY"),
    ("de todas italianas", "Sodas Italianas", "CATEGORY"),
    ("callejira sol", "Calle Girasol", "ZONE"),
    ("girazón", "Calle Girasol", "ZONE"),
    ("costradía", "Colonia Cofradía", "ZONE"),
    ("cofradía", "Colonia Cofradía", "ZONE"),
    ("cantaritos", "Cantaritos El Güero", "ZONE"),
    ("tierra de agave", "Tierra de Agave", "ZONE"),
    ("aguacatillo", "Aguacatillo", "ZONE"),
    ("san pedro", "San Pedro", "ZONE"),
    ("santa ana", "Santa Ana", "ZONE")
]

def load_menu_json():
    with open(MENU_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def seed_knowledge_graph():
    """Siembra nodos y relaciones en Apache AGE y la base de datos de grafos."""
    data = load_menu_json()
    logger.info("Iniciando siembra del Grafo de Conocimiento de Ryu...")

    # 1. Sembrar Zonas de Envío
    zones = data.get("service_policies", {}).get("delivery_rules", {}).get("special_remote_zones", [])
    logger.info(f"Sembrando {len(zones)} zonas especiales de envío...")
    
    for z in zones:
        z_id = z.get("zone_id", "")
        name = z.get("name", "").replace("'", "")
        fee = float(z.get("fee", 0.0))
        aliases = z.get("aliases", [])

        # AGE openCypher
        if db_manager.is_age_connected:
            cypher = f"""
                MERGE (z:Zone {{id: '{z_id}', name: '{name}', fee: {fee}, is_rural: true}})
                RETURN z.name
            """
            db_manager.execute_cypher(cypher)

        # Sembrar alias
        for alias in aliases:
            db_manager.save_learning_event({
                "event_id": f"INIT-ZONE-{z_id}-{hash(alias)}",
                "learned_alias": alias,
                "target_canonical_entity": name,
                "entity_type": "ZONE"
            }, b"")

    # Zona Urbana Tequila
    urban_info = data.get("service_policies", {}).get("delivery_rules", {}).get("tequila_urban_zone", {})
    if db_manager.is_age_connected:
        db_manager.execute_cypher(f"""
            MERGE (z:Zone {{id: 'zon_urban', name: 'Tequila Urbano', daytime_fee: 0, nighttime_fee: 15, is_rural: false}})
            RETURN z.name
        """)

    # 2. Sembrar Categorías y Platillos
    menus = data.get("menu", {})
    total_dishes = 0

    for menu_type, subcats in menus.items():
        if not isinstance(subcats, dict):
            continue

        if db_manager.is_age_connected:
            db_manager.execute_cypher(f"""
                MERGE (c:MenuSection {{name: '{menu_type.upper()}'}})
                RETURN c.name
            """)

        for subcat_name, items in subcats.items():
            if not isinstance(items, list):
                continue

            if db_manager.is_age_connected:
                db_manager.execute_cypher(f"""
                    MERGE (sc:Category {{name: '{subcat_name.upper()}', menu: '{menu_type.upper()}'}})
                    RETURN sc.name
                """)

            for item in items:
                dish_id = item.get("id", "").replace("'", "")
                name = item.get("name", "").replace("'", "")
                price = float(item.get("price", 0.0))
                desc = item.get("description", "").replace("'", "")
                is_combo = "combo" in name.lower() or "paquete" in name.lower() or "caja" in name.lower() or "pack" in name.lower()
                aliases = item.get("aliases", [])

                if db_manager.is_age_connected:
                    cypher_dish = f"""
                        MERGE (d:Dish {{
                            id: '{dish_id}',
                            name: '{name}',
                            price: {price},
                            is_combo: {str(is_combo).lower()},
                            category: '{subcat_name.upper()}',
                            menu: '{menu_type.upper()}'
                        }})
                        WITH d
                        MATCH (sc:Category {{name: '{subcat_name.upper()}'}})
                        MERGE (d)-[:BELONGS_TO]->(sc)
                        RETURN d.name
                    """
                    db_manager.execute_cypher(cypher_dish)

                total_dishes += 1

                # Registrar alias oficiales del JSON
                for al in aliases:
                    db_manager.save_learning_event({
                        "event_id": f"INIT-DISH-{dish_id}-{hash(al)}",
                        "learned_alias": al,
                        "target_canonical_entity": name,
                        "entity_type": "DISH"
                    }, b"")

    # 3. Sembrar Alias Fonéticos Iniciales
    logger.info(f"Sembrando {len(INITIAL_PHONETIC_ALIASES)} alias fonéticos del lenguaje mexicano...")
    for alias, target, etype in INITIAL_PHONETIC_ALIASES:
        db_manager.save_learning_event({
            "event_id": f"INIT-PHONETIC-{hash(alias)}",
            "learned_alias": alias,
            "target_canonical_entity": target,
            "entity_type": etype
        }, b"")

    logger.info(f"✅ Grafo de conocimiento sembrado exitosamente: {total_dishes} platillos y productos integrados.")

if __name__ == "__main__":
    seed_knowledge_graph()
