# -*- coding: utf-8 -*-
"""
======================================================================
RESTAURANTE RYU - M?QUINA DE ESTADOS FINITOS PARA PEDIDOS (ORDER FSM)
100% Open Source, Determinista y Thread-Safe
Evita alucinaciones del LLM en montos, direcciones y confirmaciones prematuras.
======================================================================
"""

import enum
from typing import List, Dict, Any, Optional, Tuple


class OrderState(enum.Enum):
    IDLE = "IDLE"                               # Saludo inicial, preguntas de men?
    BUILDING_ORDER = "BUILDING_ORDER"           # Agregando productos al carrito
    NEED_DELIVERY_TYPE = "NEED_DELIVERY_TYPE"   # Falta especificar si es domicilio o para recoger
    NEED_ADDRESS = "NEED_ADDRESS"               # Falta calle, n?mero o colonia (si es domicilio)
    NEED_PAYMENT = "NEED_PAYMENT"               # Falta especificar efectivo o tarjeta
    REVIEWING = "REVIEWING"                     # Todos los datos completos, esperando confirmaci?n del cliente
    CONFIRMED = "CONFIRMED"                     # Orden confirmada expl?citamente por el cliente
    CANCELLED = "CANCELLED"                     # Orden cancelada


class OrderItem:
    def __init__(self, name: str, quantity: int = 1, unit_price: float = 0.0, notes: str = "", station: str = ""):
        self.name = name.strip()
        self.quantity = max(1, int(quantity))
        self.unit_price = float(unit_price)
        self.notes = notes.strip()
        self.station = station.strip()

    @property
    def total_price(self) -> float:
        return self.quantity * self.unit_price

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "notes": self.notes,
            "station": self.station
        }


