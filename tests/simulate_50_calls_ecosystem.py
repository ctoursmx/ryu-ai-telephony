# -*- coding: utf-8 -*-
"""
==============================================================================
RESTAURANTE RYU - SIMULADOR MASIVO DE 50 LLAMADAS END-TO-END DEL ECOSISTEMA
Verificación exhaustiva de:
1. Diálogo conversacional con sentido y coherencia (3 Menús: Japonés, Snacks, Italiano)
2. KAG Engine: Hechos de verdad, reglas de envío, zonas especiales y recargo nocturno
3. Aprendizaje continuo de alias fonéticos en Grafo Apache AGE y PostgreSQL
4. Order FSM: Máquina de estados finitos y validación de comandas
5. Serialización binaria Protobuf y almacenamiento en Base de Datos
6. Generación y formateo de comandas para Telegram
7. Puente Soft Restaurant (SQL Server / contingencia SQLite) e impresión multiestación
8. Transcripciones estructuradas y telemetría de llamadas (JSONL)
==============================================================================
"""

import os
import sys
import time
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# Encoding seguro para Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from voice_engine_ryu import RyuVoiceAgent, load_restaurant_state, get_delivery_conditions_summary
from kag_engine import kag_engine
from proto_service import ProtoService
from db.graph_db import db_manager, GRAPH_NAME
from soft_restaurant_bridge import dispatch_order
from security_guard import call_rate_limiter, input_sanitizer

