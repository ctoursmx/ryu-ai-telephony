# -*- coding: utf-8 -*-
"""
======================================================================
RESTAURANTE RYU - PUENTE SOFT RESTAURANT & DESPACHADOR MULTIESTACIÓN
Inyección SQL Server, Descuento de Inventario y Comanda de Prioridad IA
======================================================================
"""

import os
import sys
import json
import socket
import logging
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("RyuSoftRestaurantBridge")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'printer_config.json')

DEFAULT_CONFIG = {
    "mode": "escpos_network",
    "enable_sql_injection": True,
    "enable_escpos_printing": True,
    "soft_restaurant_db": {
        "server": "localhost\\SOFTRESTAURANT",
        "database": "SOFTRESTAURANT10",
        "user": "sa",
        "password": "your_password",
        "driver": "ODBC Driver 17 for SQL Server",
        "trusted_connection": False
    },
    "priority_alert_settings": {
        "enabled": True,
        "header_title": "¡¡ATENCIÓN COCINA - ALTA PRIORIDAD!!",
        "source_badge": "PEDIDO TOMADO POR INTELIGENCIA ARTIFICIAL",
        "promised_delivery_time": "40 a 50 minutos",
        "print_to_all_stations": True,
        "expediter_printer_key": "expediter"
    },
    "printers": {
        "expediter": { "ip": "192.168.1.100", "port": 9100, "name": "Impresora Principal / Expedición" },
        "sushi_bar": { "ip": "192.168.1.101", "port": 9100, "name": "Impresora Barra Sushi" },
        "hot_kitchen": { "ip": "192.168.1.102", "port": 9100, "name": "Impresora Cocina Caliente" },
        "italian_kitchen": { "ip": "192.168.1.103", "port": 9100, "name": "Impresora Italiana" },
        "snack_kitchen": { "ip": "192.168.1.104", "port": 9100, "name": "Impresora Snacks" },
        "drinks_bar": { "ip": "192.168.1.105", "port": 9100, "name": "Impresora Barra Bebidas" }
    }
}

def get_config() -> Dict[str, Any]:
    """Carga configuración combinando printer_config.json y variables de entorno."""
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg.update(json.load(f))
        except Exception as e:
            logger.warning(f"Error leyendo {CONFIG_FILE}: {e}")

    # Sobrescritura con variables de entorno si existen
    sql_cfg = cfg.get("soft_restaurant_db", {})
    sql_cfg["server"] = os.getenv("SOFTRESTAURANT_SERVER", sql_cfg.get("server", "localhost\\SOFTRESTAURANT"))
    sql_cfg["database"] = os.getenv("SOFTRESTAURANT_DATABASE", sql_cfg.get("database", "SOFTRESTAURANT10"))
    sql_cfg["user"] = os.getenv("SOFTRESTAURANT_USER", sql_cfg.get("user", "sa"))
    sql_cfg["password"] = os.getenv("SOFTRESTAURANT_PASSWORD", sql_cfg.get("password", ""))
    sql_cfg["driver"] = os.getenv("SOFTRESTAURANT_DRIVER", sql_cfg.get("driver", "ODBC Driver 17 for SQL Server"))
    cfg["soft_restaurant_db"] = sql_cfg

    if os.getenv("SOFTRESTAURANT_ENABLE_INJECTION") is not None:
        cfg["enable_sql_injection"] = os.getenv("SOFTRESTAURANT_ENABLE_INJECTION", "").lower() in ["true", "1", "yes"]

    return cfg

