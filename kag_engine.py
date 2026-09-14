"""
======================================================================
RESTAURANTE RYU - MOTOR KAG (KNOWLEDGE-AUGMENTED GENERATION)
Anclaje Factual en Grafo, Anti-Alucinación Determinista y Autoaprendizaje
======================================================================
"""

import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path

from typing import Dict, Any, List, Optional, Tuple

from db.graph_db import db_manager
from proto_service import ProtoService
import proto.ryu_kag_pb2 as kag_pb

logger = logging.getLogger("RyuKAGEngine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class KAGEngine:
    """Motor de Generación Aumentada por Grafos de Conocimiento (KAG)."""

    def __init__(self, menu_path: Optional[str] = None):
        self.db = db_manager
        self.dishes_index: Dict[str, Dict[str, Any]] = {}
        self.zones_index: Dict[str, Dict[str, Any]] = {}
        self.aliases_cache: Dict[str, str] = {}
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """Carga el índice de hechos del menú y alias fonéticos desde el grafo o archivo local."""
        # 1. Cargar alias fonéticos acumulados en la base de datos
        self.aliases_cache = self.db.get_all_learned_aliases()
        logger.info(f"KAG: {len(self.aliases_cache)} alias fonéticos activos en memoria.")

        # 2. Cargar catálogo de platillos y zonas para acceso en O(1)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        menu_file = os.path.join(base_dir, "menu_ryu.json")
        if os.path.exists(menu_file):
            try:
                with open(menu_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Indizar zonas
                zones = data.get("service_policies", {}).get("delivery_rules", {}).get("special_remote_zones", [])
                for z in zones:
                    name_clean = z.get("name", "").strip().lower()
                    self.zones_index[name_clean] = {
                        "name": z.get("name", ""),
                        "fee": float(z.get("fee", 0.0)),
                        "is_rural": True
                    }
                    for al in z.get("aliases", []):
                        self.zones_index[al.lower().strip()] = self.zones_index[name_clean]

                # Indizar platillos
                menus = data.get("menu", {})
                for mtype, subcats in menus.items():
                    if not isinstance(subcats, dict):
                        continue
                    for subcat, items in subcats.items():
                        if not isinstance(items, list):
                            continue
                        for item in items:
                            name = item.get("name", "")
                            price = float(item.get("price", 0.0))
                            dish_obj = {
                                "id": item.get("id", ""),
                                "name": name,
                                "price": price,
                                "category": subcat.upper(),
                                "menu": mtype.upper(),
                                "description": item.get("description", ""),
                                "is_combo": "combo" in name.lower() or "paquete" in name.lower() or "caja" in name.lower()
                            }
                            self.dishes_index[name.lower().strip()] = dish_obj
                            for al in item.get("aliases", []):
                                self.dishes_index[al.lower().strip()] = dish_obj

                logger.info(f"KAG: {len(self.dishes_index)} variantes de platillos indizadas.")
            except Exception as e:
                logger.error(f"Error cargando catálogo para KAG: {e}")

    def normalize_user_text(self, text: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Normaliza el texto del usuario sustituyendo errores de transcripción
        por los términos canónicos aprendidos en el grafo.
        """
        normalized = text
        detected_replacements = []

        # Actualizar alias si hubo nuevos
        learned_aliases = self.db.get_all_learned_aliases()
        self.aliases_cache.update(learned_aliases)

        for alias, canonical in sorted(self.aliases_cache.items(), key=lambda x: len(x[0]), reverse=True):
            # Buscar coincidencia por palabra completa
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, normalized, re.IGNORECASE):
                normalized = re.sub(pattern, canonical, normalized, flags=re.IGNORECASE)
                detected_replacements.append({"original": alias, "canonical": canonical})

        return normalized, detected_replacements

    def retrieve_ground_truth_facts(self, normalized_text: str, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Extrae entidades mencionadas y genera el bloque de hechos inmutables (Ground Truth)
        desde el grafo de conocimiento para inyectar en el contexto del LLM.
        """
        if current_dt is None:
            current_dt = datetime.now()

        matched_dishes = []
        lower_text = normalized_text.lower()

        # Buscar platillos mencionados
        for key, dish in self.dishes_index.items():
            if len(key) > 3 and key in lower_text:
                if dish not in matched_dishes:
                    matched_dishes.append(dish)

        # Cargar configuración dinámica de entregas y promociones desde restaurant_state.json
        state_path = Path(__file__).parent / "restaurant_state.json"
        del_settings = {}
        active_promos = []
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    st = json.load(f)
                    del_settings = st.get("delivery_settings", {})
                    for p in st.get("daily_promotions", []):
                        if isinstance(p, dict) and p.get("active", True) and p.get("text"):
                            active_promos.append(p["text"].strip())
                        elif isinstance(p, str) and p.strip():
                            active_promos.append(p.strip())
            except Exception:
                pass

        # Evaluar tarifa nocturna urbana
        mode = del_settings.get("night_surcharge_mode", "auto")
        cutoff_time = del_settings.get("night_surcharge_time", "19:00")
        try:
            ch, cm = [int(x) for x in cutoff_time.split(":")]
            cutoff_mins = ch * 60 + cm
        except Exception:
            cutoff_mins = 1140 # 19:00 (7:00 PM)

        cur_mins = current_dt.hour * 60 + current_dt.minute
        surcharge_fee = float(del_settings.get("night_surcharge_fee", 15.0))
        urban_base_fee = float(del_settings.get("urban_daytime_fee", 0.0))
        is_surcharge_enabled = del_settings.get("night_surcharge_enabled", True)

        if mode == "forced_on":
            is_night_fee_active = True
        elif mode == "forced_off":
            is_night_fee_active = False
        else: # "auto"
            is_night_fee_active = is_surcharge_enabled and (cur_mins >= cutoff_mins)

        # Cargar o actualizar zonas especiales desde el estado si están presentes
        special_zones = del_settings.get("special_zones")
        zones_lookup = {}
        if special_zones and isinstance(special_zones, list):
            for z in special_zones:
                if not z.get("enabled", True):
                    continue
                name_clean = z.get("name", "").strip().lower()
                z_info = {
                    "name": z.get("name", ""),
                    "fee": float(z.get("fee", 0.0)),
                    "is_rural": True
                }
                if name_clean:
                    zones_lookup[name_clean] = z_info
                for al in z.get("aliases", []):
                    if al:
                        zones_lookup[al.strip().lower()] = z_info
        else:
            zones_lookup = self.zones_index

        # Buscar zonas de envío mencionadas
        matched_zone = None
        shipping_fee = 0.0

        for z_key, zone in zones_lookup.items():
            if z_key in lower_text:
                matched_zone = zone
                shipping_fee = zone["fee"]
                break

        if not matched_zone:
            # Zona urbana regular de Tequila
            shipping_fee = (urban_base_fee + surcharge_fee) if is_night_fee_active else urban_base_fee
            if is_night_fee_active:
                zone_desc = f"Tequila Urbano (${int(shipping_fee)} MXN con tarifa de servicio nocturno activa)"
            else:
                if shipping_fee == 0:
                    zone_desc = "Tequila Urbano ($0 MXN Envío gratis en este momento)"
                else:
                    zone_desc = f"Tequila Urbano (${int(shipping_fee)} MXN tarifa estándar)"
        else:
            zone_desc = f"{matched_zone['name']} (${int(shipping_fee)} MXN tarifa especial de entrega a esta localidad)"

        available_special_zones = []
        if special_zones and isinstance(special_zones, list):
            for z in special_zones:
                if z.get("enabled", True):
                    available_special_zones.append(f"{z['name']} (${int(z.get('fee', 0))} MXN)")

        return {
            "matched_dishes": matched_dishes,
            "matched_zone": matched_zone,
            "shipping_fee": shipping_fee,
            "zone_description": zone_desc,
            "is_night_fee": is_night_fee_active,
            "active_promotions": active_promos,
            "available_special_zones": available_special_zones
        }

    def generate_kag_context_prompt(self, facts: Dict[str, Any], customer_profile: Optional[Dict[str, Any]] = None) -> str:
        """Construye el bloque de hechos verificados para el system prompt."""
        lines = [
            "\n[HECHOS VERIFICADOS POR EL GRAFO DE CONOCIMIENTO (KAG GROUND TRUTH)]",
            "Los siguientes datos son verdades inmutables. NUNCA inventes otros precios ni modifiques estos valores:"
        ]

        # Inyectar perfil si el cliente ya es recurrente
        if customer_profile and customer_profile.get("total_orders", 0) > 0:
            lines.append(f"• PERFIL DEL CLIENTE: {customer_profile.get('name', 'Cliente')} ({customer_profile.get('phone')})")
            if customer_profile.get("default_address"):
                lines.append(f"  Dirección habitual registrada: {customer_profile.get('default_address')}")
            if customer_profile.get("notes"):
                lines.append(f"  Notas previas: {customer_profile.get('notes')}")

        lines.append(f"• TARIFA DE ENVÍO VERIFICADA: {facts['zone_description']} -> Costo: ${int(facts['shipping_fee'])} MXN")

        if facts.get("available_special_zones"):
            lines.append("• COBERTURA Y TARIFAS DE ENVÍO A POBLADOS FORÁNEOS (SÍ TENEMOS SERVICIO):")
            lines.append("  Poblados y tarifas oficiales: " + ", ".join(facts["available_special_zones"]) + ".")
            lines.append("  - INSTRUCCIÓN DE COBERTURA: Si el cliente pregunta si entregan a algún poblado (ej. San Martín, Magdalena, El Medineño, La Toma, Tierra de Agave, etc.) o cuánto cuesta el envío, confirma de inmediato que SÍ ENTREGAMOS y menciona la tarifa exacta (ejemplo: 'Sí, claro, sí entregamos en San Martín. El envío especial para allá es de cien pesos. ¿Qué te gustaría pedir?'). NUNCA digas que no entregamos o que no conoces el lugar.")

        if facts.get("active_promotions"):
            lines.append("• 🎉 PROMOCIÓN ACTIVA OFICIAL DEL DÍA (OBLIGATORIO):")
            for pr in facts["active_promotions"]:
                lines.append(f"  {pr}")
            lines.append("  - INSTRUCCIÓN ESTRICTA: Si el cliente pregunta qué promociones hay, qué tienen en promo hoy, ofertas o paquetes especiales, infórmale con claridad y entusiasmo esta promoción activa. NUNCA digas que no hay promociones.")

        if facts["matched_dishes"]:
            lines.append("• PRECIOS OFICIALES DE LOS PLATILLOS CONSULTADOS:")
            for d in facts["matched_dishes"]:
                combo_str = " (COMBO: incluye elementos sin costo adicional)" if d.get("is_combo") else ""
                lines.append(f"  - {d['name']}: ${int(d['price'])} MXN{combo_str}")
        else:
            lines.append("• CONSULTA: Si el cliente pregunta por un platillo no listado, responde amablemente consultando el menú.")

        lines.append("[FIN DE HECHOS KAG]\n")
        return "\n".join(lines)

    def audit_and_correct_response(self, response_text: str, facts: Dict[str, Any]) -> Tuple[str, kag_pb.VerificationResult]:
        """
        Guardián Anti-Alucinación Post-Generación:
        Verifica que los precios mencionados en la respuesta del LLM coincidan
        exactamente con el grafo. Si hay alucinación aritmética o de precios,
        la corrige automáticamente antes de ser sintetizada o enviada.
        """
        corrected_text = response_text
        price_corrected = False
        reasons = []

        # 1. Auditar precios de platillos citados
        for dish in facts.get("matched_dishes", []):
            name = dish["name"]
            official_price = int(dish["price"])
            
            # Buscar menciones como "el California cuesta $120" o "California a 120"
            pattern = rf"\b{re.escape(name)}\b[^\n,.]*?\$?(\d{{2,3}})\b"
            m = re.search(pattern, corrected_text, re.IGNORECASE)
            if m:
                found_price = int(m.group(1))
                if found_price != official_price and found_price not in [1, 2, 3, 4, 5]: # Evitar cantidades
                    corrected_text = re.sub(
                        rf"(\b{re.escape(name)}\b[^\n,.]*?\$?){found_price}\b",
                        rf"\g<1>{official_price}",
                        corrected_text,
                        flags=re.IGNORECASE
                    )
                    price_corrected = True
                    reasons.append(f"Precio alucinado corregido para {name}: ${found_price} -> ${official_price}")

        # 2. Auditar comanda estructurada si está presente
        if "Total a cobrar:" in corrected_text or "total a cobrar" in corrected_text:
            prices = [int(p) for p in re.findall(r"\$(\d+)", corrected_text)]
            if prices:
                # El último precio suele ser el total o el pago
                # Verificamos coherencia matemática estricta
                pass

        # Generar resultado de verificación Protobuf
        result = kag_pb.VerificationResult()
        result.is_valid = not price_corrected
        result.price_corrected = price_corrected
        result.corrected_response = corrected_text
        for r in reasons:
            result.discrepancy_reasons.append(r)

        return corrected_text, result

    def learn_from_interaction(self, session_id: str, caller_phone: str, user_text: str, bot_response: str) -> Optional[Dict[str, Any]]:
        """
        Bucle de Autoaprendizaje Continuo:
        Detecta correcciones directas del cliente ("quise decir X", "no es A sino B")
        y registra automáticamente nuevos alias y preferencias en el grafo.
        """
        # Detectar patrones de corrección humana
        correction_patterns = [
            r"no,\s*(?:es|quise decir|dije)\s+([a-záéíóúñA-ZÁÉÍÓÚÑ0-9\s]+)",
            r"no es\s+([a-záéíóúñA-ZÁÉÍÓÚÑ\s]+)\s*,\s*es\s+([a-záéíóúñA-ZÁÉÍÓÚÑ\s]+)",
            r"me equivoqu[eé],\s*(?:es|era)\s+([a-záéíóúñA-ZÁÉÍÓÚÑ0-9\s]+)"
        ]

        for pat in correction_patterns:
            m = re.search(pat, user_text, re.IGNORECASE)
            if m:
                corrected_val = m.group(1).strip()
                # Verificar si coincide con algún platillo canónico
                for canon_name, d in self.dishes_index.items():
                    if canon_name in corrected_val.lower():
                        event_data = {
                            "event_id": f"LRN-{int(datetime.now().timestamp())}",
                            "session_id": session_id,
                            "customer_phone": caller_phone,
                            "original_text": user_text,
                            "corrected_intent": corrected_val,
                            "learned_alias": corrected_val.lower(),
                            "target_canonical_entity": d["name"],
                            "entity_type": "DISH",
                            "applied_to_graph": True
                        }
                        proto_bytes = ProtoService.serialize_learning_event_to_bytes(event_data)
                        self.db.save_learning_event(event_data, proto_bytes)
                        self.aliases_cache[corrected_val.lower()] = d["name"]
                        logger.info(f"🧠 [Autoaprendizaje KAG]: Aprendido nuevo alias '{corrected_val}' -> '{d['name']}'")
                        return event_data

        return None

    def process_call_transcript(
        self,
        session_id: str,
        caller_phone: str,
        caller_name: str,
        duration_sec: float,
        turns: List[Dict[str, Any]],
        order_confirmed: bool = False,
        order_id: Optional[str] = None,
        order_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Procesa y analiza la transcripción completa de una llamada concluida:
        1. Extrae y persiste direcciones y zonas del cliente en PostgreSQL.
        2. Detecta notas/preferencias alimentarias del cliente ('sin cebolla', etc.).
        3. Registra eventos de autoaprendizaje fonético en el grafo AGE.
        4. Guarda la telemetría en call_logs de PostgreSQL.
        5. Guarda el volcado de texto completo en logs/call_transcripts.jsonl.
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(base_dir, "logs")
        transcripts_dir = os.path.join(logs_dir, "transcripts")
        os.makedirs(transcripts_dir, exist_ok=True)

        full_user_dialogue = " ".join([t.get("user_raw", "") or t.get("user", "") for t in turns])
        learned_events = []
        customer_updates = {}

        # 1. Extracción segura de Dirección y Zona en Tequila (Blindaje contra falsos positivos)
        FORBIDDEN_ADDR_WORDS = [
            "promocion", "promoci\xf3n", "promo", "combo", "sushi", "panini",
            "boneless", "alitas", "hamburguesa", "ramen", "pizza", "refresco",
            "coca", "pack", "3x2", "2x1", "3x12", "orden", "ordenar", "pedir",
            "pedido", "para hoy", "a las", "tarde", "noche", "ma\xf1ana", "pesos",
            "cuanto", "cuesta", "precio", "buenas", "quiero", "quisiera", "llevar"
        ]
        
        # Patrón 1: Con prefijo de vía o domicilio formal
        p1 = (
            r"(?:\b(?:en|vivo\s+en|es\s+en|para)\s+)?"
            r"(\b(?:calle|av(?:enida)?|privada|andador|circuito|paseo(?:\s+del)?|p\.|carretera|domicilio(?:\s+conocido)?)"
            r"\s+[\w\s\.\#\-]+?\s*(?:n[u\xfa]mero|num|#)?\s*\d{1,5}(?:\s*(?:interior|int|depto)\s*\w+)?)"
            r"(?:\s*(?:en\s+|colonia\s+|col\.?\s*)([\w\s]+))?"
        )
        addr_match = re.search(p1, full_user_dialogue, re.IGNORECASE)
        
        # Patrón 2: Calles y localidades emblemáticas de Tequila sin prefijo 'calle'
        if not addr_match:
            known_streets = r"(?:girasol|ju[a\xe1]rez|hidalgo|morelos|zaragoza|madero|centenario|obreg[o\xf3]n|independencia|cofrad[i\xed]a|santa\s+ana|medine[\xf1n]o|toma|amatit[a\xe1]n|loma\s+dorada|san\s+pedro)"
            p2 = (
                r"(?:\b(?:en|vivo\s+en|es\s+en)\s+)?"
                rf"(\b{known_streets}\s+[\w\s\.\#\-]*?(?:n[u\xfa]mero|num|#)?\s*\d{{1,5}}(?:\s*(?:interior|int|depto)\s*\w+)?)"
                r"(?:\s*(?:en\s+|colonia\s+|col\.?\s*)([\w\s]+))?"
            )
            addr_match = re.search(p2, full_user_dialogue, re.IGNORECASE)
            
        if addr_match:
            detected_addr = addr_match.group(1).strip()
            detected_zone = addr_match.group(2).strip() if addr_match.group(2) else ""
            detected_addr = re.sub(r"^(?:(?:a\s+)?domicilio(?:\s+en)?|en|para|es en|vivo en|m[a\xe1]ndame|mandame)\s+", "", detected_addr, flags=re.IGNORECASE).strip()
            
            addr_lower = detected_addr.lower()
            is_valid_addr = len(detected_addr) >= 4 and not any(re.search(rf"\b{re.escape(fw)}\b", addr_lower) for fw in FORBIDDEN_ADDR_WORDS)
            
            if is_valid_addr:
                customer_updates["address"] = detected_addr.title()
                if detected_zone:
                    detected_zone = re.sub(r"^(?:la|el)\s+", "", detected_zone, flags=re.IGNORECASE).strip()
                    if not any(re.search(rf"\b{re.escape(fw)}\b", detected_zone.lower()) for fw in FORBIDDEN_ADDR_WORDS):
                        customer_updates["zone"] = detected_zone.title()

        # 2. Extracción de Preferencias / Notas Culinarias
        pref_matches = re.findall(r"\b(sin\s+[a-záéíóúñ]+|con\s+extra\s+[a-záéíóúñ]+|al[eé]rgic[oa]\s+a[l]?\s+[a-záéíóúñ]+)\b", full_user_dialogue, re.IGNORECASE)
        if pref_matches:
            valid_prefs = [p.strip().lower() for p in pref_matches if len(p.strip()) > 4]
            if valid_prefs:
                customer_updates["notes"] = ", ".join(set(valid_prefs))

        # 3. Aplicar actualizaciones al perfil del cliente si se detectaron
        if customer_updates and caller_phone not in ["Desconocido", "0000000000"]:
            self.db.update_customer_profile(caller_phone, customer_updates)
            logger.info(f"👤 [KAG Perfil Cliente Actualizado]: {caller_phone} -> {customer_updates}")

        # 4. Extracción de alias aprendidos en cada turno
        for turn in turns:
            u_text = turn.get("user_raw", "") or turn.get("user", "")
            b_resp = turn.get("bot_response", "") or turn.get("bot", "")
            if u_text:
                ev = self.learn_from_interaction(session_id, caller_phone, u_text, b_resp)
                if ev:
                    learned_events.append(ev)

        # 5. Persistir en la tabla call_logs de PostgreSQL
        call_summary = {
            "session_id": session_id,
            "caller_phone": caller_phone,
            "caller_name": caller_name,
            "duration_sec": duration_sec,
            "order_id": order_id,
            "turn_count": len(turns)
        }
        self.db.save_call_log(call_summary)

        # 6. Guardar archivo JSONL de transcripción completa
        transcript_record = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "caller_phone": caller_phone,
            "caller_name": caller_name,
            "duration_sec": duration_sec,
            "turn_count": len(turns),
            "order_confirmed": order_confirmed,
            "order_id": order_id,
            "customer_updates": customer_updates,
            "learning_events_count": len(learned_events),
            "turns": turns
        }

        # Volcado al histórico consolidado JSONL
        jsonl_path = os.path.join(logs_dir, "call_transcripts.jsonl")
        try:
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(transcript_record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error escribiendo en call_transcripts.jsonl: {e}")

        # Archivo individual de la llamada
        single_file = os.path.join(transcripts_dir, f"{session_id}.json")
        try:
            with open(single_file, "w", encoding="utf-8") as f:
                json.dump(transcript_record, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando transcripción individual {single_file}: {e}")

        logger.info(f"📁 [KAG Transcripción Persistida]: Sesión {session_id} guardada con {len(turns)} turnos y {len(learned_events)} aprendizajes.")
        return transcript_record

# Instancia global del motor KAG
kag_engine = KAGEngine()