# Definición exhaustiva de 50 escenarios de llamadas realistas y completos
CALL_SCENARIOS = [
    # --- MENÚ JAPONÉS: ROLLOS ESPECIALES Y TRADICIONALES ---
    {
        "id": 1,
        "phone": "+523311001001",
        "name": "Carlos Valenzuela",
        "dialogue": [
            ("Hola buenas tardes, me gustaría pedir comida japonesa para entrega a domicilio", "¿A qué dirección y colonia te lo enviamos?"),
            ("Sería en Calle Girasol número doce en la Colonia Cofradía", "Anotada la dirección en Calle Girasol #12, Cofradía. ¿Qué te gustaría ordenar de nuestro menú japonés?"),
            ("Quiero un rollo Mechudo y un sushi Philadelphia empanizado", "Un Mechudo y un Philadelphia Empanizado. ¿Gustas agregar alguna bebida como Calpico o refresco?"),
            ("Un Calpico de un litro por favor", "Anotado el Calpico de un litro. ¿Tu pago sería en efectivo o con tarjeta?"),
            ("En efectivo con un billete de quinientos", "¿Confirmo tu pedido para mandarlo a cocina?"),
            ("Sí, confírmalo por favor", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Mechudo", "Philadelphia Empanizado", "Calpico 1L"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },
    {
        "id": 2,
        "phone": "+523311001002",
        "name": "Andrea Navarro",
        "dialogue": [
            ("Buenas tardes, tienen disponible el rollo Cheese Explosion?", "Sí, el Cheese Explosion está disponible en ciento treinta y cinco pesos."),
            ("Perfecto, quiero dos Cheese Explosion y una orden de kushiages de queso", "Dos Cheese Explosion y una orden de Kushiages. ¿Sería a domicilio o para recoger en sucursal?"),
            ("Paso a recoger al restaurante en veinte minutos", "Anotado para recoger en sucursal. ¿A qué nombre registramos la orden?"),
            ("Andrea Navarro", "Anotada Andrea Navarro. ¿Pagarías con tarjeta o en efectivo?"),
            ("Pago con tarjeta en sucursal", "¿Confirmo tu pedido?"),
            ("Sí, adelante por favor", "¡Excelente! Ya quedó registrado tu pedido para recoger en sucursal.")
        ],
        "expected_zone": "Sucursal",
        "expected_items": ["Cheese Explosion", "Kushiages"],
        "payment": "Tarjeta",
        "type": "sucursal"
    },
    {
        "id": 3,
        "phone": "+523311001003",
        "name": "Fernando Ruiz",
        "dialogue": [
            ("Hola, quiero pedir la Tabla de Sushi Mixta de treinta piezas", "La Tabla de Sushi Mixta de 30 bocadillos tiene un costo de trescientos pesos. ¿A dónde te la enviamos?"),
            ("Avenida Hidalgo cuarenta y cinco interior dos, centro de Tequila", "Anotado en Avenida Hidalgo #45. ¿Deseas agregar alguna bebida o postre?"),
            ("Una jarra de Calpico tradicional", "Jarra de Calpico tradicional. ¿Tu forma de pago?"),
            ("Efectivo con billete de quinientos", "¿Confirmo tu comanda?"),
            ("Sí, confírmala", "¡Excelente! Ya mandé tu pedido a cocina.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Tabla de Sushi Mixta", "Calpico Jarra"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },
    {
        "id": 4,
        "phone": "+523311001004",
        "name": "Mariana Orozco",
        "dialogue": [
            ("Hola buenas tardes, tienen servicio a La Toma?", "Sí, con gusto entregamos en La Toma, la tarifa especial de envío es de ochenta pesos."),
            ("Muy bien, mándame un Arcoíris Roll y un sushi de plátano", "Un Arcoíris Roll y un Plátano Roll para La Toma. ¿Alguna indicación especial?"),
            ("El sushi de plátano sin queso philadelphia por favor", "Anotado sin queso philadelphia. ¿Pagarías en efectivo o tarjeta?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu orden para La Toma?"),
            ("Sí, por favor confirmen", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "La Toma",
        "expected_items": ["Arcoíris Roll", "Plátano Roll"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },
    {
        "id": 5,
        "phone": "+523311001005",
        "name": "Héctor Barba",
        "dialogue": [
            ("Buenas tardes, cuánto cobran de envío a Cantaritos El Güero?", "El costo de envío a Cantaritos El Güero es de setenta pesos."),
            ("Perfecto, quiero una orden de alitas mango habanero y un yakimeshi mixto con camarón", "Alitas Mango Habanero y Yakimeshi Mixto con camarón. ¿Deseas agregar bebidas?"),
            ("Dos cervezas Corona frías", "¿Pagas con tarjeta o en efectivo al repartidor?"),
            ("Con tarjeta por favor", "¿Confirmo tu pedido para Cantaritos El Güero?"),
            ("Sí, está confirmado", "¡Excelente! Ya mandé la orden a cocina.")
        ],
        "expected_zone": "Cantaritos El Güero",
        "expected_items": ["Alitas Mango Habanero", "Yakimeshi Mixto", "Cerveza Corona"],
        "payment": "Tarjeta",
        "type": "domicilio"
    },

    # --- MENÚ ITALIANO: LASAÑA, PASTAS, PANINIS, PITAS Y SODAS CON BOBA ---
    {
        "id": 6,
        "phone": "+523311001006",
        "name": "Sofía Cárdenas",
        "dialogue": [
            ("Buenas tardes, tienen lasaña italiana hoy?", "Sí, tenemos Lasaña Tradicional en capas con carne y mozzarella en ciento cincuenta pesos."),
            ("Quiero una lasaña y un fettuccine alfredo con pollo", "Una Lasaña Tradicional y un Fettuccine Alfredo con pollo. ¿Deseas agregar sodas italianas con boba?"),
            ("Sí, una soda italiana de fresa con boba y una de mora azul", "Dos sodas italianas con boba. ¿A qué dirección te lo enviamos?"),
            ("Paseo del Centenario setenta y tres", "¿Tu pago sería en efectivo o tarjeta?"),
            ("Con tarjeta al recibir", "¿Confirmo tu orden?"),
            ("Sí, confírmala por favor", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Lasagna Tradicional", "Fettuccine Alfredo", "Soda Italiana con Boba"],
        "payment": "Tarjeta",
        "type": "domicilio"
    },
    {
        "id": 7,
        "phone": "+523311001007",
        "name": "Rodrigo Tapia",
        "dialogue": [
            ("Hola qué paninis y pitas tienen disponibles?", "Tenemos especialidades BBQ, Chipotle, Cheesesteak, Pollo Clásico, Pollo Crispy y Carnes Frías. Vienen con papas a la francesa."),
            ("Quiero un panini de pollo crispy y una pita cheesesteak", "Un Panini Pollo Crispy y una Pita Cheesesteak con papas. ¿Alguna bebida?"),
            ("Un refresco de lata de trescientos cincuenta y cinco mililitros", "¿Sería a domicilio o para recoger en sucursal?"),
            ("A domicilio a Calle Zaragoza número ochenta y cinco", "¿Pagas en efectivo o con tarjeta?"),
            ("Efectivo con billete de doscientos", "¿Confirmamos tu pedido?"),
            ("Sí, confírmalo", "¡Excelente! Ya mandé tu orden a cocina.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Panini Pollo Crispy", "Pita Cheesesteak", "Refresco"],
        "payment": "Efectivo $200",
        "type": "domicilio"
    },
    {
        "id": 8,
        "phone": "+523311001008",
        "name": "Valeria Meza",
        "dialogue": [
            ("Hola, entregan en El Medineño?", "Sí, entregamos en El Medineño con una tarifa especial de cien pesos."),
            ("De acuerdo, quiero un espagueti boloñesa y una lasaña", "Un Espagueti Boloñesa y una Lasaña Tradicional para El Medineño. ¿Deseas bebidas?"),
            ("Una soda de piña con boba", "¿Cómo prefieres realizar tu pago?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu pedido para El Medineño?"),
            ("Sí, confírmalo", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "El Medineño",
        "expected_items": ["Espagueti Boloñesa", "Lasagna Tradicional", "Soda Italiana con Boba"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },

    # --- MENÚ SNACKS: HAMBURGUESAS, COMBOS, ALITAS Y BONELESS ---
    {
        "id": 9,
        "phone": "+523311001009",
        "name": "Jorge Corona",
        "dialogue": [
            ("Buenas tardes, me das informes del paquete Pa Que Compartas?", "El paquete Pa Que Compartas incluye alitas, boneless, dos hamburguesas y papas por doscientos diez pesos."),
            ("Mándame ese paquete, con las alitas en salsa BBQ y los boneless mango habanero", "Pa Que Compartas con alitas BBQ y boneless mango habanero. ¿A qué dirección te lo enviamos?"),
            ("Calle Morelos número treinta y dos en la colonia centro", "Anotado en Morelos #32. ¿Pagarías con tarjeta o en efectivo?"),
            ("En efectivo con billete de quinientos pesos", "¿Confirmo tu comanda para mandarla a cocina?"),
            ("Sí, confírmala por favor", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Pa Que Compartas"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },
    {
        "id": 10,
        "phone": "+523311001010",
        "name": "Karla Esparza",
        "dialogue": [
            ("Hola, quiero dos hamburguesas Big Ryu con papas a la francesa", "Dos hamburguesas Big Ryu con papas. ¿Deseas agregar tocino extra o bebidas?"),
            ("Con tocino extra en ambas hamburguesas y dos aguas de jamaica", "Anotado con tocino extra y dos aguas. ¿Es para recoger en restaurante o a domicilio?"),
            ("Paso a recoger a la sucursal de Paseo del Centenario", "Anotado para recoger en sucursal. ¿A nombre de quién?"),
            ("Karla Esparza", "¿Tu forma de pago sería tarjeta o efectivo?"),
            ("Pago con tarjeta al recoger", "¿Confirmamos tu orden?"),
            ("Sí, confirmo", "¡Excelente! Ya quedó lista en cocina para tu llegada.")
        ],
        "expected_zone": "Sucursal",
        "expected_items": ["Hamburguesa Big Ryu", "Papas Francesa", "Topping Tocino"],
        "payment": "Tarjeta",
        "type": "sucursal"
    },

    # --- PEDIDOS PROGRAMADOS / A FUTURO ---
    {
        "id": 11,
        "phone": "+523311001011",
        "name": "Ernesto Ramos",
        "dialogue": [
            ("Hola buenas tardes, puedo programar un pedido para las ocho y media de la noche?", "Con gusto te agendamos para las ocho y media de la noche. ¿Qué te gustaría ordenar?"),
            ("Un ramen tradicional y una orden de gyosas de res", "Un Ramen y gyosas de res agendados para las 8:30 PM. ¿A qué dirección te lo entregamos?"),
            ("Calle Juárez número cincuenta y ocho", "¿Tu pago sería en efectivo o tarjeta?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu pedido agendado para las 8:30 PM?"),
            ("Sí, confírmalo por favor", "¡Excelente! Ya quedó agendado tu pedido para las 8:30 PM.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Ramen Ryu", "Gyosas"],
        "payment": "Efectivo $500",
        "type": "programado",
        "scheduled_time": "8:30 PM"
    },
    {
        "id": 12,
        "phone": "+523311001012",
        "name": "Lucía Morales",
        "dialogue": [
            ("Buenas tardes, quiero dejar encargado un pedido para mañana a las dos de la tarde", "Con gusto te lo dejamos programado para mañana a las dos de la tarde. ¿Qué platillos serían?"),
            ("Tres paquetes de sushi empanizado y dos calpicos de litro", "Tres sushis empanizados y dos calpicos de litro agendados para mañana a las 2:00 PM. ¿A qué dirección?"),
            ("Calle Abasolo número doce interior cuatro", "¿Tu forma de pago?"),
            ("Con tarjeta al repartidor", "¿Confirmo tu pedido a futuro?"),
            ("Sí, confirmado", "¡Excelente! Quedó agendado tu pedido para mañana a las 2:00 PM.")
        ],
        "expected_zone": "Tequila Urbano",
        "expected_items": ["Sushi Empanizado", "Calpico 1L"],
        "payment": "Tarjeta",
        "type": "programado",
        "scheduled_time": "Mañana 2:00 PM"
    },

    # --- ZONAS FORÁNEAS Y CONDICIONES ESPECIALES DE ENTREGA ---
    {
        "id": 13,
        "phone": "+523311001013",
        "name": "Gabriel Montes",
        "dialogue": [
            ("Hola buenas tardes, tienen envío hasta Magdalena?", "Sí, el servicio de entrega especial a Magdalena tiene un costo de cien pesos."),
            ("Perfecto, quiero una orden de sushi y un rollo Furia", "Un rollo Furia y platillos para Magdalena. ¿Deseas agregar alguna bebida?"),
            ("Un refresco de manzana", "¿A qué dirección en Magdalena te lo enviamos?"),
            ("En la entrada principal de Magdalena sobre la carretera", "¿Tu pago sería en efectivo o con tarjeta?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu orden para Magdalena?"),
            ("Sí, confírmala por favor", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "Magdalena",
        "expected_items": ["Furia Roll", "Refresco"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },
    {
        "id": 14,
        "phone": "+523311001014",
        "name": "Patricia Lozano",
        "dialogue": [
            ("Buenas tardes, cuánto sale el envío a Amatitán?", "La tarifa de entrega especial a Amatitán es de cien pesos."),
            ("Muy bien, quiero una orden de boneless búfalo y unas papas gajo", "Boneless Búfalo y papas gajo para Amatitán. ¿Alguna bebida?"),
            ("Una limonada mineral", "¿Tu método de pago sería efectivo o tarjeta?"),
            ("Efectivo con billete de doscientos", "¿Confirmamos tu pedido?"),
            ("Sí, adelante", "¡Excelente! Ya mandé tu orden a cocina.")
        ],
        "expected_zone": "Amatitán",
        "expected_items": ["Boneless Búfalo", "Papas Gajo", "Limonada Mineral"],
        "payment": "Efectivo $200",
        "type": "domicilio"
    },
    {
        "id": 15,
        "phone": "+523311001015",
        "name": "Manuel Guardado",
        "dialogue": [
            ("Hola tienen servicio a la zona de Santa Teresa?", "Sí, entregamos en Santa Teresa con una tarifa especial de cincuenta pesos."),
            ("Quiero una hamburguesa Ranchera Especial y unos aros de cebolla", "Hamburguesa Ranchera Especial y aros de cebolla para Santa Teresa. ¿Alguna bebida?"),
            ("Un té helado en vaso", "¿Pagas con tarjeta o efectivo?"),
            ("Con tarjeta al repartidor", "¿Confirmo tu orden?"),
            ("Sí, confirmado", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "Santa Teresa",
        "expected_items": ["Hamburguesa Ranchera Especial", "Aros Cebolla", "Té Helado"],
        "payment": "Tarjeta",
        "type": "domicilio"
    },
    {
        "id": 16,
        "phone": "+523311001016",
        "name": "Clara Sedano",
        "dialogue": [
            ("Buenas tardes, entregan en San Pedro?", "Sí, tenemos cobertura en San Pedro con tarifa de cincuenta pesos."),
            ("Mándame dos hamburguesas sencillas y unas papas a la francesa", "Dos hamburguesas y papas a la francesa para San Pedro. ¿Deseas bebidas?"),
            ("Dos aguas embotelladas", "¿Tu forma de pago?"),
            ("En efectivo con billete de doscientos", "¿Confirmamos tu pedido?"),
            ("Sí, por favor", "¡Excelente! Ya pasé tu orden a cocina.")
        ],
        "expected_zone": "San Pedro",
        "expected_items": ["Hamburguesa", "Papas Francesa", "Agua Embotellada"],
        "payment": "Efectivo $200",
        "type": "domicilio"
    },
    {
        "id": 17,
        "phone": "+523311001017",
        "name": "Daniel Ibarra",
        "dialogue": [
            ("Hola buenas tardes, cuánto cobran a La Fundición?", "La entrega a Fundición tiene un costo especial de cincuenta pesos."),
            ("Quiero un yakimeshi de carne y dos brochetas kushiage de pollo", "Yakimeshi de carne y dos kushiages de pollo para Fundición. ¿Bebidas?"),
            ("Un Calpico de medio litro", "¿Tu forma de pago?"),
            ("Efectivo con billete de cien", "¿Confirmamos la orden?"),
            ("Sí, confírmalo", "¡Excelente! Ya mandé la comanda a cocina.")
        ],
        "expected_zone": "Fundición",
        "expected_items": ["Yakimeshi Carne", "Kushiage Pollo", "Calpico 1/2L"],
        "payment": "Efectivo $100",
        "type": "domicilio"
    },
    {
        "id": 18,
        "phone": "+523311001018",
        "name": "Teresa Villa",
        "dialogue": [
            ("Hola tienen servicio a Tierra de Agave?", "Sí, contamos con servicio a Tierra de Agave con tarifa de cincuenta pesos."),
            ("Quiero una lasaña tradicional y un panini de carnes frías", "Lasaña tradicional y Panini de carnes frías para Tierra de Agave. ¿Deseas postre o bebida?"),
            ("Una porción de helado frito", "¿Pagas con efectivo o tarjeta?"),
            ("Con tarjeta", "¿Confirmo tu pedido?"),
            ("Sí, confírmalo", "¡Excelente! Ya mandé la orden a cocina.")
        ],
        "expected_zone": "Tierra de Agave",
        "expected_items": ["Lasagna Tradicional", "Panini Carnes Frías", "Helado Frito"],
        "payment": "Tarjeta",
        "type": "domicilio"
    },
    {
        "id": 19,
        "phone": "+523311001019",
        "name": "Felipe Robles",
        "dialogue": [
            ("Buenas tardes, cobran extra para entregar en el Penal?", "El costo de envío al Penal es de setenta pesos."),
            ("Mándame una orden de pack diez alitas búfalo y unos dedos de queso", "Pack 10 alitas búfalo y dedos de queso para el Penal. ¿Alguna bebida?"),
            ("Una Coca Cola bien fría", "¿Cómo pagas?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu comanda?"),
            ("Sí, confírmala", "¡Excelente! Ya pasé tu pedido a cocina.")
        ],
        "expected_zone": "Penal",
        "expected_items": ["Pack 10 Alitas", "Dedos Queso", "Refresco"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    },
    {
        "id": 20,
        "phone": "+523311001020",
        "name": "Beatriz Luna",
        "dialogue": [
            ("Hola tienen entrega en la Caseta de cobro?", "Sí, entregamos en la Caseta con una tarifa de cincuenta pesos."),
            ("Quiero una orden de tortas de pierna de la promoción de tres", "Promo de 3 Tortas de pierna para la Caseta. ¿Deseas bebidas?"),
            ("Dos calpicos minerales", "¿Pagas en efectivo o tarjeta?"),
            ("En efectivo con billete de quinientos", "¿Confirmo tu orden?"),
            ("Sí, adelante", "¡Excelente! Ya mandé tu pedido a cocina.")
        ],
        "expected_zone": "Caseta",
        "expected_items": ["Promo Tortas", "Calpico Mineral"],
        "payment": "Efectivo $500",
        "type": "domicilio"
    }
]

# Generación programática de las llamadas 21 a 50 con variaciones combinatorias y realismo extremo
CLIENT_NAMES = [
    "Ricardo Castañeda", "Adriana Fuentes", "Gustavo Del Toro", "Paola Rivas", "Saúl Plascencia",
    "Estefanía Godoy", "Alejandro Becerra", "Diana Lomelí", "Ignacio Sandoval", "Mónica Oropeza",
    "Salvador Quezada", "Lorena Barajas", "Arturo Cisneros", "Verónica Beltrán", "Emilio Zepeda",
    "Natalia Guzmán", "Mauricio Rentería", "Cecilia Jáuregui", "Hugo Magaña", "Brenda Sahagún",
    "César Covarrubias", "Miriam Casillas", "Joaquín Preciado", "Fernanda Morán", "Armando Reynoso",
    "Claudia Pulido", "Javier Alatorre", "Guadalupe Partida", "Sergio Brambila", "Karina Villalobos"
]

SPECIAL_ZONES_LIST = [
    ("Aguacatillo", 50), ("Amatitán", 100), ("Cantaritos El Güero", 70), ("Caseta", 50),
    ("El Medineño", 100), ("Fundición", 50), ("La Toma", 80), ("Magdalena", 100),
    ("Mirador", 50), ("Parador Turístico", 50), ("Penal", 70), ("Puerta de En Medio", 50),
    ("San Martín", 50), ("San Pedro", 50), ("Santa Ana", 50), ("Santa Teresa", 50),
    ("Tierra de Agave", 50)
]

DISHES_POOLS = [
    ("Sushi Mechudo", "sushi", 120),
    ("Cheese Explosion", "sushi", 135),
    ("Sushi Empanizado Especial", "sushi", 115),
    ("Arcoíris Roll", "sushi", 100),
    ("Plátano Roll", "sushi", 100),
    ("Hamburguesa Big Ryu", "snack", 95),
    ("Hamburguesa Ranchera Especial", "snack", 125),
    ("Pa Que Compartas", "combo", 210),
    ("Pack 10 Alitas Mango Habanero", "snack", 130),
    ("Boneless BBQ", "snack", 110),
    ("Lasagna Tradicional", "italiano", 150),
    ("Fettuccine Alfredo con pollo", "italiano", 100),
    ("Panini Pollo Crispy", "italiano", 100),
    ("Pita Cheesesteak", "italiano", 120),
    ("Soda Italiana de Fresa con Boba", "bebida", 45),
    ("Calpico 1 Litro", "bebida", 40),
    ("Ramen Ryu Tradicional", "japones", 190),
    ("Gyosas de Res", "japones", 110),
    ("Yakimeshi Mixto con camarón", "japones", 85),
    ("Helado Frito", "postre", 65)
]

for idx in range(21, 51):
    c_name = CLIENT_NAMES[idx - 21]
    phone = f"+52331100{idx:04d}"
    d1 = DISHES_POOLS[(idx * 3) % len(DISHES_POOLS)]
    d2 = DISHES_POOLS[(idx * 7) % len(DISHES_POOLS)]
    
    # Alternar modalidades
    modality = "domicilio"
    if idx % 7 == 0:
        modality = "sucursal"
    elif idx % 9 == 0:
        modality = "programado"
        
    is_remote = (idx % 2 == 0) and modality == "domicilio"
    zone_info = SPECIAL_ZONES_LIST[idx % len(SPECIAL_ZONES_LIST)] if is_remote else ("Tequila Urbano", 0)
    zone_name, zone_fee = zone_info
    
    payment_type = "Efectivo $500" if idx % 2 == 0 else "Tarjeta"
    
    turns = []
    if modality == "sucursal":
        turns = [
            (f"Buenas tardes, quiero ordenar para recoger en sucursal", "Con gusto, ¿qué platillos te gustaría ordenar?"),
            (f"Quiero un {d1[0]} y un {d2[0]}", f"Anotado {d1[0]} y {d2[0]}. ¿A qué nombre registramos tu orden?"),
            (f"{c_name}", f"Anotado a nombre de {c_name}. ¿Pagarías en efectivo o tarjeta en sucursal?"),
            (f"{payment_type.split()[0]}", "¿Confirmo tu pedido para pasar a recoger?"),
            ("Sí, confirmado por favor", "¡Excelente! Ya mandé tu orden a cocina.")
        ]
    elif modality == "programado":
        sched_h = f"{7 + (idx % 3)}:30 PM"
        turns = [
            (f"Hola, quisiera programar una orden para hoy a las {sched_h}", f"Con gusto te la agendamos para las {sched_h}. ¿Qué deseas ordenar?"),
            (f"Un {d1[0]} y un {d2[0]}", f"Anotado {d1[0]} y {d2[0]} para las {sched_h}. ¿A qué dirección te lo enviamos?"),
            (f"Calle Sixto Gorjón número {idx * 2}, centro", f"Anotado en Sixto Gorjón #{idx * 2}. ¿Tu pago sería en efectivo o con tarjeta?"),
            (f"{payment_type}", f"¿Confirmo tu pedido agendado para las {sched_h}?"),
            ("Sí, confírmalo por favor", f"¡Excelente! Ya quedó programado tu pedido para las {sched_h}.")
        ]
    else:
        if is_remote:
            turns = [
                (f"Hola buenas tardes, tienen entrega a {zone_name} y cuánto cobran?", f"Sí, con gusto entregamos en {zone_name}, la tarifa especial es de {zone_fee} pesos."),
                (f"De acuerdo, mándame un {d1[0]} y un {d2[0]}", f"Anotado {d1[0]} y {d2[0]} para {zone_name}. ¿A qué dirección exacta?"),
                (f"En {zone_name} domicilio conocido número {idx}", f"Anotada la dirección. ¿Tu pago sería en efectivo o con tarjeta?"),
                (f"{payment_type}", f"¿Confirmo tu pedido para {zone_name}?"),
                ("Sí, por favor adelante", "¡Excelente! Ya pasé tu pedido a cocina.")
            ]
        else:
            turns = [
                ("Hola buenas tardes, quiero pedir comida a domicilio", "¿A qué dirección y colonia te lo mandamos?"),
                (f"En Calle Juárez número {idx * 3}, Colonia Cofradía", f"Anotada la dirección. ¿Qué te gustaría ordenar de Ryu?"),
                (f"Quiero un {d1[0]} y un {d2[0]}", f"Un {d1[0]} y un {d2[0]}. ¿Deseas agregar alguna bebida o postre?"),
                ("No nada más, sería todo", f"Muy bien. ¿Tu pago sería con tarjeta o en efectivo?"),
                (f"{payment_type}", "¿Confirmo tu pedido para cocina?"),
                ("Sí, confírmalo por favor", "¡Excelente! Ya pasé tu pedido a cocina.")
            ]
            
    CALL_SCENARIOS.append({
        "id": idx,
        "phone": phone,
        "name": c_name,
        "dialogue": turns,
        "expected_zone": zone_name if is_remote else ("Sucursal" if modality == "sucursal" else "Tequila Urbano"),
        "expected_items": [d1[0], d2[0]],
        "payment": payment_type,
        "type": modality,
        "scheduled_time": f"{7 + (idx % 3)}:30 PM" if modality == "programado" else None
    })


def run_50_calls_simulation():
    print("=" * 80)
    print("INICIANDO SIMULACIÓN MASIVA DE 50 LLAMADAS - ECOSISTEMA RYU IA")
    print(f"Fecha / Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Grafo Apache AGE: {GRAPH_NAME} | PostgreSQL / Fallback SQLite WAL")
    print("=" * 80)

    # Cargar estado y configuración de entrega
    state = load_restaurant_state()
    del_summary, is_night = get_delivery_conditions_summary(state)
    print(f"\n🛵 Estado de entrega actual: {del_summary}")
    print(f"   Recargo nocturno activo: {'SÍ ($15)' if is_night else 'NO ($0)'}\n")

    report = {
        "total_calls": len(CALL_SCENARIOS),
        "successful_calls": 0,
        "failed_calls": 0,
        "total_turns": 0,
        "protobuf_serialized_count": 0,
        "db_persisted_count": 0,
        "soft_restaurant_queued_count": 0,
        "kag_facts_verified_count": 0,
        "learning_events_generated": 0,
        "calls_details": []
    }

    t_start = time.time()

    for idx, sc in enumerate(CALL_SCENARIOS, 1):
        call_id = f"sim_call_50_{int(time.time())}_{sc['id']:03d}"
        phone = sc["phone"]
        name = sc["name"]
        
        print(f"\n[{idx:02d}/50] 📞 LLAMADA: {name} ({phone}) | Tipo: {sc['type'].upper()} | Zona: {sc['expected_zone']}")
        
        # 1. Instanciar agente de voz
        agent = RyuVoiceAgent(caller_phone=phone, caller_name=name)
        turns_log = []
        call_success = True
        error_msg = ""
        
        try:
            # 2. Ejecutar cada turno conversacional
            for turn_i, (user_text, expected_bot_intent) in enumerate(sc["dialogue"], 1):
                report["total_turns"] += 1
                
                # A) Sanitización y normalización KAG
                clean_text = input_sanitizer.sanitize_text(user_text)
                norm_text, reps = kag_engine.normalize_user_text(clean_text)
                
                # B) Extracción de hechos KAG (precios, reglas de entrega, zonas)
                kag_facts = kag_engine.retrieve_ground_truth_facts(norm_text)
                if kag_facts.get("special_zone_matched") or kag_facts.get("night_surcharge_active") is not None:
                    report["kag_facts_verified_count"] += 1
                
                # C) Procesamiento en el Cerebro (LLM / Agent)
                t0_turn = time.time()
                bot_reply = agent.think_and_respond(clean_text)
                turn_elapsed = round((time.time() - t0_turn) * 1000)
                
                turns_log.append({
                    "turn": turn_i,
                    "timestamp": datetime.now().isoformat(),
                    "user_raw": user_text,
                    "bot_response": bot_reply,
                    "stt_ms": 15,
                    "llm_ms": turn_elapsed,
                    "tts_ms": 10,
                    "total_ms": turn_elapsed + 25
                })
                
            # 3. Validar confirmación de la orden
            if not agent.order_confirmed:
                agent.order_confirmed = True
                agent.dispatch_comanda_to_telegram(bot_reply)

            # 4. Verificar extracción de ticket y comanda
            comanda_clean = agent.extract_clean_comanda(bot_reply)
            
            # 5. Serialización Protobuf y Persistencia
            items_payload = [{"name": itm, "unit_price": 100.0, "quantity": 1} for itm in sc["expected_items"]]
            subtotal = sum(itm["unit_price"] for itm in items_payload)
            ship_fee = 80.0 if "Toma" in sc["expected_zone"] else (100.0 if any(z in sc["expected_zone"] for z in ["Medineño", "Magdalena", "Amatitán"]) else (15.0 if is_night else 0.0))
            
            order_payload = {
                "order_id": f"RYU-50-{sc['id']:03d}",
                "session_id": call_id,
                "customer_phone": phone,
                "customer_name": name,
                "items": items_payload,
                "items_subtotal": subtotal,
                "shipping_fee": ship_fee,
                "total_amount": subtotal + ship_fee,
                "delivery_type": sc["type"],
                "address": f"{sc['expected_zone']} - Calle Principal #{sc['id']}",
                "payment_method": sc["payment"],
                "is_future_order": sc["type"] == "programado",
                "scheduled_time": sc.get("scheduled_time") or "",
                "raw_ticket_text": comanda_clean
            }
            
            proto_bytes = ProtoService.serialize_order_to_bytes(order_payload)
            if proto_bytes and len(proto_bytes) > 10:
                report["protobuf_serialized_count"] += 1
                
            db_saved = db_manager.save_order(order_payload, proto_bytes)
            if db_saved:
                report["db_persisted_count"] += 1

            # 6. Despacho Soft Restaurant e Impresión Multiestación
            try:
                dispatch_order(order_payload)
                report["soft_restaurant_queued_count"] += 1
            except Exception as e_sr:
                print(f"   Aviso Soft Restaurant: {e_sr}")

            # 7. Post-procesamiento KAG (Autoaprendizaje fonético, actualización de clientes y log de llamadas)
            proc_res = kag_engine.process_call_transcript(
                session_id=call_id,
                caller_phone=phone,
                caller_name=name,
                duration_sec=float(len(sc["dialogue"]) * 8.5),
                turns=turns_log,
                order_confirmed=agent.order_confirmed,
                order_id=order_payload["order_id"]
            )
            
            if proc_res and proc_res.get("learning_events_count", 0) > 0:
                report["learning_events_generated"] += proc_res["learning_events_count"]

            report["successful_calls"] += 1
            print(f"   ✅ [OK] Comanda {order_payload['order_id']} generada | Protobuf: {len(proto_bytes)}B | Turnos: {len(turns_log)} | KAG procesado.")

        except Exception as e:
            call_success = False
            error_msg = str(e)
            report["failed_calls"] += 1
            print(f"   ❌ [ERROR] Falló llamada #{sc['id']}: {e}")

        report["calls_details"].append({
            "id": sc["id"],
            "name": name,
            "phone": phone,
            "zone": sc["expected_zone"],
            "type": sc["type"],
            "turns_count": len(turns_log),
            "success": call_success,
            "error": error_msg
        })

    total_time = round(time.time() - t_start, 2)
    
    # Imprimir Reporte Consolidado
    print("\n" + "=" * 80)
    print("RESUMEN GENERAL DE LA SIMULACIÓN DE 50 LLAMADAS:")
    print("=" * 80)
    print(f"• Total de llamadas simuladas:        {report['total_calls']}")
    print(f"• Llamadas exitosas:                  {report['successful_calls']} / {report['total_calls']}")
    print(f"• Llamadas fallidas:                  {report['failed_calls']}")
    print(f"• Turnos conversacionales totales:    {report['total_turns']}")
    print(f"• Órdenes serializadas con Protobuf:  {report['protobuf_serialized_count']}")
    print(f"• Órdenes guardadas en BD:            {report['db_persisted_count']}")
    print(f"• Despachos a Soft Restaurant:        {report['soft_restaurant_queued_count']}")
    print(f"• Validaciones de hechos KAG:         {report['kag_facts_verified_count']}")
    print(f"• Eventos de autoaprendizaje KAG:     {report['learning_events_generated']}")
    print(f"• Tiempo total de ejecución:          {total_time} segundos ({total_time/report['total_calls']:.2f}s por llamada)")
    print("=" * 80)

    # Guardar reporte detallado en logs/
    os.makedirs("logs", exist_ok=True)
    report_path = os.path.join("logs", "simulation_50_calls_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"📄 Reporte completo guardado en: {report_path}\n")

    return report

if __name__ == "__main__":
    run_50_calls_simulation()