class SoftRestaurantSQLBridge:
    """Gestor de integración transaccional con Microsoft SQL Server de Soft Restaurant."""

    def __init__(self):
        self.config = get_config()
        self._init_offline_queue()

    def _init_offline_queue(self):
        """Inicializa cola SQLite local de contingencia en caso de que SQL Server esté temporalmente apagado."""
        db_path = os.path.join(os.path.dirname(__file__), "db", "soft_restaurant_offline_queue.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.sqlite_queue = sqlite3.connect(db_path, check_same_thread=False)
        with self.sqlite_queue:
            self.sqlite_queue.execute("""
                CREATE TABLE IF NOT EXISTS pending_orders (
                    folio_ryu TEXT PRIMARY KEY,
                    payload_json TEXT,
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT
                )
            """)

    def get_connection(self):
        """Crea conexión ODBC a Microsoft SQL Server."""
        try:
            import pyodbc
        except ImportError:
            raise RuntimeError("pyodbc no está instalado. Ejecuta: pip install pyodbc")

        db_cfg = self.config.get("soft_restaurant_db", {})
        driver = db_cfg.get("driver", "ODBC Driver 17 for SQL Server")
        server = db_cfg.get("server", "localhost\\SOFTRESTAURANT")
        database = db_cfg.get("database", "SOFTRESTAURANT10")
        user = db_cfg.get("user", "sa")
        password = db_cfg.get("password", "")

        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
            "Connection Timeout=3;"
        )
        return pyodbc.connect(conn_str)

    def inject_order_and_deduct_inventory(self, order: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Inserta el pedido en SQL Server de Soft Restaurant y descuenta inventario.
        Si la base de datos está offline, encola el pedido localmente.
        """
        folio = order.get("order_id", f"RYU-{int(datetime.now().timestamp())}")
        cliente = order.get("customer_name", "Cliente")
        telefono = order.get("customer_phone", "Desconocido")
        tipo_entrega = order.get("delivery_type", "domicilio")
        direccion = order.get("address", "")
        zona = order.get("zone_name", "Tequila Urbano")
        total = float(order.get("total_amount", 0.0))
        envio = float(order.get("shipping_fee", 0.0))
        subtotal = float(order.get("items_subtotal", max(0.0, total - envio)))
        metodo_pago = order.get("payment_method", "Efectivo")
        paga_con = float(order.get("payment_change_for", 0.0) or 0.0)
        es_futuro = 1 if order.get("is_future_order") else 0
        fecha_prog = str(order.get("scheduled_time", ""))

        # 1. Intentar inyección directa en SQL Server
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # A) Registrar encabezado de comanda
            cursor.execute("""
                EXEC sp_Ryu_RegistrarPedidoIA
                    @FolioRyu = ?,
                    @ClienteNombre = ?,
                    @ClienteTelefono = ?,
                    @TipoEntrega = ?,
                    @DireccionEntrega = ?,
                    @ZonaEntrega = ?,
                    @SubtotalPlatillos = ?,
                    @CostoEnvio = ?,
                    @TotalACobrar = ?,
                    @MetodoPago = ?,
                    @PagaCon = ?,
                    @EsFuturo = ?,
                    @FechaProgramada = ?;
            """, (folio, cliente, telefono, tipo_entrega, direccion, zona,
                  subtotal, envio, total, metodo_pago, paga_con, es_futuro, fecha_prog))

            # B) Registrar partidas y descontar inventario
            items = order.get("items", [])
            for item in items:
                nombre_platillo = item.get("name", "Platillo")
                cantidad = int(item.get("quantity", 1))
                precio = float(item.get("price", item.get("unit_price", 0.0)))
                estacion = item.get("station", "hot_kitchen")
                notas = item.get("notes", "")

                cursor.execute("""
                    EXEC sp_Ryu_DescontarInventarioItem
                        @FolioRyu = ?,
                        @NombrePlatillo = ?,
                        @Cantidad = ?,
                        @PrecioUnitario = ?,
                        @Estacion = ?,
                        @Notas = ?;
                """, (folio, nombre_platillo, cantidad, precio, estacion, notas))

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"✅ [Soft Restaurant SQL]: Comanda {folio} inyectada e inventario descontado exitosamente.")
            return True, "Inyección e inventario completados en Soft Restaurant"

        except Exception as e:
            logger.warning(f"⚠️ [Soft Restaurant SQL Offline/Simulación]: No se pudo conectar a SQL Server ({e}). Encolando localmente.")
            # Guardar en cola de contingencia local SQLite
            try:
                with self.sqlite_queue:
                    self.sqlite_queue.execute("""
                        INSERT OR REPLACE INTO pending_orders (folio_ryu, payload_json, status, created_at)
                        VALUES (?, ?, 'QUEUED_OFFLINE', ?)
                    """, (folio, json.dumps(order, ensure_ascii=False), datetime.now().isoformat()))
                return False, f"SQL Server offline. Comanda encolada localmente: {e}"
            except Exception as err_q:
                logger.error(f"Error encolando en SQLite: {err_q}")
                return False, str(e)

    def process_offline_queue(self) -> int:
        """Procesa y reintenta inyectar pedidos que quedaron pendientes en la cola SQLite."""
        try:
            with self.sqlite_queue:
                cur = self.sqlite_queue.cursor()
                cur.execute("SELECT folio_ryu, payload_json FROM pending_orders WHERE status = 'QUEUED_OFFLINE'")
                rows = cur.fetchall()
                if not rows:
                    return 0
                
                success_count = 0
                for folio, payload_str in rows:
                    order = json.loads(payload_str)
                    conn = None
                    try:
                        conn = self.get_connection()
                        # Si conecta con éxito, inyectamos directamente
                        cursor = conn.cursor()
                        cursor.execute("""
                            EXEC sp_Ryu_RegistrarPedidoIA
                                @FolioRyu = ?, @ClienteNombre = ?, @ClienteTelefono = ?,
                                @TipoEntrega = ?, @DireccionEntrega = ?, @ZonaEntrega = ?,
                                @SubtotalPlatillos = ?, @CostoEnvio = ?, @TotalACobrar = ?,
                                @MetodoPago = ?, @PagaCon = ?, @EsFuturo = ?, @FechaProgramada = ?;
                        """, (
                            order.get("order_id"), order.get("customer_name", "Cliente"),
                            order.get("customer_phone", ""), order.get("delivery_type", "domicilio"),
                            order.get("address", ""), order.get("zone_name", "Tequila Urbano"),
                            float(order.get("items_subtotal", 0.0)), float(order.get("shipping_fee", 0.0)),
                            float(order.get("total_amount", 0.0)), order.get("payment_method", "Efectivo"),
                            float(order.get("payment_change_for", 0.0) or 0.0),
                            1 if order.get("is_future_order") else 0, str(order.get("scheduled_time", ""))
                        ))
                        for item in order.get("items", []):
                            cursor.execute("""
                                EXEC sp_Ryu_DescontarInventarioItem
                                    @FolioRyu = ?, @NombrePlatillo = ?, @Cantidad = ?,
                                    @PrecioUnitario = ?, @Estacion = ?, @Notas = ?;
                            """, (
                                order.get("order_id"), item.get("name"), int(item.get("quantity", 1)),
                                float(item.get("price", item.get("unit_price", 0.0))),
                                item.get("station", "hot_kitchen"), item.get("notes", "")
                            ))
                        conn.commit()
                        cursor.close()
                        conn.close()

                        cur.execute("UPDATE pending_orders SET status = 'PROCESSED' WHERE folio_ryu = ?", (folio,))
                        success_count += 1
                        logger.info(f"✅ Pedido en cola {folio} sincronizado con Soft Restaurant.")
                    except Exception as err:
                        if conn:
                            conn.close()
                        logger.debug(f"Aún no se puede sincronizar pedido {folio}: {err}")
                        break # Si falló la conexión, detenemos reintentos por ahora
                return success_count
        except Exception as e:
            logger.error(f"Error procesando cola offline: {e}")
            return 0

# Instancia singleton del puente SQL
sql_bridge = SoftRestaurantSQLBridge()

def generate_ai_priority_ticket(order: Dict[str, Any]) -> str:
    """
    Genera la comanda adicional especial de ALTA PRIORIDAD para cocina y repartidores,
    indicando claramente que proviene del sistema de IA con promesa de tiempo.
    """
    date_str = datetime.now().strftime('%d/%m/%Y %I:%M %p')
    deliv_type = '🛵 A DOMICILIO' if order.get('delivery_type') == 'domicilio' else '🥡 PARA RECOGER (SUCURSAL)'
    cfg = get_config().get("priority_alert_settings", {})
    promised_time = cfg.get("promised_delivery_time", "40 a 50 minutos")
    
    total = float(order.get('total_amount', 0.0))
    shipping = float(order.get('shipping_fee', 0.0))
    subtotal = float(order.get('items_subtotal', max(0.0, total - shipping)))

    lines = [
        "========================================",
        " 🔥 ¡¡ATENCIÓN COCINA - ALTA PRIORIDAD!! 🔥 ",
        "  🤖 PEDIDO DE INTELIGENCIA ARTIFICIAL  ",
        "========================================",
        f"FOLIO RYU:   #{order.get('order_id', '001')}",
        f"FECHA/HORA:  {date_str}",
        f"CLIENTE:     {order.get('customer_name', 'General')}",
        f"TELÉFONO:    {order.get('customer_phone', 'No especificado')}",
        f"MODALIDAD:   {deliv_type}",
    ]

    if order.get('delivery_type') == 'domicilio' and order.get('address'):
        lines.append(f"DIRECCIÓN:   {order.get('address')}")
    if order.get('references'):
        lines.append(f"REFERENCIAS: {order.get('references')}")

    lines.extend([
        "----------------------------------------",
        "  ⚠️  DAR PRIORIDAD MÁXIMA EN COCINA  ⚠️ ",
        f"  ⏱️  TIEMPO PROMETIDO: {promised_time}",
        "----------------------------------------",
        "CANT  DESCRIPCIÓN COMPLETA DEL PEDIDO"
    ])

    for idx, item in enumerate(order.get('items', []), 1):
        lines.append(f" {item.get('quantity', 1)}x  {item.get('name')} (${float(item.get('price', item.get('unit_price', 0.0))):.2f})")
        if item.get('options'):
            lines.append(f"     ↳ Opciones: {', '.join(item.get('options'))}")
        if item.get('notes'):
            lines.append(f"     ↳ NOTA: {item.get('notes')}")

    lines.extend([
        "----------------------------------------",
        f"SUBTOTAL:     ${subtotal:.2f} MXN",
        f"ENVÍO:        ${shipping:.2f} MXN",
        f"TOTAL COBRAR: ${total:.2f} MXN",
        f"FORMA PAGO:   {order.get('payment_method', 'Efectivo')}",
    ])

    if order.get('payment_change_for'):
        paga = float(order.get('payment_change_for'))
        cambio = max(0.0, paga - total)
        lines.append(f"PAGA CON:     ${paga:.2f} (Cambio: ${cambio:.2f})")

    lines.extend([
        "========================================",
        "  ✅ TICKET VALIDADO Y AUDITADO POR IA  ",
        "========================================",
        "\n\n\n" # Espacio para corte
    ])

    return "\n".join(lines)

def generate_station_ticket(station_name: str, order: Dict[str, Any], station_items: List[Dict[str, Any]]) -> str:
    """Genera la comanda específica para la estación de preparación (Sushi, Caliente, etc.)."""
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    deliv_type = 'A DOMICILIO' if order.get('delivery_type') == 'domicilio' else 'PARA LLEVAR'
    
    lines = [
        "========================================",
        f"       ESTACIÓN: {station_name.upper()}",
        f"         ORDEN #{order.get('order_id', '001')}",
        "========================================",
        f"Fecha: {date_str}",
        f"Cliente: {order.get('customer_name', 'General')}",
        f"Tipo: {deliv_type}",
        "----------------------------------------",
        "CANT  DESCRIPCION"
    ]
    
    for item in station_items:
        lines.append(f"{item.get('quantity', 1)}x    {item.get('name')}")
        if item.get('options'):
            lines.append(f"      * {', '.join(item.get('options'))}")
        if item.get('notes'):
            lines.append(f"      * NOTA: {item.get('notes')}")
            
    lines.append("----------------------------------------")
    if order.get('order_notes'):
        lines.append(f"Notas Generales: {order.get('order_notes')}")
    lines.append("\n\n\n")
    
    return "\n".join(lines)

def send_to_network_printer(ip: str, port: int, text: str, timeout: float = 1.0) -> Tuple[bool, str]:
    """Envía texto con comandos de inicialización y corte ESC/POS por TCP/IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        
        esc_init = b'\x1b\x40'              # ESC @: Inicializar impresora
        esc_bold_on = b'\x1b\x45\x01'        # ESC E 1: Negrita
        esc_cut = b'\x1d\x56\x42\x00'        # GS V 66 0: Corte parcial de papel
        
        payload = esc_init + esc_bold_on + text.encode('latin-1', errors='replace') + esc_cut
        s.sendall(payload)
        s.close()
        return True, "Impreso correctamente"
    except Exception as e:
        return False, str(e)

def dispatch_order(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Función Principal de Despacho al Terminar y Confirmar la Llamada:
    1. Inyecta en SQL Server de Soft Restaurant y descuenta inventario.
    2. Imprime comandas separadas por estación de trabajo.
    3. Imprime la Comanda Adicional Especial de ALTA PRIORIDAD IA.
    """
    config = get_config()
    results = {
        "order_id": order.get("order_id", "001"),
        "sql_server_injection": None,
        "stations_printed": {},
        "priority_ticket_printed": None
    }
    
    # 1. Inyección en SQL Server (Soft Restaurant)
    if config.get("enable_sql_injection", True):
        success, msg = sql_bridge.inject_order_and_deduct_inventory(order)
        results["sql_server_injection"] = {"status": "ok" if success else "queued", "message": msg}

    # 2. Separar platillos por estación de trabajo
    items_by_station: Dict[str, List[Dict[str, Any]]] = {}
    for item in order.get('items', []):
        station = item.get('station')
        if not station:
            # Mapeo inteligente si no viene explícito
            name_lower = item.get('name', '').lower()
            if any(w in name_lower for w in ['sushi', 'rollo', 'nigiri', 'sashimi']):
                station = 'sushi_bar'
            elif any(w in name_lower for w in ['fettuccine', 'lasagna', 'lasaña', 'pita', 'panini']):
                station = 'italian_kitchen'
            elif any(w in name_lower for w in ['hamburguesa', 'alita', 'boneless', 'hot dog', 'papas']):
                station = 'snack_kitchen'
            elif any(w in name_lower for w in ['refresco', 'soda', 'calpico', 'té', 'agua', 'cerveza']):
                station = 'drinks_bar'
            else:
                station = 'hot_kitchen'
        
        if station not in items_by_station:
            items_by_station[station] = []
        items_by_station[station].append(item)

    # 3. Imprimir comanda por estación
    mode = config.get("mode", "file_simulation")
    printers_cfg = config.get("printers", {})

    print(f"\n🖨️ [DESPACHADOR RYU] Despachando Orden #{order.get('order_id', '001')} a {len(items_by_station)} estaciones...")
    for station, items in items_by_station.items():
        printer_info = printers_cfg.get(station, { 'name': station, 'ip': '127.0.0.1', 'port': 9100 })
        ticket_text = generate_station_ticket(printer_info.get('name', station), order, items)
        
        if mode == 'escpos_network' and config.get("enable_escpos_printing", True):
            success, msg = send_to_network_printer(printer_info['ip'], printer_info['port'], ticket_text)
            results["stations_printed"][station] = {'status': 'ok' if success else 'error', 'message': msg}
            print(f" -> Estación '{station}' ({printer_info['name']}): {msg}")
        else:
            print(f"\n--- [TICKET ESTACIÓN: {printer_info.get('name')}] ---")
            print(ticket_text)
            results["stations_printed"][station] = {'status': 'simulated'}

    # 4. Imprimir COMANDA ADICIONAL DE PRIORIDAD IA
    priority_settings = config.get("priority_alert_settings", {})
    if priority_settings.get("enabled", True):
        priority_ticket_text = generate_ai_priority_ticket(order)
        expediter_key = priority_settings.get("expediter_printer_key", "expediter")
        expediter_printer = printers_cfg.get(expediter_key, { 'name': 'Expedición Central', 'ip': '127.0.0.1', 'port': 9100 })

        destinations = [expediter_printer]
        if priority_settings.get("print_to_all_stations", False):
            for st in items_by_station.keys():
                p_info = printers_cfg.get(st)
                if p_info and p_info not in destinations:
                    destinations.append(p_info)

        priority_results = []
        for dest in destinations:
            if mode == 'escpos_network' and config.get("enable_escpos_printing", True):
                success, msg = send_to_network_printer(dest['ip'], dest['port'], priority_ticket_text)
                priority_results.append({'printer': dest['name'], 'status': 'ok' if success else 'error', 'message': msg})
                print(f" 🚨 [COMANDA PRIORIDAD IA]: Enviada a {dest['name']} ({dest['ip']}) -> {msg}")
            else:
                priority_results.append({'printer': dest['name'], 'status': 'simulated'})
                print(f"\n🚨 [VISTA PREVIA COMANDA PRIORIDAD IA -> {dest['name']}] 🚨")
                print(priority_ticket_text)

        results["priority_ticket_printed"] = priority_results

    return results


def get_pending_pos_orders() -> List[Dict[str, Any]]:
    """Recupera los pedidos pendientes de impresión e inyección en Soft Restaurant."""
    bridge = SoftRestaurantSQLBridge()
    orders = []
    try:
        with bridge.sqlite_queue:
            cur = bridge.sqlite_queue.cursor()
            cur.execute("""
                SELECT folio_ryu, payload_json, status, created_at 
                FROM pending_orders 
                WHERE status IN ('PENDING', 'QUEUED_OFFLINE')
                ORDER BY created_at ASC
            """)
            for row in cur.fetchall():
                try:
                    payload = json.loads(row[1])
                    payload["_queue_status"] = row[2]
                    payload["_queued_at"] = row[3]
                    orders.append(payload)
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error consultando pedidos pendientes: {e}")
    return orders


def mark_pos_order_acknowledged(folio: str, status: str = "INJECTED") -> bool:
    """Marca un pedido como inyectado/impreso en el POS local del restaurante."""
    bridge = SoftRestaurantSQLBridge()
    try:
        with bridge.sqlite_queue:
            bridge.sqlite_queue.execute("""
                UPDATE pending_orders 
                SET status = ? 
                WHERE folio_ryu = ?
            """, (status, folio))
        logger.info(f"✅ [POS Bridge]: Comanda {folio} marcada como {status}.")
        return True
    except Exception as e:
        logger.error(f"Error actualizando estado de comanda {folio}: {e}")
        return False


if __name__ == '__main__':
    sample = {
        "order_id": "RYU-IA-777",
        "customer_name": "Cliente Prueba",
        "customer_phone": "3385261250",
        "delivery_type": "domicilio",
        "address": "Calle Girasol #3, Colonia Cofradía",
        "zone_name": "Colonia Cofradía",
        "payment_method": "Efectivo",
        "payment_change_for": 500.0,
        "items_subtotal": 360.0,
        "shipping_fee": 15.0,
        "total_amount": 375.0,
        "items": [
            { "name": "Sushi Tocayo Roll", "quantity": 1, "price": 115.0, "station": "sushi_bar", "notes": "Sin ajonjolí" },
            { "name": "Lasagna Tradicional", "quantity": 1, "price": 150.0, "station": "italian_kitchen" },
            { "name": "Alitas BBQ", "quantity": 1, "price": 100.0, "station": "snack_kitchen" }
        ]
    }
    res = dispatch_order(sample)
    print("\nResultado del despacho:", json.dumps(res, indent=2))
