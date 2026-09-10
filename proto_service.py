"""
======================================================================
RESTAURANTE RYU - SERVICIO PROTOCOL BUFFERS (SERIALIZACIÓN DE ALTO RENDIMIENTO)
Manejo binario estricto de Comandas, Sesiones Telefónicas y Hechos KAG
======================================================================
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional

import proto.ryu_order_pb2 as order_pb
import proto.ryu_telephony_pb2 as tel_pb
import proto.ryu_kag_pb2 as kag_pb
from google.protobuf.json_format import MessageToDict, ParseDict

class ProtoService:
    """Servicio de serialización y deserialización binaria con Protocol Buffers."""

    @staticmethod
    def create_order_protobuf(data: Dict[str, Any]) -> order_pb.Order:
        """Convierte un diccionario de comanda en un mensaje Order Protobuf."""
        order = order_pb.Order()
        order.order_id = str(data.get("order_id", f"RYU-{int(datetime.now().timestamp())}"))
        order.session_id = str(data.get("session_id", ""))
        order.customer_phone = str(data.get("customer_phone", "Desconocido"))
        order.customer_name = str(data.get("customer_name", "Cliente"))
        order.created_at = str(data.get("created_at", datetime.now().isoformat()))
        order.is_future_order = bool(data.get("is_future_order", False))
        order.scheduled_time = str(data.get("scheduled_time", ""))
        order.raw_ticket_text = str(data.get("raw_ticket_text", ""))

        # Items
        items_subtotal = 0.0
        for item_data in data.get("items", []):
            item = order.items.add()
            item.item_id = str(item_data.get("item_id", item_data.get("name", "").lower().replace(" ", "_")))
            item.name = str(item_data.get("name", "Platillo"))
            item.unit_price = float(item_data.get("unit_price", item_data.get("price", 0.0)))
            item.quantity = int(item_data.get("quantity", 1))
            item.subtotal = item.unit_price * item.quantity
            items_subtotal += item.subtotal
            item.notes = str(item_data.get("notes", ""))
            item.is_combo_included = bool(item_data.get("is_combo_included", False))
            item.category = str(item_data.get("category", ""))
            for opt in item_data.get("options", []):
                item.options.append(str(opt))

        order.items_subtotal = float(data.get("items_subtotal", items_subtotal))
        order.shipping_fee = float(data.get("shipping_fee", 0.0))
        order.total_amount = float(data.get("total_amount", order.items_subtotal + order.shipping_fee))

        # Entrega
        deliv = data.get("delivery", {})
        deliv_type_str = str(deliv.get("type", data.get("delivery_type", ""))).upper()
        if "DOMICILIO" in deliv_type_str:
            order.delivery.type = order_pb.DeliveryType.DOMICILIO
        elif "SUCURSAL" in deliv_type_str or "RECOGER" in deliv_type_str or "LLEVAR" in deliv_type_str:
            order.delivery.type = order_pb.DeliveryType.SUCURSAL
        else:
            order.delivery.type = order_pb.DeliveryType.DELIVERY_UNSPECIFIED

        order.delivery.address = str(deliv.get("address", data.get("address", "")))
        order.delivery.references = str(deliv.get("references", data.get("references", "")))
        order.delivery.zone_name = str(deliv.get("zone_name", data.get("zone_name", "Tequila Urbano")))
        order.delivery.shipping_fee = order.shipping_fee
        order.delivery.is_night_rate_applied = bool(deliv.get("is_night_rate_applied", False))

        # Pago
        pay = data.get("payment", {})
        pay_method_str = str(pay.get("method", data.get("payment_method", "EFECTIVO"))).upper()
        if "TARJETA" in pay_method_str:
            order.payment.method = order_pb.PaymentMethod.TARJETA
        elif "TRANSFERENCIA" in pay_method_str:
            order.payment.method = order_pb.PaymentMethod.TRANSFERENCIA
        elif "EFECTIVO" in pay_method_str:
            order.payment.method = order_pb.PaymentMethod.EFECTIVO
        else:
            order.payment.method = order_pb.PaymentMethod.PAYMENT_UNSPECIFIED

        order.payment.paid_with_amount = float(pay.get("paid_with_amount", data.get("payment_change_for", 0.0) or 0.0))
        if order.payment.paid_with_amount > 0:
            order.payment.change_due = max(0.0, order.payment.paid_with_amount - order.total_amount)

        # Estado
        if order.is_future_order:
            order.status = order_pb.OrderStatus.PROGRAMADO_FUTURO
        else:
            order.status = order_pb.OrderStatus.PENDIENTE_PREPARACION

        # Hash criptográfico de auditoría matemática
        audit_payload = f"{order.order_id}:{order.total_amount}:{order.customer_phone}:{len(order.items)}"
        order.audit_hash = hashlib.sha256(audit_payload.encode()).hexdigest()

        return order

    @staticmethod
    def serialize_order_to_bytes(order_data: Dict[str, Any]) -> bytes:
        """Serializa una orden a bytes Protobuf listos para persistir en PostgreSQL BYTEA."""
        pb_order = ProtoService.create_order_protobuf(order_data)
        return pb_order.SerializeToString()

    @staticmethod
    def deserialize_order_from_bytes(raw_bytes: bytes) -> Dict[str, Any]:
        """Deserializa bytes binarios Protobuf a un diccionario de Python."""
        order = order_pb.Order()
        order.ParseFromString(raw_bytes)
        return MessageToDict(order, preserving_proto_field_name=True)

    @staticmethod
    def create_learning_event_protobuf(data: Dict[str, Any]) -> kag_pb.LearningFeedbackEvent:
        """Crea un mensaje de evento de autoaprendizaje KAG."""
        event = kag_pb.LearningFeedbackEvent()
        event.event_id = str(data.get("event_id", f"LRN-{int(datetime.now().timestamp())}"))
        event.session_id = str(data.get("session_id", ""))
        event.customer_phone = str(data.get("customer_phone", ""))
        event.original_text = str(data.get("original_text", ""))
        event.corrected_intent = str(data.get("corrected_intent", ""))
        event.learned_alias = str(data.get("learned_alias", ""))
        event.target_canonical_entity = str(data.get("target_canonical_entity", ""))
        event.notes = str(data.get("notes", ""))
        event.created_at = str(data.get("created_at", datetime.now().isoformat()))
        event.applied_to_graph = bool(data.get("applied_to_graph", False))

        type_str = str(data.get("entity_type", "DISH")).upper()
        if "DISH" in type_str:
            event.entity_type = kag_pb.EntityType.DISH
        elif "ZONE" in type_str:
            event.entity_type = kag_pb.EntityType.ZONE
        elif "INGREDIENT" in type_str:
            event.entity_type = kag_pb.EntityType.INGREDIENT
        elif "CATEGORY" in type_str:
            event.entity_type = kag_pb.EntityType.CATEGORY
        else:
            event.entity_type = kag_pb.EntityType.ENTITY_UNSPECIFIED

        return event

    @staticmethod
    def serialize_learning_event_to_bytes(event_data: Dict[str, Any]) -> bytes:
        pb_event = ProtoService.create_learning_event_protobuf(event_data)
        return pb_event.SerializeToString()

    @staticmethod
    def deserialize_learning_event_from_bytes(raw_bytes: bytes) -> Dict[str, Any]:
        event = kag_pb.LearningFeedbackEvent()
        event.ParseFromString(raw_bytes)
        return MessageToDict(event, preserving_proto_field_name=True)
