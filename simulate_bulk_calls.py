# ==============================================================================
# SIMULADOR MASIVO DE LLAMADAS TELEFÓNICAS - RESTAURANTE RYU
# Entrena el bucle de autoaprendizaje KAG y densifica el grafo Apache AGE
# ==============================================================================

import os
import sys
import time
import random

# Asegurar encoding UTF-8
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from kag_engine import kag_engine
from db.graph_db import graph_db
from proto_service import create_order_proto, serialize_order

SIMULATED_CALLS = [
    {
        "phone": "+523314143526",
        "name": "Arath Morales",
        "turns": [
            ("Hola buenas tardes, tienen servicio a domicilio?", "¿A qué colonia y calle te lo mandamos?"),
            ("Sería en calle Girasol número doce en la Cofradía", "Anotada la dirección en Cofradía. ¿Qué te gustaría ordenar?"),
            ("Me das un sucho empanizado y una soda de fresa con boba", "Un Sushi Empanizado y una soda italiana de fresa con boba. ¿Deseas agregar algo más?"),
            ("No nada más, cuánto sería en total?", "Serían doscientos quince pesos con envío. ¿Pagas en efectivo o tarjeta?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu pedido para mandarlo a cocina?"),
            ("Sí, confírmalo por favor", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "learned_aliases": [("sucho empanizado", "Sushi Empanizado"), ("boba de fresa", "Soda Italiana de Fresa con Boba")]
    },
    {
        "phone": "+523741001234",
        "name": "Josué Cabrales",
        "turns": [
            ("Hola, me gustaría ordenar una hamburguesa grande", "De res grande tenemos la Big Ryu en noventa y cinco o la Ranchera Especial en ciento veinticinco."),
            ("La Ranchera Especial y unas papas a la francesa", "Anotada la Ranchera Especial con papas. ¿Alguna bebida?"),
            ("Un Calpico de un litro", "Calpico de un litro. ¿Es para recoger en sucursal o a domicilio?"),
            ("Paso a recoger al restaurante en veinte minutos", "Anotado para recoger en sucursal. ¿Tu nombre?"),
            ("Josué Cabrales", "¿Confirmo tu pedido?"),
            ("Sí, adelante", "¡Excelente! Queda listo para que pases a recoger.")
        ],
        "learned_aliases": [("la ranchera", "Hamburguesa Ranchera Especial"), ("calpico grande", "Calpico (1 Litro)")]
    },
    {
        "phone": "+523385269988",
        "name": "Valeria Gómez",
        "turns": [
            ("Buenas noches, tienen lasaña italiana disponible?", "Sí, tenemos Lasagna Tradicional con carne y queso mozzarella en ciento cincuenta pesos."),
            ("Quiero una soñada y un petit chigni alfredo con pollo", "Una Lasaña Tradicional y un Fettuccine Alfredo con pollo. ¿Deseas agregar postre o bebida?"),
            ("Dos refrescos de lata por favor", "¿A qué domicilio te lo enviamos?"),
            ("En Paseo del Centenario cuarenta y cinco interior tres", "¿Tu método de pago sería efectivo o tarjeta?"),
            ("Con tarjeta al repartidor", "¿Confirmamos tu pedido?"),
            ("Sí, está bien", "¡Excelente! Ya pasé tu orden a cocina.")
        ],
        "learned_aliases": [("soñada", "Lasagna Tradicional"), ("petit chigni", "Fettuccine Alfredo")]
    },
    {
        "phone": "+523741054321",
        "name": "Carlos Mendoza",
        "turns": [
            ("Buenas, tienen servicio hasta Cantaritos El Güero?", "Sí, el costo de envío a Cantaritos El Güero es de cuarenta pesos."),
            ("Perfecto, mándame una orden de alitas mango habanero y unos boneless barbacoa", "Una orden de alitas mango habanero y boneless BBQ. ¿Qué bebidas te gustaría agregar?"),
            ("Dos cervezas Corona bien frías", "¿Pagarías en efectivo o tarjeta?"),
            ("En efectivo con billete de doscientos", "¿Confirmas tu orden?"),
            ("Sí, por favor", "¡Excelente! Ya mandamos la comanda a cocina.")
        ],
        "learned_aliases": [("alitas habanero", "Alitas Mango Habanero"), ("boneless barbacoa", "Boneless BBQ")]
    },
    {
        "phone": "+523311223344",
        "name": "Mariana Ruiz",
        "turns": [
            ("Hola quiero hacer un pedido programado para las ocho de la noche", "Con gusto te agendamos para las ocho de la noche. ¿Qué platillos te gustaría ordenar?"),
            ("Un ramen de la casa tradicional y un yakimeshi especial con camarón", "Un Ramen Ryu tradicional y un Yakimeshi mixto con camarón agendados para las ocho. ¿A qué dirección?"),
            ("Calle Juárez setenta y ocho, centro de Tequila", "¿Cómo prefieres realizar tu pago?"),
            ("Pago con tarjeta al entregar", "¿Confirmo tu pedido agendado?"),
            ("Sí, confirmado", "¡Excelente! Quedó agendado tu pedido para las ocho de la noche.")
        ],
        "learned_aliases": [("ramen de la casa", "Ramen Ryu"), ("yakimeshi especial", "Yakimeshi Mixto")]
    }
]

def run_simulations():
    print("==================================================================")
    print("INICIANDO SIMULACIONES DE LLAMADAS PARA DENSIFICAR EL GRAFO KAG")
    print(f"Base de datos de grafos: {graph_db.graph_name} (PostgreSQL + Apache AGE)")
    print("==================================================================\n")
    
    total_learned = 0
    total_interactions = 0
    
    for i, call_data in enumerate(SIMULATED_CALLS, 1):
        phone = call_data["phone"]
        name = call_data["name"]
        print(f"📞 Simulando llamada {i}/{len(SIMULATED_CALLS)}: {name} ({phone})")
        session_id = f"sim_call_{int(time.time())}_{i}"
        
        # 1. Registrar / Actualizar cliente en Grafo AGE y SQL
        graph_db.upsert_customer(phone, name, total_orders=i)
        
        # 2. Procesar turnos de conversación
        for turn_idx, (user_msg, bot_msg) in enumerate(call_data["turns"], 1):
            total_interactions += 1
            # Normalización KAG
            norm_text, reps = kag_engine.normalize_user_text(user_msg)
            # Extracción de hechos
            facts = kag_engine.retrieve_ground_truth_facts(norm_text)
            # Autoaprendizaje continuo
            kag_engine.learn_from_interaction(
                session_id=session_id,
                caller_phone=phone,
                user_text=user_msg,
                bot_response=bot_msg
            )
            
        # 3. Forzar vinculación de nuevos alias aprendidos en Apache AGE
        for alias_phrase, canonical_name in call_data.get("learned_aliases", []):
            try:
                alias_clean = alias_phrase.strip().lower()
                query = f"""
                SELECT * FROM cypher('{graph_db.graph_name}', $$
                    MATCH (d:Dish)
                    WHERE toLower(d.name) = toLower('{canonical_name}')
                    MERGE (a:Alias {{name: '{alias_clean}'}})
                    MERGE (a)-[r:MEANS]->(d)
                    RETURN d.name, a.name
                $$) as (dish_name agtype, alias_name agtype);
                """
                graph_db.execute_cypher(query)
                total_learned += 1
                print(f"   ✨ [Grafo AGE]: Vinculado alias '{alias_phrase}' -> '{canonical_name}'")
            except Exception as e:
                print(f"   Aviso en cypher alias: {e}")
                
        print(f"   ✅ Llamada {i} procesada. Perfil de cliente y diálogo integrados al KAG.\n")
        
    print("==================================================================")
    print(f"RESUMEN DE ENTRENAMIENTO DE GRAFOS:")
    print(f"• Llamadas simuladas: {len(SIMULATED_CALLS)}")
    print(f"• Turnos de conversación procesados: {total_interactions}")
    print(f"• Nuevos nodos y relaciones aprendidas en Apache AGE: {total_learned}")
    print(f"• Alias totales en caché de memoria KAG: {len(kag_engine.alias_cache)}")
    print("==================================================================")

if __name__ == "__main__":
    run_simulations()