class OrderStateMachine:
    """
    M?quina de estados determinista para validar pedidos telef?nicos en Restaurante Ryu.
    """

    def __init__(self, customer_phone: str = "", customer_name: str = "Cliente"):
        self.customer_phone = customer_phone
        self.customer_name = customer_name
        self.items: List[OrderItem] = []
        self.delivery_type: Optional[str] = None  # "domicilio" o "sucursal"
        self.address: Optional[str] = None
        self.zone_name: Optional[str] = None
        self.shipping_fee: float = 0.0
        self.payment_method: Optional[str] = None  # "Efectivo" o "Tarjeta"
        self.payment_change_for: Optional[float] = None
        self.is_future_order: bool = False
        self.scheduled_time: Optional[str] = None
        self.state: OrderState = OrderState.IDLE
        self.confirmation_requested: bool = False

    def add_item(self, name: str, quantity: int = 1, unit_price: float = 0.0, notes: str = "", station: str = "") -> OrderItem:
        # Verificar si ya existe el producto con las mismas notas para sumar cantidad
        for item in self.items:
            if item.name.lower() == name.lower() and item.notes.lower() == notes.lower():
                item.quantity += quantity
                if unit_price > 0:
                    item.unit_price = unit_price
                self._update_state()
                return item

        new_item = OrderItem(name=name, quantity=quantity, unit_price=unit_price, notes=notes, station=station)
        self.items.append(new_item)
        self._update_state()
        return new_item

    def remove_item(self, name: str) -> bool:
        initial_len = len(self.items)
        self.items = [item for item in self.items if item.name.lower() != name.lower()]
        self._update_state()
        return len(self.items) < initial_len

    def clear_items(self):
        self.items = []
        self._update_state()

    def set_delivery_type(self, del_type: str):
        norm = del_type.lower().strip()
        if "domicilio" in norm or "envio" in norm or "entrega" in norm:
            self.delivery_type = "domicilio"
        elif "sucursal" in norm or "recoger" in norm or "llevar" in norm or "aqui" in norm or "pasar" in norm:
            self.delivery_type = "sucursal"
            self.shipping_fee = 0.0
            self.address = "Para recoger en sucursal Ryu"
        else:
            self.delivery_type = norm
        self._update_state()

    def set_address(self, address: str, zone_name: Optional[str] = None, shipping_fee: float = 0.0):
        self.address = address.strip()
        if zone_name:
            self.zone_name = zone_name.strip()
        if shipping_fee >= 0:
            self.shipping_fee = shipping_fee
        self.delivery_type = "domicilio"
        self._update_state()

    def set_payment(self, method: str, change_for: Optional[float] = None):
        norm = method.lower().strip()
        if "tarjeta" in norm or "terminal" in norm or "transferencia" in norm:
            self.payment_method = "Tarjeta"
            self.payment_change_for = None
        elif "efectivo" in norm or "cambio" in norm or "billete" in norm:
            self.payment_method = "Efectivo"
            if change_for:
                self.payment_change_for = float(change_for)
        else:
            self.payment_method = method
        self._update_state()

    def set_scheduled(self, is_future: bool, scheduled_time: Optional[str] = None):
        self.is_future_order = is_future
        self.scheduled_time = scheduled_time
        self._update_state()

    @property
    def items_subtotal(self) -> float:
        return sum(item.total_price for item in self.items)

    @property
    def total_amount(self) -> float:
        return self.items_subtotal + self.shipping_fee

    @property
    def missing_fields(self) -> List[str]:
        missing = []
        if not self.items:
            missing.append("productos")
        if not self.delivery_type:
            missing.append("tipo_entrega (domicilio o sucursal)")
        elif self.delivery_type == "domicilio" and (not self.address or len(self.address) < 4):
            missing.append("direccion de entrega")
        if not self.payment_method:
            missing.append("forma de pago (efectivo o tarjeta)")
        return missing

    @property
    def can_confirm(self) -> bool:
        return len(self.missing_fields) == 0 and len(self.items) > 0

    def _update_state(self):
        if self.state in [OrderState.CONFIRMED, OrderState.CANCELLED]:
            return
        if not self.items:
            self.state = OrderState.IDLE
        elif not self.delivery_type:
            self.state = OrderState.NEED_DELIVERY_TYPE
        elif self.delivery_type == "domicilio" and (not self.address or len(self.address) < 4):
            self.state = OrderState.NEED_ADDRESS
        elif not self.payment_method:
            self.state = OrderState.NEED_PAYMENT
        else:
            self.state = OrderState.REVIEWING

    def confirm_order(self) -> Tuple[bool, str]:
        """Confirma la orden solo si todos los campos obligatorios est?n satisfechos."""
        if not self.can_confirm:
            missing_str = ", ".join(self.missing_fields)
            return False, f"No se puede confirmar el pedido. Falta: {missing_str}"
        self.state = OrderState.CONFIRMED
        return True, "Pedido confirmado exitosamente."

    def cancel_order(self, reason: str = ""):
        self.state = OrderState.CANCELLED

    def generate_review_summary(self) -> str:
        """Genera el resumen determinista para que la IA lo lea al cliente antes de confirmar."""
        if not self.items:
            return "A?n no tienes platillos agregados a tu orden."

        items_str = ", ".join([f"{item.quantity} {item.name}" for item in self.items])
        deliv_str = f"a domicilio en {self.address}" if self.delivery_type == "domicilio" else "para recoger en sucursal"
        pay_str = f"pago con {self.payment_method}"
        if self.payment_change_for and self.payment_change_for > self.total_amount:
            pay_str += f" (cambio de ${self.payment_change_for:.0f})"

        sched_str = f" programado para {self.scheduled_time}" if self.is_future_order and self.scheduled_time else ""

        return (
            f"Tu orden es: {items_str}, {deliv_str}{sched_str}, "
            f"con un total de ${self.total_amount:.0f} pesos ({pay_str}). "
            f"?Todo est? correcto para prepararlo?"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_phone": self.customer_phone,
            "customer_name": self.customer_name,
            "state": self.state.value,
            "items": [i.to_dict() for i in self.items],
            "items_subtotal": self.items_subtotal,
            "shipping_fee": self.shipping_fee,
            "total_amount": self.total_amount,
            "delivery_type": self.delivery_type or "",
            "address": self.address or "",
            "zone_name": self.zone_name or "",
            "payment_method": self.payment_method or "",
            "payment_change_for": self.payment_change_for,
            "is_future_order": self.is_future_order,
            "scheduled_time": self.scheduled_time or "",
            "can_confirm": self.can_confirm,
            "missing_fields": self.missing_fields
        }
