#!/usr/bin/env python3
"""
generate_voice_manifest.py
Genera y sincroniza el archivo voice_studio_manifest.json para el Estudio de Grabación Web de Ryu.
Extrae automáticamente:
1. 176 Platillos de menu_ryu.json (Japonés, Snacks, Italiano)
2. 25 Frases del Flujo Telefónico (Saludos, Preguntas, Zonas Foráneas, Promos)
3. 30 Cantidades, Conectores y Montos de Dinero
"""

import json
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent
MENU_FILE = ROOT_DIR / "menu_ryu.json"
MANIFEST_FILE = ROOT_DIR / "voice_studio_manifest.json"
AUDIO_DIR = ROOT_DIR / "audio_clips"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Frases fijas de conversación
FLOW_PHRASES = [
    {
        "id": "flow_saludo",
        "category": "flow",
        "title": "Saludo Inicial de Bienvenida",
        "prompt_text": "¡Buenas tardes! Bienvenido a Restaurante Ryu, comida japonesa, snacks y comida italiana. ¿Qué se te antoja ordenar hoy?",
        "phonetic_tip": "Tono cálido y amable de bienvenida, con ritmo natural y alegre."
    },
    {
        "id": "flow_pregunta_servicio",
        "category": "flow",
        "title": "Pregunta de Servicio (Domicilio / Recoger)",
        "prompt_text": "¿Tu pedido sería para entrega a domicilio o pasarías a recogerlo a la sucursal?",
        "phonetic_tip": "Entonación de pregunta clara y comprensible."
    },
    {
        "id": "flow_pregunta_direccion",
        "category": "flow",
        "title": "Pregunta de Dirección y Colonia",
        "prompt_text": "¿A qué dirección y colonia te lo enviamos?",
        "phonetic_tip": "Tono atento y claro para que el cliente dicte su domicilio."
    },
    {
        "id": "flow_pregunta_pago",
        "category": "flow",
        "title": "Pregunta de Método de Pago",
        "prompt_text": "¿Tu pago sería en efectivo o con tarjeta?",
        "phonetic_tip": "Pausa breve entre 'efectivo' y 'tarjeta'."
    },
    {
        "id": "flow_pregunta_billete",
        "category": "flow",
        "title": "Pregunta de Denominación para Cambio",
        "prompt_text": "¿Con qué billete pagarías para enviarte tu cambio?",
        "phonetic_tip": "Tono servicial y paciente."
    },
    {
        "id": "flow_pregunta_algo_mas",
        "category": "flow",
        "title": "Pregunta si Desea Agregar Algo Más",
        "prompt_text": "¿Te gustaría agregar algo más a tu orden, alguna bebida, postre o rollo?",
        "phonetic_tip": "Tono de sugerencia amable sin sonar insistente."
    },
    {
        "id": "flow_espera_calma",
        "category": "flow",
        "title": "Recordatorio de Paciencia",
        "prompt_text": "Aquí sigo en la línea, tómate tu tiempo con calma.",
        "phonetic_tip": "Tono tranquilizador y paciente."
    },
    {
        "id": "flow_espera_corto",
        "category": "flow",
        "title": "Intercepción Corta de Presencia",
        "prompt_text": "Bueno, aquí sigo en la línea a tus órdenes.",
        "phonetic_tip": "Rápido y atento, en caso de silencios breves del cliente."
    },
    {
        "id": "flow_confirmacion_intro",
        "category": "flow",
        "title": "Introducción de Confirmación",
        "prompt_text": "Excelente, déjame confirmarte tu orden:",
        "phonetic_tip": "Tono seguro y claro antes de enumerar los platillos."
    },
    {
        "id": "flow_confirmacion_cierre",
        "category": "flow",
        "title": "Pregunta de Validación de Orden",
        "prompt_text": "¿Todo correcto con tu pedido?",
        "phonetic_tip": "Entonación de confirmación final clara."
    },
    {
        "id": "flow_despedida_general",
        "category": "flow",
        "title": "Despedida y Agradecimiento",
        "prompt_text": "¡Muchas gracias por ordenar en Ryu! Enseguida lo pasamos a cocina para preparártelo. ¡Que disfrutes tu comida!",
        "phonetic_tip": "Entonación sonriente, agradecida y energética."
    },
    {
        "id": "flow_recoger_listo",
        "category": "flow",
        "title": "Instrucciones de Recoger en Sucursal",
        "prompt_text": "Tu pedido estará listo en aproximadamente 25 a 30 minutos aquí en sucursal en Paseo del Centenario 27, colonia Cofradía. ¡Te esperamos!",
        "phonetic_tip": "Pronunciar claramente la dirección 'Paseo del Centenario 27'."
    },
    {
        "id": "flow_domicilio_tiempo",
        "category": "flow",
        "title": "Tiempo Estimado para Domicilio",
        "prompt_text": "Tu pedido ya está en camino a cocina, el repartidor llegará a tu domicilio en aproximadamente 40 a 55 minutos.",
        "phonetic_tip": "Tono confiable y profesional."
    },
    {
        "id": "flow_cocina_cerrada",
        "category": "flow",
        "title": "Aviso de Cocina Cerrada",
        "prompt_text": "Hola, muchas gracias por llamar a Restaurante Ryu. En este momento nuestra cocina se encuentra cerrada. Nuestro horario de servicio comienza a las dos de la tarde. ¡Esperamos tu llamada más tarde!",
        "phonetic_tip": "Tono muy cortés, empático y claro."
    },
    {
        "id": "flow_zona_foranea_aviso",
        "category": "flow",
        "title": "Aviso General de Zona Foránea",
        "prompt_text": "Te comento que para tu zona el envío tiene un costo adicional que se sumará al total de tu cuenta.",
        "phonetic_tip": "Informativo y transparente."
    },
    {
        "id": "flow_zona_medineno",
        "category": "flow",
        "title": "Tarifa de Envío El Medineño",
        "prompt_text": "Para El Medineño el costo de envío es de 100 pesos.",
        "phonetic_tip": "Claro y conciso."
    },
    {
        "id": "flow_zona_san_martin",
        "category": "flow",
        "title": "Tarifa de Envío San Martín de Cañas",
        "prompt_text": "Para San Martín de Cañas el costo de envío es de 100 pesos.",
        "phonetic_tip": "Claro y conciso."
    },
    {
        "id": "flow_zona_magdalena",
        "category": "flow",
        "title": "Tarifa de Envío Magdalena",
        "prompt_text": "Para Magdalena el costo de envío es de 100 pesos.",
        "phonetic_tip": "Claro y conciso."
    },
    {
        "id": "flow_zona_tierra_agave",
        "category": "flow",
        "title": "Tarifa de Envío Fraccionamiento Tierra de Agave",
        "prompt_text": "Para Fraccionamiento Tierra de Agave el costo de envío es de 80 pesos.",
        "phonetic_tip": "Claro y conciso."
    },
    {
        "id": "flow_zona_aguacatillo",
        "category": "flow",
        "title": "Tarifa de Envío El Aguacatillo",
        "prompt_text": "Para El Aguacatillo el costo de envío es de 30 pesos.",
        "phonetic_tip": "Claro y conciso."
    },
    {
        "id": "flow_promocion_intro",
        "category": "flow",
        "title": "Introducción a Promoción del Día",
        "prompt_text": "Hoy tenemos una excelente promoción activa:",
        "phonetic_tip": "Entonación atractiva y animada."
    },
    {
        "id": "flow_promo_3x2",
        "category": "flow",
        "title": "Promoción 3x2 en Sushi",
        "prompt_text": "Hoy tenemos promoción 3 por 2 en rollos de sushi tradicionales. ¡Compras dos rollos y el tercero va por nuestra cuenta!",
        "phonetic_tip": "Entonación entusiasta, destacando 'tres por dos'."
    },
    {
        "id": "flow_promo_boneless",
        "category": "flow",
        "title": "Promoción Boneless Medio Kilo",
        "prompt_text": "Hoy tenemos los Boneless de medio kilo en promoción especial a solo 120 pesos.",
        "phonetic_tip": "Entonación animada."
    },
    {
        "id": "flow_promo_hamburguesas",
        "category": "flow",
        "title": "Promoción Hamburguesas",
        "prompt_text": "Hoy tenemos todas las hamburguesas sencillas con papas a solo 85 pesos.",
        "phonetic_tip": "Entonación animada."
    },
    {
        "id": "flow_promo_yakimeshi",
        "category": "flow",
        "title": "Promoción Yakimeshi Mixto",
        "prompt_text": "Hoy el Yakimeshi mixto tiene 20% de descuento.",
        "phonetic_tip": "Entonación animada."
    }
]

