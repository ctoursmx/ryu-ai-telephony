# -*- coding: utf-8 -*-
"""
Puente de Integración Soft Restaurant / Impresión Directa ESC-POS para Restaurante Ryu
Permite:
1. Escuchar pedidos nuevos vía Webhook / Polling.
2. Imprimir comandas separadas automáticamente por estación de cocina:
   - Barra Sushi (sushi_bar)
   - Cocina Caliente (hot_kitchen)
   - Cocina Italiana (italian_kitchen)
   - Cocina Snacks (snack_kitchen)
   - Barra de Bebidas / Postres (drinks_bar / dessert_bar)
3. Opcional: Insertar pedidos en la base de datos SQL Server de Soft Restaurant.
"""

import json
import os
import socket
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'printer_config.json')

DEFAULT_CONFIG = {
    "mode": "escpos_network",  # Opciones: 'escpos_network', 'soft_restaurant_sql', 'file_simulation'
    "soft_restaurant_db": {
        "server": "localhost\\SOFTRESTAURANT",
        "database": "SOFTRESTAURANT10",
        "user": "sa",
        "password": "your_password"
    },
    "printers": {
        "sushi_bar": { "ip": "192.168.1.101", "port": 9100, "name": "Impresora Sushi" },
        "hot_kitchen": { "ip": "192.168.1.102", "port": 9100, "name": "Impresora Cocina Caliente" },
        "italian_kitchen": { "ip": "192.168.1.103", "port": 9100, "name": "Impresora Italiana" },
        "snack_kitchen": { "ip": "192.168.1.104", "port": 9100, "name": "Impresora Snacks" },
        "drinks_bar": { "ip": "192.168.1.105", "port": 9100, "name": "Impresora Barra Bebidas" }
    }
}

def get_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_station_ticket(station_name, order, station_items):
    """
    Genera el texto de la comanda específico para la estación de trabajo.
    """
    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    deliv_type = 'A DOMICILIO' if order.get('delivery_type') == 'domicilio' else 'PARA LLEVAR'
    
    lines = [
        "========================================",
        f"       COMANDA: {station_name.upper()}",
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
    lines.append("\n\n\n")  # Espacio para corte
    
    return "\n".join(lines)

def send_to_network_printer(ip, port, text):
    """
    Envía texto formateado con comandos ESC/POS básicos a una impresora térmica por TCP/IP.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, port))
        
        # Comando ESC/POS inicialización: ESC @ (\x1b\x40)
        # Corte de papel: GS V 66 0 (\x1d\x56\x42\x00)
        esc_init = b'\x1b\x40'
        esc_cut = b'\x1d\x56\x42\x00'
        
        payload = esc_init + text.encode('latin-1', errors='replace') + esc_cut
        s.sendall(payload)
        s.close()
        return True, "Impreso correctamente"
    except Exception as e:
        return False, str(e)

def dispatch_order(order):
    """
    Distribuye los platillos de una orden a sus respectivas impresoras por estación.
    """
    config = get_config()
    items_by_station = {}
    
    for item in order.get('items', []):
        station = item.get('station', 'hot_kitchen')
        if station not in items_by_station:
            items_by_station[station] = []
        items_by_station[station].append(item)
        
    results = {}
    print(f"\n[DESPACHADOR] Procesando Orden #{order.get('order_id', '001')} para {len(items_by_station)} estaciones...")
    
    for station, items in items_by_station.items():
        printer_info = config.get('printers', {}).get(station, { 'name': station, 'ip': '127.0.0.1', 'port': 9100 })
        ticket_text = generate_station_ticket(printer_info.get('name', station), order, items)
        
        if config.get('mode') == 'escpos_network':
            success, msg = send_to_network_printer(printer_info['ip'], printer_info['port'], ticket_text)
            results[station] = {'status': 'ok' if success else 'error', 'message': msg}
            print(f" -> Estación '{station}' ({printer_info['name']}): {msg}")
        else:
            # Modo simulación en archivo / consola
            print(f"\n--- [VISTA PREVIA TICKET: {printer_info.get('name')}] ---")
            print(ticket_text)
            results[station] = {'status': 'simulated'}
            
    return results

if __name__ == '__main__':
    # Prueba con orden de ejemplo multiarea (Sushi + Cocina Caliente + Bebida)
    sample_order = {
        "order_id": "RYU-101",
        "customer_name": "Carlos Gomez",
        "customer_phone": "3741234567",
        "delivery_type": "domicilio",
        "address": "P.º del Centenario #10, Tequila",
        "items": [
            { "name": "Sushi Tocayo Roll", "quantity": 1, "price": 115, "station": "sushi_bar", "notes": "Sin ajonjolí" },
            { "name": "Ramen de Cerdo", "quantity": 1, "price": 190, "station": "hot_kitchen", "options": ["Cerdo"], "notes": "Huevo bien cocido" },
            { "name": "Calpico 1 Litro", "quantity": 1, "price": 40, "station": "drinks_bar" }
        ],
        "order_notes": "Tocar el timbre blanco"
    }
    
    dispatch_order(sample_order)
