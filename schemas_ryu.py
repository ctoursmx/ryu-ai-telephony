#!/usr/bin/env python3
"""
schemas_ryu.py
Modelos Pydantic formales para OpenAPI 3.1 y validación de interfaces REST del Restaurante Ryu.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# 1. AUTENTICACIÓN
# ----------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(..., description="Nombre de usuario del administrador", examples=["admin"])
    password: str = Field(..., description="Contraseña de acceso seguro", examples=["ryu_tequila_2026"])


class LoginResponse(BaseModel):
    status: str = Field("ok", description="Estado del inicio de sesión", examples=["ok"])
    token: str = Field(..., description="Token criptográfico HMAC-SHA256 para Authorization Bearer", examples=["admin:1791945003:512a06ebdd..."])
    username: str = Field("admin", description="Usuario autenticado", examples=["admin"])


class AuthCheckResponse(BaseModel):
    authenticated: bool = Field(..., description="Indica si la sesión actual es válida")
    username: Optional[str] = Field(None, description="Usuario identificado si la sesión es válida", examples=["admin"])


# ----------------------------------------------------------------------
# 2. CONTROL OPERACIONAL Y EXISTENCIAS
# ----------------------------------------------------------------------
class ToggleIngredientRequest(BaseModel):
    ingredient_id: str = Field(..., description="Identificador único del ingrediente en minúsculas", examples=["pulpo"])
    available: bool = Field(True, description="True para disponible, False para marcar como agotado", examples=[False])


class ToggleDishRequest(BaseModel):
    dish_id: str = Field(..., description="Identificador único del platillo del catálogo", examples=["jp_rol_01"])
    available: bool = Field(True, description="True para habilitado en cocina, False para deshabilitar", examples=[True])


class ToggleStoreRequest(BaseModel):
    is_open: bool = Field(..., description="Estado general de recepción de pedidos (True=Abierto, False=Cerrado)", examples=[True])


class SaveAnnouncementsRequest(BaseModel):
    average_prep_and_delivery_time: Optional[str] = Field(
        None,
        description="Tiempo estimado anunciado a clientes",
        examples=["40 a 55 minutos"])
    special_service_override: Optional[str] = Field(
        None,
        description="Aviso dinámico de cocina inyectado al agente de voz",
        examples=["Demora de 15 min por alta demanda en sushi bar"])


# ----------------------------------------------------------------------
# 3. ZONAS Y POLÍTICAS DE ENTREGA
# ----------------------------------------------------------------------
class SpecialDeliveryZoneModel(BaseModel):
    id: str = Field(..., description="ID canónico de la zona", examples=["zon_11"])
    name: str = Field(..., description="Nombre formal de la zona o poblado", examples=["Medineño"])
    fee: float = Field(..., description="Tarifa de envío oficial en MXN", examples=[100.0])
    enabled: bool = Field(True, description="Si la entrega a esta zona está habilitada", examples=[True])
    aliases: List[str] = Field(default_factory=list, description="Variantes fonéticas y alias reconocidos por la IA", examples=["el medineño", "medineno"])
    notes: Optional[str] = Field("", description="Notas de acceso o referencias de entrega", examples=["Carretera a San Martín"])


class UrbanDeliveryRulesModel(BaseModel):
    daytime_fee: float = Field(0.0, description="Costo de entrega diurno en Tequila Centro", examples=[0.0])
    daytime_schedule: str = Field("Antes de las 19:30 hrs (7:30 PM)", description="Horario de tarifa diurna")
    nighttime_fee: float = Field(15.0, description="Costo de entrega nocturno en Tequila Centro", examples=[15.0])
    nighttime_schedule: str = Field("A partir de las 19:30 hrs (7:30 PM)", description="Horario de tarifa nocturna")
    description: str = Field(..., description="Regla textual explicada")


class DeliverySettingsResponse(BaseModel):
    tequila_urban_zone: UrbanDeliveryRulesModel
    special_zones: List[SpecialDeliveryZoneModel]


# ----------------------------------------------------------------------
# 4. VOICE STUDIO (ESTUDIO DE GRABACIÓN)
# ----------------------------------------------------------------------
class VoiceStudioItemModel(BaseModel):
    id: str = Field(..., description="Identificador único del clip de audio", examples=["flow_saludo"])
    category: str = Field(..., description="Categoría (flow, japanese, snacks, italian, numbers)", examples=["flow"])
    sub_category: Optional[str] = Field("", description="Subcategoría interna del menú", examples=[""])
    title: str = Field(..., description="Título legible del elemento", examples=["Saludo Inicial de Bienvenida"])
    prompt_text: str = Field(..., description="Texto canónico a pronunciar frente al micrófono", examples=["¡Buenas tardes! Bienvenido a Restaurante Ryu..."])
    phonetic_tip: Optional[str] = Field("", description="Recomendación fonética o de entonación")
    status: str = Field("pending", description="Estado de grabación ('pending' o 'recorded')", examples=["pending"])
    duration_sec: float = Field(0.0, description="Duración del audio en segundos", examples=[7.4])
    audio_alaw: Optional[str] = Field(None, description="Ruta al archivo telefónico G.711 A-law 8kHz", examples=["/audio_clips/flow_saludo.alaw"])
    audio_wav: Optional[str] = Field(None, description="Ruta al archivo WAV 16kHz para navegador", examples=["/api/voice-studio/audio/flow_saludo"])
    updated_at: Optional[str] = Field(None, description="Timestamp ISO de la última grabación")


class VoiceStudioManifestResponse(BaseModel):
    version: str = Field("1.0.0", alias="_version")
    generated_at: str
    total_items: int = Field(..., description="Total de frases y platillos catalogados", examples=[233])
    recorded_items: int = Field(..., description="Total de elementos ya grabados", examples=[12])
    pending_items: int = Field(..., description="Total de elementos pendientes por grabar", examples=[221])
    completion_percent: float = Field(..., description="Porcentaje de avance completado", examples=[5.1])
    items: List[VoiceStudioItemModel]


class VoiceStudioUploadResponse(BaseModel):
    status: str = Field("ok", examples=["ok"])
    item_id: str = Field(..., examples=["dish_jp_rol_01"])
    duration_sec: float = Field(..., examples=[2.1])
    item: Optional[VoiceStudioItemModel] = None


class VoiceStudioPreviewRequest(BaseModel):
    item_ids: List[str] = Field(..., description="Lista de IDs de clips a concatenar en orden", examples=["flow_saludo", "dish_jp_rol_01", "flow_despedida_general"])


# ----------------------------------------------------------------------
# 5. POS BRIDGE Y COMANDAS
# ----------------------------------------------------------------------
class POSOrderAckResponse(BaseModel):
    status: str = Field("ok", examples=["ok"])
    order_id: str = Field(..., examples=["ryu_ord_20260913_001"])


class GenericStatusResponse(BaseModel):
    status: str = Field("ok", examples=["ok"])
    message: Optional[str] = Field(None, examples=["Operación realizada con éxito"])