# Tokens y Conectores
TOKENS_AND_NUMBERS = [
    {"id": "tok_un", "category": "numbers", "title": "Un", "prompt_text": "un", "phonetic_tip": "Pausa corta después de la palabra."},
    {"id": "tok_una", "category": "numbers", "title": "Una", "prompt_text": "una", "phonetic_tip": "Pausa corta."},
    {"id": "tok_una_orden", "category": "numbers", "title": "Una orden de", "prompt_text": "una orden de", "phonetic_tip": "Fluido y natural."},
    {"id": "tok_dos", "category": "numbers", "title": "Dos", "prompt_text": "dos", "phonetic_tip": "Pausa corta."},
    {"id": "tok_tres", "category": "numbers", "title": "Tres", "prompt_text": "tres", "phonetic_tip": "Pausa corta."},
    {"id": "tok_cuatro", "category": "numbers", "title": "Cuatro", "prompt_text": "cuatro", "phonetic_tip": "Pausa corta."},
    {"id": "tok_cinco", "category": "numbers", "title": "Cinco", "prompt_text": "cinco", "phonetic_tip": "Pausa corta."},
    {"id": "tok_seis", "category": "numbers", "title": "Seis", "prompt_text": "seis", "phonetic_tip": "Pausa corta."},
    {"id": "tok_y", "category": "numbers", "title": "Y (Conector)", "prompt_text": "y", "phonetic_tip": "Conector natural entre platillos."},
    {"id": "tok_con", "category": "numbers", "title": "Con", "prompt_text": "con", "phonetic_tip": "Conector natural."},
    {"id": "tok_sin", "category": "numbers", "title": "Sin", "prompt_text": "sin", "phonetic_tip": "Ej. 'sin cebolla'."},
    {"id": "tok_pesos", "category": "numbers", "title": "Pesos", "prompt_text": "pesos", "phonetic_tip": "Cierre de precio."},
    {"id": "tok_total_serian", "category": "numbers", "title": "El total sería", "prompt_text": "el total sería de", "phonetic_tip": "Introducción al precio."},
    {"id": "tok_efectivo", "category": "numbers", "title": "En efectivo", "prompt_text": "en efectivo", "phonetic_tip": "Claro."},
    {"id": "tok_tarjeta", "category": "numbers", "title": "Con tarjeta", "prompt_text": "con tarjeta", "phonetic_tip": "Claro."},
    {"id": "tok_domicilio", "category": "numbers", "title": "Para entrega a domicilio", "prompt_text": "para entrega a domicilio", "phonetic_tip": "Fluido."},
    {"id": "tok_recoger", "category": "numbers", "title": "Para pasar a recoger", "prompt_text": "para pasar a recoger a sucursal", "phonetic_tip": "Fluido."},
    # Cantidades de dinero comunes
    {"id": "num_80", "category": "numbers", "title": "80 pesos", "prompt_text": "ochenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_100", "category": "numbers", "title": "100 pesos", "prompt_text": "cien pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_120", "category": "numbers", "title": "120 pesos", "prompt_text": "ciento veinte pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_140", "category": "numbers", "title": "140 pesos", "prompt_text": "ciento cuarenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_150", "category": "numbers", "title": "150 pesos", "prompt_text": "ciento cincuenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_160", "category": "numbers", "title": "160 pesos", "prompt_text": "ciento sesenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_180", "category": "numbers", "title": "180 pesos", "prompt_text": "ciento ochenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_200", "category": "numbers", "title": "200 pesos", "prompt_text": "doscientos pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_220", "category": "numbers", "title": "220 pesos", "prompt_text": "doscientos veinte pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_250", "category": "numbers", "title": "250 pesos", "prompt_text": "doscientos cincuenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_280", "category": "numbers", "title": "280 pesos", "prompt_text": "doscientos ochenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_300", "category": "numbers", "title": "300 pesos", "prompt_text": "trescientos pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_350", "category": "numbers", "title": "350 pesos", "prompt_text": "trescientos cincuenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_400", "category": "numbers", "title": "400 pesos", "prompt_text": "cuatrocientos pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_450", "category": "numbers", "title": "450 pesos", "prompt_text": "cuatrocientos cincuenta pesos", "phonetic_tip": "Precio claro."},
    {"id": "num_500", "category": "numbers", "title": "500 pesos", "prompt_text": "quinientos pesos", "phonetic_tip": "Precio claro."}
]


