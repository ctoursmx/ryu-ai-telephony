/**
 * Servicio de Validación y Gestión de Pedidos - Restaurante Ryu
 * Validador de menús por horario y formateador de comandas para Telegram / Soft Restaurant
 */

const fs = require('fs');
const path = require('path');

const menuData = JSON.parse(fs.readFileSync(path.join(__dirname, 'menu_ryu.json'), 'utf8'));

/**
 * Retorna las categorías y platillos disponibles según la fecha/hora actual o proporcionada.
 * @param {Date} dateObj
 */
function getActiveMenus(dateObj = new Date()) {
  const daysOfWeek = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
  const currentDay = daysOfWeek[dateObj.getDay()];
  const currentHour = dateObj.getHours() + dateObj.getMinutes() / 60;

  const available = {
    japanese: false,
    italian: false,
    snacks: false,
    active_categories: []
  };

  // Regla 1: Menú Japonés (Todos los días, 1:00 PM - 11:00 PM -> 13:00 a 23:00)
  if (currentHour >= 13 && currentHour <= 23) {
    available.japanese = true;
    available.active_categories.push('japanese');
  }

  // Regla 2: Comida Italiana (Viernes, Sábado, Domingo de 1:00 PM a 7:00 PM -> 13:00 a 19:00)
  const isWeekendItalian = ['friday', 'saturday', 'sunday'].includes(currentDay);
  if (isWeekendItalian && (currentHour >= 13 && currentHour < 19)) {
    available.italian = true;
    available.active_categories.push('italian');
  }

  // Regla 3: Snacks (Todos los días de 7:00 PM a 11:00 PM -> 19:00 a 23:00)
  if (currentHour >= 19 && currentHour <= 23) {
    available.snacks = true;
    available.active_categories.push('snacks');
  }

  return {
    day: currentDay,
    time: `${dateObj.getHours().toString().padStart(2, '0')}:${dateObj.getMinutes().toString().padStart(2, '0')}`,
    is_open: available.japanese || available.italian || available.snacks,
    available_menus: available
  };
}

/**
 * Genera el formato de comanda optimizado para el bot de Telegram
 * @param {Object} order
 */
function formatTelegramTicket(order) {
  const dateStr = new Date().toLocaleString('es-MX', { timeZone: 'America/Mexico_City' });
  const typeEmoji = order.delivery_type === 'domicilio' ? '🛵 A DOMICILIO' : '🥡 PARA LLEVAR (RECOGER)';

  let ticket = `🍣 *NUEVO PEDIDO - RESTAURANTE RYU* 🍱\n`;
  ticket += `━━━━━━━━━━━━━━━━━━━━━\n`;
  ticket += `📅 *Fecha:* ${dateStr}\n`;
  ticket += `👤 *Cliente:* ${order.customer_name}\n`;
  ticket += `📱 *Teléfono:* ${order.customer_phone}\n`;
  ticket += `📍 *Modalidad:* ${typeEmoji}\n`;

  if (order.delivery_type === 'domicilio') {
    ticket += `🏠 *Dirección:* ${order.address}\n`;
    if (order.references) ticket += `📌 *Referencias:* ${order.references}\n`;
  }

  ticket += `━━━━━━━━━━━━━━━━━━━━━\n`;
  ticket += `📝 *DETALLE DE PLATILLOS:*\n`;

  let total = 0;
  order.items.forEach((item, index) => {
    const itemTotal = item.price * item.quantity;
    total += itemTotal;
    ticket += `  ${index + 1}. *${item.quantity}x* ${item.name} ($${item.price} c/u) = $${itemTotal}\n`;
    if (item.options && item.options.length > 0) {
      ticket += `     ↳ _Opciones: ${item.options.join(', ')}_\n`;
    }
    if (item.notes) {
      ticket += `     ↳ _Nota: ${item.notes}_\n`;
    }
  });

  ticket += `━━━━━━━━━━━━━━━━━━━━━\n`;
  ticket += `💵 *TOTAL A COBRAR:* $${total} MXN\n`;
  ticket += `💳 *Método de Pago:* ${order.payment_method || 'Efectivo'}\n`;
  if (order.payment_change_for) {
    ticket += `💰 *Paga con:* $${order.payment_change_for} (Cambio: $${order.payment_change_for - total})\n`;
  }
  ticket += `━━━━━━━━━━━━━━━━━━━━━\n`;
  ticket += `⏳ *Estado:* Pendiente de Preparación`;

  return ticket;
}

module.exports = {
  menuData,
  getActiveMenus,
  formatTelegramTicket
};
