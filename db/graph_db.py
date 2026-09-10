"""
======================================================================
RESTAURANTE RYU - GESTOR DE BASE DE DATOS DE GRAFOS (POSTGRESQL + APACHE AGE)
Soporte para openCypher, almacenamiento binario Protobuf y Fallback Resiliente
======================================================================
"""

import os
import re
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


logger = logging.getLogger("RyuGraphDB")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "ryu_db")

POSTGRES_USER = os.getenv("POSTGRES_USER", "ryu_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ryu_secret_password")

GRAPH_NAME = "ryu_knowledge_graph"

class PostgresAGEManager:
    """Administrador de la conexión con PostgreSQL y la extensión de grafos Apache AGE."""

    def __init__(self):
        self._pg_conn = None
        self._is_age_ready = False
        self._use_fallback = False
        self._init_sqlite_fallback()
        self._try_connect_postgres()

    def _init_sqlite_fallback(self):
        """Inicializa almacenamiento local en caso de que PostgreSQL esté temporalmente fuera de línea."""
        db_path = os.path.join(os.path.dirname(__file__), "ryu_local_cache.db")
        self._sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._sqlite_conn:
            self._sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    phone TEXT PRIMARY KEY,
                    name TEXT,
                    default_address TEXT,
                    default_zone TEXT,
                    notes TEXT,
                    total_orders INTEGER DEFAULT 0,
                    updated_at TEXT
                )
            """)
            self._sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    customer_phone TEXT,
                    customer_name TEXT,
                    total_amount REAL,
                    shipping_fee REAL,
                    status TEXT,
                    proto_payload BLOB,
                    created_at TEXT
                )
            """)
            self._sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS learning_events (
                    event_id TEXT PRIMARY KEY,
                    learned_alias TEXT,
                    target_entity TEXT,
                    entity_type TEXT,
                    applied_to_graph INTEGER DEFAULT 1,
                    created_at TEXT
                )
            """)
            self._sqlite_conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_aliases_cache (
                    alias TEXT PRIMARY KEY,
                    canonical_name TEXT,
                    entity_type TEXT
                )
            """)

    def _try_connect_postgres(self) -> bool:
        """Intenta establecer conexión con PostgreSQL y cargar Apache AGE."""
        try:
            import psycopg2
            import psycopg2.extras

            self._pg_conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                connect_timeout=3
            )
            self._pg_conn.autocommit = True
            
            with self._pg_conn.cursor() as cur:
                # Cargar extensión AGE y configurar search_path
                cur.execute("CREATE EXTENSION IF NOT EXISTS age;")
                cur.execute("LOAD 'age';")
                cur.execute('SET search_path = ag_catalog, "$user", public;')
                
                # Crear grafo si no existe
                cur.execute(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM ag_graph WHERE name = '{GRAPH_NAME}') THEN
                            PERFORM create_graph('{GRAPH_NAME}');
                        END IF;
                    END $$;
                """)
            self._is_age_ready = True
            self._use_fallback = False
            logger.info(f"✅ Conectado exitosamente a PostgreSQL + Apache AGE (Grafo: '{GRAPH_NAME}').")
            return True
        except Exception as e:
            logger.warning(f"⚠️ No se pudo conectar a PostgreSQL + AGE ({e}). Activando motor de grafos en memoria y caché local.")
            self._use_fallback = True
            self._is_age_ready = False
            return False

    @property
    def is_age_connected(self) -> bool:
        return self._is_age_ready and not self._use_fallback

    def execute_cypher(self, query: str, return_cols: str = "v agtype") -> List[Any]:
        """
        Ejecuta una consulta openCypher en Apache AGE.
        Ejemplo: MATCH (d:Dish) WHERE d.price < 100 RETURN d
        """
        if not self.is_age_connected:
            return []

        clean_query = query.replace("$$", "'")
        sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {clean_query} $$) as ({return_cols});"
        try:
            with self._pg_conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error ejecutando Cypher en AGE: {e} | Query: {clean_query}")
            return []

    def save_order(self, order_dict: Dict[str, Any], proto_bytes: bytes) -> bool:
        """Guarda la orden con su payload Protobuf en PostgreSQL o respaldo SQLite."""
        order_id = order_dict.get("order_id", "")
        phone = order_dict.get("customer_phone", "")
        name = order_dict.get("customer_name", "")
        total = float(order_dict.get("total_amount", 0.0))
        shipping = float(order_dict.get("shipping_fee", 0.0))
        status = str(order_dict.get("status", "PENDIENTE_PREPARACION"))
        now_str = datetime.now().isoformat()

        if self.is_age_connected:
            try:
                import psycopg2
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO orders (order_id, customer_phone, customer_name, total_amount, shipping_fee, status, proto_payload, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (order_id) DO UPDATE SET
                            total_amount = EXCLUDED.total_amount,
                            status = EXCLUDED.status,
                            proto_payload = EXCLUDED.proto_payload;
                    """, (order_id, phone, name, total, shipping, status, psycopg2.Binary(proto_bytes), now_str))

                    # Actualizar historial de cliente
                    cur.execute("""
                        INSERT INTO customers (phone, name, total_orders, updated_at)
                        VALUES (%s, %s, 1, %s)
                        ON CONFLICT (phone) DO UPDATE SET
                            name = COALESCE(NULLIF(EXCLUDED.name, 'Cliente'), customers.name),
                            total_orders = customers.total_orders + 1,
                            updated_at = EXCLUDED.updated_at;
                    """, (phone, name, now_str))
                return True
            except Exception as e:
                logger.error(f"Error guardando orden en PostgreSQL: {e}")

        # Fallback local
        try:
            with self._sqlite_conn:
                self._sqlite_conn.execute("""
                    INSERT OR REPLACE INTO orders (order_id, customer_phone, customer_name, total_amount, shipping_fee, status, proto_payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (order_id, phone, name, total, shipping, status, proto_bytes, now_str))
                self._sqlite_conn.execute("""
                    INSERT INTO customers (phone, name, total_orders, updated_at)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(phone) DO UPDATE SET
                        name = COALESCE(NULLIF(excluded.name, 'Cliente'), customers.name),
                        total_orders = customers.total_orders + 1,
                        updated_at = excluded.updated_at
                """, (phone, name, now_str))
            return True
        except Exception as e:
            logger.error(f"Error guardando orden en SQLite local: {e}")
            return False

    def save_call_log(self, call_data: Dict[str, Any], proto_bytes: Optional[bytes] = None) -> bool:
        """Persiste la telemetría, duración y resumen de una llamada telefónica."""
        session_id = call_data.get("session_id", f"call_{int(datetime.now().timestamp())}")
        phone = call_data.get("caller_phone", "Desconocido")
        name = call_data.get("caller_name", "Cliente")
        duration = float(call_data.get("duration_sec", 0.0))
        order_id = call_data.get("order_id", None)
        turn_count = int(call_data.get("turn_count", 0))
        now_str = datetime.now().isoformat()

        if self.is_age_connected:
            try:
                import psycopg2
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO call_logs (session_id, caller_phone, caller_name, duration_sec, order_id, turn_count, proto_payload, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id) DO UPDATE SET
                            duration_sec = EXCLUDED.duration_sec,
                            order_id = COALESCE(EXCLUDED.order_id, call_logs.order_id),
                            turn_count = EXCLUDED.turn_count,
                            proto_payload = COALESCE(EXCLUDED.proto_payload, call_logs.proto_payload);
                    """, (session_id, phone, name, duration, order_id, turn_count, psycopg2.Binary(proto_bytes) if proto_bytes else None, now_str))
                logger.info(f"📞 [Call Log Guardado en PG]: Sesión {session_id} | {turn_count} turnos | {duration:.1f}s")
                return True
            except Exception as e:
                logger.error(f"Error guardando call_log en PostgreSQL: {e}")

        # Fallback local SQLite
        try:
            with self._sqlite_conn:
                self._sqlite_conn.execute("""
                    CREATE TABLE IF NOT EXISTS call_logs (
                        session_id TEXT PRIMARY KEY,
                        caller_phone TEXT,
                        caller_name TEXT,
                        duration_sec REAL,
                        order_id TEXT,
                        turn_count INTEGER,
                        created_at TEXT
                    )
                """)
                self._sqlite_conn.execute("""
                    INSERT OR REPLACE INTO call_logs (session_id, caller_phone, caller_name, duration_sec, order_id, turn_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (session_id, phone, name, duration, order_id, turn_count, now_str))
            return True
        except Exception as e:
            logger.error(f"Error guardando call_log en SQLite local: {e}")
            return False

    def update_customer_profile(self, phone: str, updates: Dict[str, Any]) -> bool:
        """Actualiza campos específicos (dirección, notas, zona) del perfil de un cliente."""
        if not phone or phone in ["Desconocido", "0000000000"]:
            return False
        now_str = datetime.now().isoformat()
        name = updates.get("name")
        address = updates.get("address")
        zone = updates.get("zone")
        notes = updates.get("notes")

        if self.is_age_connected:
            try:
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO customers (phone, name, default_address, default_zone, notes, updated_at)
                        VALUES (%s, COALESCE(%s, 'Cliente'), %s, %s, %s, %s)
                        ON CONFLICT (phone) DO UPDATE SET
                            name = COALESCE(NULLIF(EXCLUDED.name, 'Cliente'), customers.name),
                            default_address = COALESCE(NULLIF(EXCLUDED.default_address, ''), customers.default_address),
                            default_zone = COALESCE(NULLIF(EXCLUDED.default_zone, ''), customers.default_zone),
                            notes = CASE 
                                WHEN customers.notes IS NULL OR customers.notes = '' THEN EXCLUDED.notes
                                WHEN EXCLUDED.notes IS NOT NULL AND EXCLUDED.notes <> '' AND position(EXCLUDED.notes in customers.notes) = 0 
                                    THEN customers.notes || ' | ' || EXCLUDED.notes
                                ELSE customers.notes 
                            END,
                            updated_at = EXCLUDED.updated_at;
                    """, (phone, name, address or "", zone or "", notes or "", now_str))
                return True
            except Exception as e:
                logger.error(f"Error actualizando perfil en PostgreSQL: {e}")

        try:
            with self._sqlite_conn:
                self._sqlite_conn.execute("""
                    INSERT INTO customers (phone, name, default_address, default_zone, notes, updated_at)
                    VALUES (?, COALESCE(?, 'Cliente'), ?, ?, ?, ?)
                    ON CONFLICT(phone) DO UPDATE SET
                        default_address = COALESCE(NULLIF(excluded.default_address, ''), customers.default_address),
                        default_zone = COALESCE(NULLIF(excluded.default_zone, ''), customers.default_zone),
                        notes = COALESCE(NULLIF(excluded.notes, ''), customers.notes),
                        updated_at = excluded.updated_at
                """, (phone, name, address or "", zone or "", notes or "", now_str))
            return True
        except Exception as e:
            logger.error(f"Error actualizando perfil en SQLite: {e}")
            return False

    def save_learning_event(self, event_dict: Dict[str, Any], proto_bytes: bytes) -> bool:
        """Persiste un nuevo aprendizaje o corrección fonética en la base de datos."""
        event_id = event_dict.get("event_id", f"LRN-{int(datetime.now().timestamp())}")
        alias = event_dict.get("learned_alias", "").lower().strip()
        target = event_dict.get("target_canonical_entity", "").strip()
        etype = event_dict.get("entity_type", "DISH")
        now_str = datetime.now().isoformat()

        if not alias or not target:
            return False

        # 1. Guardar en tabla de eventos
        if self.is_age_connected:
            try:
                import psycopg2
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO learning_events (event_id, learned_alias, target_entity, entity_type, proto_payload, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (event_id) DO NOTHING;
                    """, (event_id, alias, target, etype, psycopg2.Binary(proto_bytes), now_str))
            except Exception as e:
                logger.warning(f"Error guardando learning_event en PG: {e}")

        with self._sqlite_conn:
            self._sqlite_conn.execute("""
                INSERT OR IGNORE INTO learning_events (event_id, learned_alias, target_entity, entity_type, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (event_id, alias, target, etype, now_str))
            self._sqlite_conn.execute("""
                INSERT OR REPLACE INTO graph_aliases_cache (alias, canonical_name, entity_type)
                VALUES (?, ?, ?)
            """, (alias, target, etype))

        # 2. Inyectar nuevo nodo y arista en el Grafo de Apache AGE
        if self.is_age_connected:
            try:
                cypher_alias = f"""
                    MERGE (a:Alias {{name: '{alias}', entity_type: '{etype}'}})
                    WITH a
                    MATCH (d:Dish) WHERE toLower(d.name) = toLower('{target}')
                    MERGE (d)-[:HAS_ALIAS]->(a)
                    RETURN count(a)
                """
                self.execute_cypher(cypher_alias, return_cols="cnt agtype")
                logger.info(f"🧠 [Autoaprendizaje AGE]: Alias '{alias}' vinculado a '{target}' en el grafo.")
            except Exception as e:
                logger.warning(f"No se pudo enlazar alias en AGE: {e}")

        return True

    def get_customer_profile(self, phone: str) -> Optional[Dict[str, Any]]:
        """Recupera el perfil, preferencias y dirección de un cliente recurrente."""
        if not phone or phone == "Desconocido":
            return None

        if self.is_age_connected:
            try:
                with self._pg_conn.cursor() as cur:
                    cur.execute("""
                        SELECT phone, name, default_address, default_zone, notes, total_orders
                        FROM customers WHERE phone = %s;
                    """, (phone,))
                    row = cur.fetchone()
                    if row:
                        return {
                            "phone": row[0],
                            "name": row[1],
                            "default_address": row[2] or "",
                            "default_zone": row[3] or "",
                            "notes": row[4] or "",
                            "total_orders": row[5] or 0
                        }
            except Exception as e:
                logger.warning(f"Error consultando cliente en PG: {e}")

        # Consulta en SQLite local
        cur = self._sqlite_conn.cursor()
        cur.execute("SELECT phone, name, default_address, default_zone, notes, total_orders FROM customers WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row:
            return {
                "phone": row[0],
                "name": row[1],
                "default_address": row[2] or "",
                "default_zone": row[3] or "",
                "notes": row[4] or "",
                "total_orders": row[5] or 0
            }
        return None

    def get_all_learned_aliases(self) -> Dict[str, str]:
        """Obtiene el mapa de alias fonéticos acumulados."""
        aliases = {}
        # Primero leer de SQLite
        cur = self._sqlite_conn.cursor()
        for row in cur.execute("SELECT alias, canonical_name FROM graph_aliases_cache"):
            aliases[row[0].lower()] = row[1]

        # Si AGE está disponible, fusionar con nodos Alias del grafo
        if self.is_age_connected:
            try:
                res = self.execute_cypher("MATCH (d:Dish)-[:HAS_ALIAS]->(a:Alias) RETURN d.name, a.name", return_cols="dish agtype, alias agtype")
                for row in res:
                    dish_val = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    alias_val = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    aliases[str(alias_val).lower()] = str(dish_val)
            except Exception as e:
                logger.warning(f"Error extrayendo alias desde AGE: {e}")

        return aliases

# Instancia singleton global
db_manager = PostgresAGEManager()