def extract_dishes_from_menu():
    """Lee menu_ryu.json y genera la lista estructurada de platillos para grabación."""
    if not MENU_FILE.exists():
        print(f"Error: {MENU_FILE} no encontrado.")
        return []

    with open(MENU_FILE, "r", encoding="utf-8") as f:
        menu_data = json.load(f).get("menu", {})

    dishes = []

    # 1. JAPONES
    japanese = menu_data.get("japanese", {})
    for cat_key, items in japanese.items():
        if isinstance(items, list):
            for it in items:
                d_id = f"dish_{it.get('id', cat_key)}"
                name = it.get("name", "").strip()
                price = it.get("price", 0)
                price_str = f" (${int(price)} MXN)" if price else ""
                dishes.append({
                    "id": d_id,
                    "category": "japanese",
                    "sub_category": cat_key,
                    "title": f"{name}{price_str}",
                    "prompt_text": name,
                    "phonetic_tip": f"Pronunciar claramente el nombre del platillo: {name}"
                })

    # 2. SNACKS
    snacks = menu_data.get("snacks", {})
    for cat_key, items in snacks.items():
        if isinstance(items, list):
            for it in items:
                d_id = f"dish_{it.get('id', cat_key)}"
                name = it.get("name", "").strip()
                price = it.get("price", 0)
                price_str = f" (${int(price)} MXN)" if price else ""
                dishes.append({
                    "id": d_id,
                    "category": "snacks",
                    "sub_category": cat_key,
                    "title": f"{name}{price_str}",
                    "prompt_text": name,
                    "phonetic_tip": f"Pronunciar claramente: {name}"
                })

    # 3. ITALIANO
    italian = menu_data.get("italian", {})
    # Platillos
    for it in italian.get("platillos", []):
        d_id = f"dish_{it.get('id', 'ita')}"
        name = it.get("name", "").strip()
        price = it.get("price", 0)
        dishes.append({
            "id": d_id,
            "category": "italian",
            "sub_category": "platillos",
            "title": f"{name} (${int(price)} MXN)",
            "prompt_text": name,
            "phonetic_tip": f"Platillo italiano: {name}"
        })
    # Paninis y Pitas
    paninis = italian.get("paninis_y_pitas", {}).get("especialidades", [])
    for esp in paninis:
        name = esp.get("name", "")
        d_id = f"dish_ita_panini_{name.lower().replace(' ', '_')}"
        dishes.append({
            "id": d_id,
            "category": "italian",
            "sub_category": "paninis_y_pitas",
            "title": f"Panini o Pita {name}",
            "prompt_text": f"Panini de {name}",
            "phonetic_tip": f"Especialidad de Panini: {name}"
        })
    # Ensaladas Italianas
    ensaladas = italian.get("ensaladas_italianas", {}).get("variedades", [])
    for ens in ensaladas:
        name = ens if isinstance(ens, str) else ens.get("name", "")
        d_id = f"dish_ita_ensalada_{name.lower().replace(' ', '_')}"
        dishes.append({
            "id": d_id,
            "category": "italian",
            "sub_category": "ensaladas",
            "title": f"Ensalada Italiana {name}",
            "prompt_text": f"Ensalada de {name}",
            "phonetic_tip": f"Ensalada: {name}"
        })
    # Sodas Italianas
    for soda in italian.get("sodas_italianas", []):
        d_id = f"dish_{soda.get('id', 'ita_soda')}"
        name = soda.get("name", "").strip()
        price = soda.get("price", 0)
        dishes.append({
            "id": d_id,
            "category": "italian",
            "sub_category": "sodas_italianas",
            "title": f"{name} (${int(price)} MXN)",
            "prompt_text": name,
            "phonetic_tip": f"Bebida italiana: {name}"
        })

    return dishes


