import json
import os
import sys
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MENU_FILE = os.path.join(CURRENT_DIR, 'menu_ryu.json')

def load_menu():
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_active_menus(dt=None):
    if dt is None:
        dt = datetime.now()
    
    # 0 = Monday, 6 = Sunday
    weekday = dt.weekday()
    hour_decimal = dt.hour + dt.minute / 60.0
    
    day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    current_day = day_names[weekday]
    
    available = {
        'japanese': False,
        'italian': False,
        'snacks': False
    }
    
    # 1. Comida Japonesa: Todos los días 1:00 PM (13:00) a 11:00 PM (23:00)
    if 13.0 <= hour_decimal <= 23.0:
        available['japanese'] = True
        
    # 2. Comida Italiana: Viernes, Sábado y Domingo (4, 5, 6) de 1:00 PM (13:00) a 7:00 PM (19:00)
    if weekday in [4, 5, 6] and (13.0 <= hour_decimal < 19.0):
        available['italian'] = True
        
    # 3. Snacks: Todos los días de 7:00 PM (19:00) a 11:00 PM (23:00)
    if 19.0 <= hour_decimal <= 23.0:
        available['snacks'] = True
        
    return {
        'day': current_day,
        'time': dt.strftime('%H:%M'),
        'available_menus': available,
        'is_open': any(available.values())
    }

def format_telegram_ticket(order):
    """
    Formatea un pedido en Markdown para ser enviado al bot de Telegram del restaurante.
    """
    date_str = datetime.now().strftime('%d/%m/%Y %I:%M %p')
    deliv_type = '🛵 A DOMICILIO' if order.get('delivery_type') == 'domicilio' else '🥡 PARA LLEVAR (RECOGER)'
    
    ticket = [
        "🍣 *NUEVO PEDIDO - RESTAURANTE RYU* 🍱",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"📅 *Fecha:* {date_str}",
        f"👤 *Cliente:* {order.get('customer_name', 'No especificado')}",
        f"📱 *Teléfono:* {order.get('customer_phone', 'No especificado')}",
        f"📍 *Modalidad:* {deliv_type}"
    ]
    
    if order.get('delivery_type') == 'domicilio':
        ticket.append(f"🏠 *Dirección:* {order.get('address', 'Pendiente')}")
        if order.get('references'):
            ticket.append(f"📌 *Referencias:* {order.get('references')}")
            
    ticket.append("━━━━━━━━━━━━━━━━━━━━━")
    ticket.append("📝 *DETALLE DE PLATILLOS:*")
    
    total = 0.0
    for idx, item in enumerate(order.get('items', []), 1):
        price = item.get('price', 0)
        qty = item.get('quantity', 1)
        subtotal = price * qty
        total += subtotal
        
        ticket.append(f"  {idx}. *{qty}x* {item.get('name')} (${price:.2f} c/u) = ${subtotal:.2f}")
        if item.get('options'):
            ticket.append(f"     ↳ _Opciones: {', '.join(item.get('options'))}_")
        if item.get('notes'):
            ticket.append(f"     ↳ _Nota: {item.get('notes')}_")
            
    ticket.append("━━━━━━━━━━━━━━━━━━━━━")
    ticket.append(f"💵 *TOTAL A COBRAR:* ${total:.2f} MXN")
    ticket.append(f"💳 *Método de Pago:* {order.get('payment_method', 'Efectivo')}")
    
    if order.get('payment_change_for'):
        change = float(order.get('payment_change_for')) - total
        ticket.append(f"💰 *Paga con:* ${order.get('payment_change_for')} (Cambio: ${change:.2f})")
        
    ticket.append("━━━━━━━━━━━━━━━━━━━━━")
    ticket.append("⏳ *Estado:* Pendiente de Preparación")
    
    return "\n".join(ticket)

if __name__ == '__main__':
    status = get_active_menus()
    print("Estado actual del restaurante:", json.dumps(status, indent=2))