def build_manifest():
    """Compila o actualiza el manifiesto conservando grabaciones previas si existen."""
    existing_items = {}
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                for it in old_data.get("items", []):
                    existing_items[it["id"]] = it
        except Exception as e:
            print(f"Aviso leyendo manifiesto existente: {e}")

    dishes = extract_dishes_from_menu()
    all_raw_items = FLOW_PHRASES + dishes + TOKENS_AND_NUMBERS

    consolidated_items = []
    recorded_count = 0

    for it in all_raw_items:
        i_id = it["id"]
        # Check if audio file physically exists on disk
        alaw_path = AUDIO_DIR / f"{i_id}.alaw"
        has_audio = alaw_path.exists() and alaw_path.stat().st_size > 0

        old_meta = existing_items.get(i_id, {})
        status = "recorded" if has_audio else old_meta.get("status", "pending")
        if status == "recorded" and not has_audio:
            status = "pending"

        duration = old_meta.get("duration_sec", 0.0)
        if has_audio and duration == 0.0:
            duration = round(alaw_path.stat().st_size / 8000.0, 2)

        if status == "recorded":
            recorded_count += 1

        consolidated_items.append({
            "id": i_id,
            "category": it["category"],
            "sub_category": it.get("sub_category", ""),
            "title": it["title"],
            "prompt_text": it["prompt_text"],
            "phonetic_tip": it.get("phonetic_tip", ""),
            "status": status,
            "duration_sec": duration,
            "audio_alaw": f"/audio_clips/{i_id}.alaw" if has_audio else None,
            "audio_wav": f"/audio_clips/{i_id}.wav" if has_audio else None,
            "updated_at": old_meta.get("updated_at", None)
        })

    manifest = {
        "_version": "1.0.0",
        "generated_at": datetime.now().isoformat(),
        "total_items": len(consolidated_items),
        "recorded_items": recorded_count,
        "pending_items": len(consolidated_items) - recorded_count,
        "completion_percent": round((recorded_count / len(consolidated_items)) * 100, 1) if consolidated_items else 0,
        "items": consolidated_items
    }

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Manifiesto generado exitosamente en {MANIFEST_FILE}")
    print(f"Total ítems: {manifest['total_items']} (Grabados: {recorded_count}, Pendientes: {manifest['pending_items']})")
    return manifest


if __name__ == "__main__":
    build_manifest()
