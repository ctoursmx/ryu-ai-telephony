"""
======================================================================
RESTAURANTE RYU - SERVIDOR CENTRAL DE VOZ IA (HUMANA, FLUIDA Y RÁPIDA)
======================================================================
"""

import os
import re
import json
import time
import asyncio
import datetime
import threading
import urllib.request
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import edge_tts
from openai import OpenAI

from kag_engine import kag_engine
from proto_service import ProtoService
from db.graph_db import db_manager
from security_guard import input_sanitizer


# --- CONFIGURACIÓN CENTRAL ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8869418381:AAFQyF_V5hfwJ2HF5isH4WGUZ-17iTQhNzI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-5308916263")
VOICE_NAME = os.getenv("VOICE_NAME", "es-MX-DaliaNeural")

LLM_MODEL = os.getenv("AI_LLM_MODEL", "")

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=3.5, max_retries=1)
    LLM_MODEL = LLM_MODEL or "gpt-4o-mini"
elif GEMINI_API_KEY:
    openai_client = OpenAI(
        api_key=GEMINI_API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=3.5,
        max_retries=1
    )
    LLM_MODEL = LLM_MODEL or "gemini-3.1-flash-lite"
elif GROQ_API_KEY:
    openai_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        timeout=3.5,
        max_retries=1
    )
    LLM_MODEL = LLM_MODEL or "llama-3.3-70b-versatile"
else:
    openai_client = None
    LLM_MODEL = "gemini-3.1-flash-lite"

PROMPT_SNAPPY_PATH = Path(__file__).parent / "prompt_voice_telephone_snappy.md"
PROMPT_FULL_PATH = Path(__file__).parent / "prompt_voice_telephone_ryu.md"
if PROMPT_SNAPPY_PATH.exists():
    SYSTEM_PROMPT = PROMPT_SNAPPY_PATH.read_text(encoding="utf-8")
elif PROMPT_FULL_PATH.exists():
    SYSTEM_PROMPT = PROMPT_FULL_PATH.read_text(encoding="utf-8")
else:
    SYSTEM_PROMPT = "Eres la recepcionista telefónica de Ryu en Tequila. Habla con calidez humana mexicana, sin emojis ni viñetas."

class RyuVoiceAgent:
    def __init__(self, caller_phone="Desconocido", caller_name="Cliente"):
        self.caller_phone = caller_phone
        self.caller_name = caller_name
        self.conversation_history = []
        self.call_turns_log = []
        self.order_confirmed = False
        self.session_id = f"ryu_call_{int(time.time())}_{caller_phone[-4:] if len(caller_phone)>=4 else '0000'}"

        # Consultar perfil en Grafo / DB para clientes recurrentes (dirección, notas, preferencias)
        self.customer_profile = db_manager.get_customer_profile(caller_phone)
        # REGLA ESTRICTA DE TELEFONÍA: Nunca saludar a los clientes por su nombre por teléfono.
        # Siempre mantener un saludo cálido, profesional y neutro.
        self.greeting = "¡Hola, buenas tardes! Gracias por llamar a Ryu en Tequila. ¿Qué te gustaría ordenar hoy?"


    def get_time_and_menu_status(self):
        now = datetime.datetime.now()
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_semana = dias[now.weekday()]
        hora_str = now.strftime("%I:%M %p")
        
        # --- MODO DE PRUEBAS (TODOS LOS MENÚS DISPONIBLES) ---
        # Cambiar a False cuando se pase a producción real con horarios estrictos
        TESTING_MODE_ALL_MENUS = True
        
        if TESTING_MODE_ALL_MENUS:
            estado = "ABIERTO (MODO DE PRUEBAS: Todos los menús y platillos están habilitados para ordenar a cualquier hora)."
            menu_activo = "TODOS DISPONIBLES (Menú Japonés, Menú de Snacks y Menú Italiano)"
            return dia_semana, hora_str, estado, menu_activo
            
        minutos = now.hour * 60 + now.minute
        is_weekend = now.weekday() in [4, 5, 6] # Viernes, Sábado, Domingo
        
        # Horarios oficiales de producción:
        # 1:00 PM (780 min) a 6:30 PM (1110 min): Japonés (+ Italiano si fin de semana)
        # 6:30 PM (1110 min) a 10:30 PM (1350 min): Solo Snacks
        if minutos < 780:
            estado = "CERRADO (El restaurante abre a la 1:00 PM)."
            menu_activo = "Ninguno (Cerrado por el momento)"
        elif 780 <= minutos < 1110:
            if is_weekend:
                estado = "ABIERTO. Menú Japonés Y Menú Italiano activos (hasta las 6:30 PM)."
                menu_activo = "Menú Japonés y Menú Italiano"
            else:
                estado = "ABIERTO. Solo Menú Japonés activo (hasta las 6:30 PM. A partir de las 6:30 PM entra Snacks)."
                menu_activo = "Menú Japonés"
        elif 1110 <= minutos <= 1350:
            estado = "ABIERTO. Solo Menú de Snacks activo (Hamburguesas, Hot Dogs, Boneless, Alitas, Paquetes)."
            menu_activo = "Menú de Snacks"
        else:
            estado = "CERRADO (El restaurante cerró a las 10:30 PM)."
            menu_activo = "Ninguno (Cerrado)"
            
        return dia_semana, hora_str, estado, menu_activo

    def get_current_time_str(self):
        return datetime.datetime.now().strftime("%I:%M %p")

    def detect_future_order(self) -> tuple:
        """Detecta si el pedido es programado / a futuro y extrae la fecha y hora si se especificó."""
        full_dialogue = " ".join([m.get("content", "") for m in self.conversation_history])
        is_future = bool(re.search(r"\b(a futuro|programad[ao]|para ma[ñn]ana|para m[aá]s tarde|para el (?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|para las \d+|a las \d+)\b", full_dialogue, re.IGNORECASE))
        
        m_time = re.search(r"(?:programad[ao]\s+para|para)\s+(?:el\s+)?(ma[ñn]ana(?:\s+a\s+las?\s+[\w:]+(?:\s*(?:am|pm|de la tarde|de la noche))?)?|hoy\s+a\s+las?\s+[\w:]+(?:\s*(?:am|pm|de la tarde|de la noche))?|las?\s+\d+[:\d]*\s*(?:am|pm|de la tarde|de la noche|de la ma[ñn]ana)?|(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)[^\n,.]+)", full_dialogue, re.IGNORECASE)
        scheduled_time = ""
        if m_time:
            scheduled_time = m_time.group(1) if m_time.group(1) else m_time.group(0)
            scheduled_time = re.sub(r"^(?:programad[ao]\s+para\s+|para\s+)", "", scheduled_time, flags=re.IGNORECASE).strip()
        return is_future, scheduled_time

    async def speak(self, text: str, output_audio_path: str = "response.mp3") -> str:
        clean_speech = self.clean_text_for_speech(text)
        communicate = edge_tts.Communicate(clean_speech, VOICE_NAME, rate="+8%", pitch="+0Hz")
        await communicate.save(output_audio_path)
        return output_audio_path

    async def transcribe(self, audio_file_path: str) -> str:
        if openai_client:
            with open(audio_file_path, "rb") as file:
                transcription = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=file,
                    language="es",
                    prompt="Restaurante Ryu en Tequila Jalisco. Pedidos de comida, sushi, hamburguesas, bebidas, paquetes."
                )
                return transcription.text
        return ""

    def think_and_respond(self, user_text: str) -> str:
        # Blindaje de seguridad: Sanitización contra prompt flooding / text bombing
        sanitized_input = input_sanitizer.sanitize_text(user_text, max_chars=350)
        if not sanitized_input.strip():
            return "Disculpa, no alcancé a escucharte bien. ¿Podrías indicarme qué te gustaría ordenar?"

        # Blindaje contra repetición compulsiva / spam
        if input_sanitizer.is_spam_repetition(sanitized_input, self.conversation_history):
            return "Ya registré esa indicación en tu cuenta. ¿Deseas agregar algún otro platillo o bebida?"

        dia, hora, estado, menu_activo = self.get_time_and_menu_status()
        now = datetime.datetime.now()
        is_after_730pm = (now.hour * 60 + now.minute) >= 1170 # 7:30 PM (19:30)
        costo_envio_base = "$15 MXN (Tarifa de envío nocturno activa después de las 7:30 PM)" if is_after_730pm else "$0 MXN (Envío gratis dentro de Tequila antes de las 7:30 PM)"
        
        current_prompt = SYSTEM_PROMPT
                
        # 1. Normalización KAG de fonética y alias aprendidos en el grafo
        clean_user_text, replacements = kag_engine.normalize_user_text(sanitized_input)

        
        # 2. Hechos inmutables desde el Grafo de Conocimiento (KAG Ground Truth)
        kag_facts = kag_engine.retrieve_ground_truth_facts(clean_user_text, now)
        kag_prompt_block = kag_engine.generate_kag_context_prompt(kag_facts, self.customer_profile)
        
        system_context = (
            f"{current_prompt}\n\n"
            f"--- ESTADO EN TIEMPO REAL (TEQUILA, JALISCO) ---\n"
            f"• Día actual: {dia}\n"
            f"• Hora actual: {hora}\n"
            f"• Tarifa de envío estándar actual: {costo_envio_base}\n"
            f"• Estado del local: {estado}\n"
            f"• Menú disponible en este momento: {menu_activo}\n"
            f"--------------------------------------------------\n"
            f"{kag_prompt_block}"
        )
        
        messages = [
            {"role": "system", "content": system_context}
        ]
        
        for msg in self.conversation_history[-10:]:
            messages.append(msg)

        clean_user_text = re.sub(r"\bsucho\b", "sushi", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsuchi\b", "sushi", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsucesos\b", "sushis", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bdos sucesos\b", "dos sushis", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bmora\b", "hola", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\babomicillo\b", "a domicilio", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bguelo\b", "quiero", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bse tenta\b", "setenta", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bdepoyo\b", "de pollo", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bpues no le\b", "ponle", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bdocientos\b", "doscientos", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bun premado\b", "confirmado", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bpremado\b", "confirmado", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcon\s+permado\b", "confirmado", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bdombra\b", "combo", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bconco\s+individual\b|\bconco\b", "combo individual", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bdesiento\b", "doscientos", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bdesientos\b", "doscientos", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bquiniento\b", "quinientos", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcallejera son\b", "calle Zaragoza", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcon\s+el\s+nuevo\s+hecho\b", "con un billete de cien", clean_user_text, flags=re.IGNORECASE)
        
        # Fonética de direcciones, nombres y platillos de Tequila, Jalisco
        clean_user_text = re.sub(r"\bcallejira\s*sol\b", "Calle Girasol", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcalle\s*gira\s*sol\b", "Calle Girasol", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcalles?\s*giraz[oó]n\b", "Calle Girasol", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bgiraz[oó]n\b", "Girasol", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcalles?\s+y\s+raz[oó]n\b|\bcalle\s+raz[oó]n\b", "Calle Girasol", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\b(?:en\s+la\s+)?costrad[ií]a\b", "Colonia Cofradía", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bco?forad[ií]a\b", "Colonia Cofradía", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcontrajeta\b", "con tarjeta", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bpor\s+suave\s+cabr[aá]nes\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsuave\s+cabr[aá]nes\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsuel\s*cabrales\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\brosue\s*cabrales\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bposue\s+cabrales\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bjosue\s+cabrales\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcosme\s+de\s+la\s+verdad\b", "Josué Cabrales", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bla\s*proguesa\b", "la hamburguesa", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bproguesa\b", "hamburguesa", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bd[ií]lan\s*porque\s*esa\b", "di la hamburguesa", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bmatador\s+del\s+interito\b", "adentro", clean_user_text, flags=re.IGNORECASE)
        
        # Fonética de Menú Italiano (Lasaña, Sodas Italianas, Pitas, Paninis)
        clean_user_text = re.sub(r"\b(?:la\s+)?soñada\b", "la lasaña", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bcomo\s+edla\b", "cómo está", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bexplica,\s*me\b", "explícame", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\b(?:de\s+)?todas\s+italianas\b|\btodas\s+italiana\b", "sodas italianas", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\b(?:que\s+es\s+)?a\s*bores\b|\bes\s*a\s*bores\b", "qué sabores", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bfueron\s+cohetan\b|\bcuanto\s+cuentran\b", "cuánto cuestan", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\by\s+hay\s+la\s+compa\b|\by\s+la\s+compa\b|\bla\s+compa\b", "¿qué la acompaña?", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\b(?:una\s+)?gubua\s+de\s+fresas?\b|\b(?:una\s+)?boba\s+de\s+fresas?\b", "soda italiana de fresa con boba", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bgubua\b", "boba", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bpetit\s+chigni\b|\bpetuchini\b|\bpetuccini\b", "fettuccine", clean_user_text, flags=re.IGNORECASE)

        # Fonética de Zonas y Localidades de Envío
        clean_user_text = re.sub(r"\b(?:los\s+)?cantaritos(?:\s+el\s+[gwü]ero)?\b", "Cantaritos El Güero", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\btierra\s+d?e?\s*agave\b", "Tierra de Agave", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bpuerta\s+d?e?\s*en\s*medio\b", "Puerta de En Medio", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bparador\s+tur[ií]stico\b", "Parador Turístico", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsanta\s*ana\b|\bsantaana\b", "Santa Ana", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsanta\s*teresa\b", "Santa Teresa", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsan\s*mart[ií]n\b", "San Martín", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bmedine[ñn]o\b", "Medineño", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\baguacatillo\b", "Aguacatillo", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bamatit[aá]n\b", "Amatitán", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bla\s*fundici[oó]n\b", "Fundición", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bla\s*toma\b", "Toma", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bel\s*mirador\b", "Mirador", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bel\s*penal\b", "Penal", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bla\s*caseta\b", "Caseta", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bsan\s*pedro\b", "San Pedro", clean_user_text, flags=re.IGNORECASE)
        clean_user_text = re.sub(r"\bmagdalena\b", "Magdalena", clean_user_text, flags=re.IGNORECASE)

        # Intentar extraer nombre del cliente del diálogo
        m_name = re.search(r"(?:me llamo|mi nombre es|a nombre de|con|soy|por)\s+([a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ]+)?)", clean_user_text, re.IGNORECASE)
        if m_name and len(m_name.group(1).strip()) > 2 and m_name.group(1).lower() not in ["sushi", "hamburguesa", "coca", "domicilio", "efectivo", "tarjeta", "cambio"]:
            self.caller_name = m_name.group(1).strip().title()
        if "Josué Cabrales" in clean_user_text or "Josue Cabrales" in clean_user_text:
            self.caller_name = "Josué Cabrales"

        messages.append({"role": "user", "content": clean_user_text})
        
        if not openai_client:
            return "Lo siento, hubo un problema con la conexión."

        # Detectar si el usuario está haciendo una pregunta, queja, duda o aclaración
        is_question = bool(re.search(r"(\?|\bqu[eé]\b|\bcu[aá]l\b|\bc[oó]mo\b|\bcu[aá]nto\b|\bcu[aá]nta\b|\bpor\s*qu[eé]\b|\bpero\b|\bespera\b|\bno\b|\bcambia\b|\bqu[ií]t|\bponle\b|\bagr[eé]gale\b|\btiene\b)", clean_user_text, re.IGNORECASE))

        # Palabras de afirmación directa obligatorias para confirmar
        CONFIRM_WORDS = [
            r"\bs[ií]\b",
            r"\bconfirmo\b",
            r"\bconfirmar\b",
            r"\bconfirmado\b",
            r"\bconf[ií]rmalo\b",
            r"\bconf[ií]rmame\b",
            r"\badelante\b",
            r"\bde acuerdo\b",
            r"\bpor favor\b",
            r"\best[aá] bien\b",
            r"\btodo bien\b",
            r"\bas[ií] est[aá] bien\b"
        ]
        is_affirmative = any(re.search(pat, clean_user_text, re.IGNORECASE) for pat in CONFIRM_WORDS)
        
        # Una confirmación NUNCA es una pregunta
        is_confirmation = is_affirmative and not is_question

        # Si el bot ya había preguntado "¿Confirmo tu pedido?" o "¿Confirmamos?" en el turno previo
        # y el cliente confirma de manera explícita y NO está preguntando nada:
        last_bot_msg = self.conversation_history[-1]["content"].lower() if self.conversation_history else ""
        asked_for_confirmation = any(w in last_bot_msg for w in ["confirmo tu pedido", "confirmamos", "te confirmo", "confirmo el pedido"])
        
        if asked_for_confirmation and is_confirmation:
            is_future, sched_time = self.detect_future_order()
            if is_future:
                if sched_time:
                    bot_response = f"¡Excelente! Ya quedó agendado tu pedido para {sched_time}. Lo prepararemos con puntualidad. ¿Deseas ordenar algo más?"
                else:
                    bot_response = "¡Excelente! Ya quedó agendado tu pedido a futuro. Lo prepararemos con puntualidad. ¿Deseas ordenar algo más?"
            else:
                bot_response = "¡Excelente! Ya pasé tu pedido a cocina y te lo llevamos en unos cuarenta a cincuenta minutos. ¿Deseas ordenar algo más?"
            self.conversation_history.append({"role": "user", "content": clean_user_text})
            self.conversation_history.append({"role": "assistant", "content": bot_response})
            self.order_confirmed = True
            self.dispatch_comanda_to_telegram(bot_response)
            return self.clean_text_for_display(bot_response)

        max_toks = 350 if is_confirmation else 240

        response = None
        candidate_models = [LLM_MODEL]
        for alt in ["gemini-3.1-flash-lite", "gemma-4-26b-a4b-it", "gemini-flash-latest"]:
            if alt not in candidate_models:
                candidate_models.append(alt)

        for model_to_try in candidate_models:
            try:
                response = openai_client.chat.completions.create(
                    model=model_to_try,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=max_toks
                )
                if response and response.choices and response.choices[0].message.content:
                    break
            except Exception as e:
                print(f"⚠️ [Aviso LLM {model_to_try}]: {e}. Intentando siguiente modelo...")
                continue
        
        bot_response = response.choices[0].message.content.strip() if (response and response.choices and response.choices[0].message.content) else ""
        if not bot_response:
            bot_response = "Disculpa, ¿me podrías repetir qué se te antoja ordenar? Con gusto te tomo tu pedido."
        
        # 3. Guardián Anti-Alucinación KAG (Auditoría de hechos contra el Grafo)
        bot_response, v_result = kag_engine.audit_and_correct_response(bot_response, kag_facts)
        if v_result.price_corrected:
            print(f"🛡️ [KAG Anti-Alucinación]: Corrección de precios aplicada -> {v_result.discrepancy_reasons}")
            
        # 4. Bucle de Autoaprendizaje Continuo KAG
        kag_engine.learn_from_interaction(
            session_id=self.session_id,
            caller_phone=self.caller_phone,
            user_text=clean_user_text,
            bot_response=bot_response
        )
        
        self.conversation_history.append({"role": "user", "content": clean_user_text})
        self.conversation_history.append({"role": "assistant", "content": bot_response})
        
        # Guardián de confirmación: NUNCA cerrar la llamada si el cliente estaba haciendo una pregunta
        lower_resp = bot_response.lower()

        if any(p in lower_resp for p in ["pasé tu pedido a cocina", "enviado a cocina", "quedó agendado", "quedo agendado", "[comanda]"]):
            if is_question:
                print("🛡️ [Guardián de Confirmación]: El bot intentó confirmar pero el cliente hizo una pregunta. Cancelando confirmación prematura.")
                self.order_confirmed = False
            else:
                self.order_confirmed = True
                self.dispatch_comanda_to_telegram(bot_response)
            
        return self.clean_text_for_display(bot_response)

    def clean_text_for_display(self, raw_text: str) -> str:
        text = raw_text
        if "[CLIENTE]" in text:
            m = re.search(r"\[CLIENTE\]([\s\S]*?)\[/CLIENTE\]", text, re.IGNORECASE)
            if m:
                text = m.group(1)
                
        text = re.sub(r"\[COMANDA\][\s\S]*?\[/COMANDA\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[CLIENTE\]|\[/CLIENTE\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def clean_text_for_speech(self, raw_text: str) -> str:
        text = self.clean_text_for_display(raw_text)
        
        # Eliminar emojis y caracteres no deseados
        text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
        text = re.sub(r"[\u2600-\u26FF\u2700-\u27BF]", "", text)
        
        text = re.sub(r"\$(\d+)", r"\1 pesos", text)
        text = text.replace("MXN", "pesos")
        text = text.replace("*", "")
        text = text.replace("•", "")
        text = text.replace("#", "número ")
        text = text.replace("1x", "una orden de ")
        text = text.replace("2x", "dos órdenes de ")
        text = text.replace("3x", "tres órdenes de ")
        
        # Correcciones fonéticas obligatorias para voz mexicana
        text = re.sub(r"\bRyuBot\b", "Riu Bot", text, flags=re.IGNORECASE)
        text = re.sub(r"\bRyu\b", "Riu", text, flags=re.IGNORECASE)
        text = re.sub(r"\bRyü\b", "Riu", text, flags=re.IGNORECASE)
        text = re.sub(r"\bGyosas\b", "Giosas", text, flags=re.IGNORECASE)
        text = re.sub(r"\bGyosa\b", "Giosa", text, flags=re.IGNORECASE)
        text = re.sub(r"\bKushiage\b", "Kushiague", text, flags=re.IGNORECASE)
        text = re.sub(r"\bKaraage\b", "Karaague", text, flags=re.IGNORECASE)
        text = re.sub(r"\bYakimeshi\b", "Yaquimeshi", text, flags=re.IGNORECASE)
        text = re.sub(r"\bP[.\s]*[ºo]\s*del Centenario\b", "Paseo del Centenario", text, flags=re.IGNORECASE)
        
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def audit_comanda_math(self, text: str) -> str:
        """Garantiza exactitud matemática estricta para Total a cobrar y Cambio en comandas"""
        try:
            item_prices = []
            for line in text.splitlines():
                clean_line = line.strip()
                if any(clean_line.startswith(c) for c in ["•", "-", "*"]):
                    prices = re.findall(r"\$(\d+)", clean_line)
                    if prices:
                        item_prices.append(int(prices[-1]))
            
            shipping = 0
            m_ship = re.search(r"Costo de Env[ií]o:?</b>?\s*\$?(\d+)", text, re.IGNORECASE)
            if m_ship:
                shipping = int(m_ship.group(1))
            
            if item_prices:
                correct_total = sum(item_prices) + shipping
                m_tot = re.search(r"(<b>Total a cobrar:?</b>\s*\$?)(\d+)(\s*MXN)?", text, re.IGNORECASE)
                if m_tot and int(m_tot.group(2)) != correct_total:
                    text = re.sub(r"(<b>Total a cobrar:?</b>\s*\$?)\d+(\s*MXN)?", rf"\g<1>{correct_total}\g<2>", text, flags=re.IGNORECASE)
                elif not m_tot:
                    m_tot2 = re.search(r"(Total a cobrar:?\s*\$?)(\d+)(\s*MXN)?", text, re.IGNORECASE)
                    if m_tot2 and int(m_tot2.group(2)) != correct_total:
                        text = re.sub(r"(Total a cobrar:?\s*\$?)\d+(\s*MXN)?", rf"\g<1>{correct_total}\g<2>", text, flags=re.IGNORECASE)
        except Exception:
            pass
        return text

    def format_comanda_html(self, raw_comanda: str) -> str:
        """Convierte markdown a HTML limpio y estético para Telegram"""
        text = raw_comanda.strip()
        text = re.sub(r"\[/?COMANDA\]", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\[/?CLIENTE\]", "", text, flags=re.IGNORECASE).strip()
        # Eliminar corchetes innecesarios que el LLM pudiera poner en los valores
        text = re.sub(r"\[(Domicilio:[^\]]+)\]", r"\1", text)
        text = re.sub(r"\[(Sucursal:[^\]]+)\]", r"\1", text)
        text = re.sub(r"\[(Efectivo[^\]]*)\]", r"\1", text)
        text = re.sub(r"\[(Tarjeta)\]", r"\1", text)
        # Convertir **negrita** a <b>negrita</b>
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        # Limpiar posibles encabezados repetidos
        text = re.sub(r"^#+.*$", "", text, flags=re.MULTILINE)
        text = self.audit_comanda_math(text)
        return text.strip()

    def extract_clean_comanda(self, bot_response: str) -> str:
        """Garantiza extraer los platillos, precios oficiales exactos, pago y dirección"""
        # 1. Si viene la etiqueta [COMANDA] explícita en la respuesta del bot
        m = re.search(r"\[COMANDA\]([\s\S]*?)\[/COMANDA\]", bot_response, re.IGNORECASE)
        if m and len(m.group(1).strip()) > 15:
            return self.format_comanda_html(m.group(1).strip())
            
        # 2. Si no viene en la última respuesta, buscar en el historial
        for msg in reversed(self.conversation_history):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                m2 = re.search(r"\[COMANDA\]([\s\S]*?)\[/COMANDA\]", content, re.IGNORECASE)
                if m2 and len(m2.group(1).strip()) > 15:
                    return self.format_comanda_html(m2.group(1).strip())
                        
        # 3. Síntesis con modelo inyectando catálogo de precios oficial de Ryu
        try:
            now_dt = datetime.datetime.now()
            is_after_730 = (now_dt.hour * 60 + now_dt.minute) >= 1170
            envio_info = "$15 MXN (Tarifa nocturna activa por ser después de las 7:30 PM)" if is_after_730 else "$0 MXN (Envío gratis antes de 7:30 PM en Tequila urbano)"
            extract_prompt = [
                {
                    "role": "system",
                    "content": (
                        f"Eres el auditor y despachador de comandas de Restaurante Ryu en Tequila.\n"
                        f"INFORMACIÓN EN TIEMPO REAL: Hora actual de la llamada: {now_dt.strftime('%I:%M %p')}. Tarifa de envío estándar actual: {envio_info}.\n"
                        f"Genera el ticket EXACTO para cocina a partir de la conversación.\n\n"
                        "CATÁLOGO OFICIAL DE PRECIOS DE RYU (OBLIGATORIO - NUNCA INVENTES PRECIOS):\n"
                        "• SUSHI Y ROLLOS: Empanizado $95, Philadelphia $95, California $95, Kani $95, Esfera Dragón Ball $95, Avocado $100, Chipotle $100, Arcoiris $100, Hulk $100, Eby $100, Plátano Roll $100, Salmón Roll $105, México Roll $105, Philadelphia Empanizado $105, Furia $105, Pink Salmón $105, Oishi $105, Flamin Hot $105, Masago $110, Empanizado Especial $115, Tocayo $115, Mar y Tierra $115, Mechudo $120, Eby Roll Especial $120, Especial Ryü $120, Especial No. 1 $120, Zizi Roll $130, Hulk Especial $130, Tuna Roll $130, Cheese Explosion $135, Panchito $140, Tocino Roll $150, Tabla de Sushi Mixta $300.\n"
                        "• ENTREMESES, SOPAS Y FUERTES JAPONÉS: Tataki $160, Aguachile (Verde/Negro/Rojo) $170, Rollo Primavera (Verduras/Pollo/Camarón) $100, Gyosas (Res/Camarón) $110, Kushiage Res/Pollo $105, Kushiage Camarón $110, Ensalada Pollo/Res $95, Mariscos $160, Verde $40, Udon $150, Sopa Especial $160, Ramen $190, Sashimi Pescado $100, Res $150, Salmón $170, Pulpo $200, Nigiris Kanikama/Banana $15 c/u, Ebi/Tako/Syake $20 c/u, Yakimeshi Verduras $40, Carne $75, Pollo/Camarón $80, Mixto $85, Tonkotsu $95, Teppanyaki Filete $130, Res $135, Pollo $140, Camarón $145, Mixto $155, Salmón $200, Verduras Salteadas $80, Sakana Furai $135, Ebi Furai $135, Chow Mein $140, Tori Karaage $140, Udon Plancha $140, Milanesa Pollo/Res $140, Brochetas Yakitori $145, Camarones Kimono $145, Camarones Philadelphia $150, Spaguetti Mariscos $150, Tempura Ebi $150, Filete Pescado Especial $150, Ebydon $150, Fire Mixto $150, Filete Pollo Especial $165, Puerquitos Locos $170.\n"
                        "• SNACKS, COMBOS Y PAQUETES: Pack 10 Alitas $130, Pack 15 Alitas $170, Pack 20 Alitas $260, Pack 30 Alitas $390, Promo Hot Dog (3) $70, Combo Nuggets $110, Combo Individual 2 $140, Combo Individual 1 $145, Paquete 3 $150, Combo Ryu Especial $150, Paquete Mix $200, Promo Tortas (3) $200, Pa Que Compartas $210, Caja Ryu Mix $420, Hot Dog clásico $25, Hot Dog Supremo $90, Hot Dog Godzilla $135, Hamburguesa Res/Pollo Plancha $55, Pollo Empanizado $65, Camarón $70, Hawaiana $80, Big Ryu $95, Hamburguesa Especial $100, Cielo Mar y Tierra $120, Ranchera Especial $125, Carolina Especial $125, Torta Telera $90, Papas Francesa $65, Papas Gajo $80, Aros Cebolla $90, Dedos Queso $95, Alitas $100, Boneless $110, Toppings Tocino/Oaxaca $15, Queso Amarillo $5, Cebolla Asada/Jamón $10, Piña/Ranch/Aderezo $20.\n"
                        "• MENÚ ITALIANO: Fettuccine Alfredo $100, Boloñesa $120, Lasagna $150, Panini (cualquier especialidad) $100, Pita (cualquier especialidad) $120 (ambos solos sin papas; especialidades: Bbq, Chipotle, Cheesesteak, Pollo Clásico, Pollo Crispy, Carnes Frías), Ensaladas Italianas Bbq/Chipotle/Cheese-Ranch/Piña Hot/Crispy $110, Toppings Champiñones/Elotes/Cebollita $15 c/u, Sodas Italianas con Boba Fresa/Piña/Mora Azul $45 c/u.\n"
                        "• BEBIDAS Y POSTRES: Refresco $35, Té Vaso $35 / Jarra $100, Limonada/Naranjada $40, Calpico 1/2L $30 / Jarra $110, Calpico 1L $40, Calpico Mineral 1/2L $35 / Jarra $120, Calpico Mineral 1L $45, Calpico Frutos Rojos $40, Michelada $90, Cerveza Corona $40, Botella Agua 500ml $12, Botella Agua 1L $15, Helado Frito $60-$75, Brochetas Plátano $55-$60.\n\n"
                        "REGLAS:\n"
                        "1. NUNCA uses la denominación del billete de pago como precio de un platillo.\n"
                        "2. CALCULA EL TOTAL EXACTO: Suma los precios oficiales de los platillos ordenados MÁS el costo de envío (si aplica) con estricta precisión aritmética (ejemplo: $145 + $40 + $15 = $200 MXN; $100 + $30 = $130 MXN). NUNCA sumes de más.\n"
                        "3. Si paga en efectivo, calcula el cambio exacto: (Billete pagado) - (Total a cobrar).\n"
                        "4. Nombres y Direcciones de Tequila:\n"
                        "   - Si se entendió 'Suave Cabranes', 'Suel Cabrales', 'Rosue', 'Josué' o similar, pon 'Josué Cabrales'.\n"
                        "   - Si la dirección fue 'callejira sol', 'girazón', o 'girasol' pon 'Calle Girasol'.\n"
                        "   - Si mencionaron 'costradía' o 'cofradía', pon 'Colonia Cofradía'.\n"
                        "5. COSTO DE ENVÍO A DOMICILIO:\n"
                        "   - Horario nocturno (después de 7:30 PM): Costo base de $15 pesos a domicilio (antes de 7:30 PM es Gratis dentro de Tequila urbano).\n"
                        "   - Zonas Especiales Foráneas: Aguacatillo $30, Penal $30, Caseta $50, Fundición $50, Toma $80, Mirador $80, Parador Turístico $80, Tierra de Agave $80, San Pedro $100, Santa Ana $100, Medineño $100, Cantaritos El Güero $100, Amatitán $100, Puerta de En Medio $100, San Martín $100, Magdalena $100, Santa Teresa $100.\n"
                        "   - Si es para recoger en sucursal (Paseo del Centenario 27), el envío es $0.\n"
                        "   - Incluye OBLIGATORIAMENTE en la comanda: 🛵 <b>Costo de Envío:</b> $[Monto] MXN (ej. $15 MXN Tarifa nocturna / $30 MXN Zona Aguacatillo / Gratis)\n"
                        "   - SUMA el costo de envío al Total a cobrar: Total = (Platillos y bebidas) + (Costo de envío).\n"
                        "6. NO USES CORCHETES [ ] en el texto generado.\n"
                        "7. REGLA ESTRICTA DE PAQUETES Y COMBOS (NUNCA COBRES ELEMENTOS POR SEPARADO):\n"
                        "   - Si el cliente pide un paquete o combo (ej. Pa Que Compartas, Paquete Mix, Combo Nuggets, Combo Individual 1 o 2, Caja Ryu Mix, etc.):\n"
                        "     El paquete se cobra ÚNICAMENTE a su precio oficial (ej. Pa Que Compartas $210).\n"
                        "     NUNCA cobres los elementos incluidos (alitas, boneless, hamburguesas, aguas) como platillos aparte ni infles el total.\n"
                        "8. NOTAS Y PERSONALIZACIONES PARA COCINA:\n"
                        "   - Si el cliente pide especificaciones ('sin cebolla', 'sin verdura', 'alitas BBQ', 'boneless Mango Habanero', etc.), anótalas como notas al lado del platillo o paquete para que cocina lo prepare exactamente como pidió el cliente.\n\n"
                        "9. PEDIDOS PROGRAMADOS / A FUTURO:\n"
                        "   - Si el pedido fue solicitado para más tarde, para mañana o para una fecha u ocasión futura específica:\n"
                        "     * Incluye OBLIGATORIAMENTE la línea: 🗓️ <b>Tipo de Pedido:</b> PEDIDO A FUTURO\n"
                        "     * Incluye OBLIGATORIAMENTE la línea: ⏰ <b>Fecha y Hora Programada:</b> [Fecha y hora solicitada, ej. Hoy 8:30 PM / Mañana 2:00 PM / Sábado 3:00 PM]\n"
                        "     * En Tiempo de Entrega pon: ⏱️ <b>Tiempo de Entrega:</b> Programado para [Fecha/Hora]\n"
                        "   - Si el pedido es normal e inmediato:\n"
                        "     * ⏱️ <b>Tiempo de Entrega:</b> 40 a 50 min\n\n"
                        "FORMATO EXACTO REQUERIDO:\n"
                        "👤 <b>Cliente:</b> Josué Cabrales\n"
                        "🗓️ <b>Tipo de Pedido:</b> [Omitir si es normal, o poner 'PEDIDO A FUTURO' si es programado]\n"
                        "⏰ <b>Fecha y Hora Programada:</b> [Solo si es pedido a futuro]\n"
                        "📍 <b>Modalidad y Dirección:</b> Domicilio: Calle Girasol #3, Interior 5, Colonia Cofradía\n"
                        "🛵 <b>Costo de Envío:</b> $15 MXN (Tarifa nocturna después de 7:30 PM)\n"
                        "📝 <b>Platillos:</b>\n• 1x Pa Que Compartas: $210 (Alitas BBQ, Boneless Mango Habanero, 1 Hamburguesa sin cebolla, 2 Aguas de Jamaica)\n"
                        "💵 <b>Total a cobrar:</b> $225 MXN\n"
                        "💳 <b>Forma de pago:</b> Tarjeta\n"
                        "⏱️ <b>Tiempo de Entrega:</b> 40 a 50 min (o Programado para Fecha/Hora)"
                    )
                },
                {"role": "user", "content": "\n".join([f"{m['role']}: {m['content']}" for m in self.conversation_history if m.get('content')])}
            ]
            res = None
            for attempt in range(4):
                try:
                    res = openai_client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=extract_prompt,
                        temperature=0.1,
                        max_tokens=350
                    )
                    break
                except Exception as e:
                    if "rate_limit" in str(e).lower() and attempt < 3:
                        time.sleep(2.5 * (attempt + 1))
                    else:
                        raise e
            raw_c = res.choices[0].message.content or bot_response if res else bot_response
            return self.format_comanda_html(raw_c)
        except Exception as e:
            print("Error sintetizando comanda:", e)
            return self.format_comanda_html(bot_response)

    def dispatch_comanda_to_telegram(self, bot_response: str):
        now = datetime.datetime.now().strftime("%d/%m/%Y %I:%M %p")
        comanda_content = self.extract_clean_comanda(bot_response)
        
        # Extraer nombre del cliente de la comanda si está disponible
        m_name = re.search(r"Cliente:?\s*</b>?\s*([^\n\r<]+)", comanda_content, re.IGNORECASE)
        if m_name and m_name.group(1).strip() and "cliente telefonico" not in m_name.group(1).lower() and "por confirmar" not in m_name.group(1).lower():
            self.caller_name = m_name.group(1).strip()
            
        # Remover la línea redundante de Cliente de comanda_content si ya va en el encabezado
        comanda_clean = re.sub(r"👤?\s*<b>Cliente:?</b>\s*[^\n\r]+\n?", "", comanda_content, flags=re.IGNORECASE).strip()
        comanda_clean = re.sub(r"👤?\s*Cliente:?\s*[^\n\r]+\n?", "", comanda_clean, flags=re.IGNORECASE).strip()
            
        is_future, sched_time = self.detect_future_order()
        is_future_order = "PEDIDO A FUTURO" in comanda_clean.upper() or is_future

        if is_future_order:
            header = "🗓️ <b>NUEVO PEDIDO A FUTURO - RYU</b> 🍣"
            status = "⏳ <b>Estado:</b> 🔵 PEDIDO A FUTURO (Programado)"
            # Asegurar distinción explícita de PEDIDO A FUTURO
            if "PEDIDO A FUTURO" not in comanda_clean.upper():
                comanda_clean = f"🗓️ <b>Tipo de Pedido:</b> PEDIDO A FUTURO\n" + comanda_clean
            if "Fecha y Hora Programada:" not in comanda_clean and sched_time:
                comanda_clean = f"⏰ <b>Fecha y Hora Programada:</b> {sched_time.title()}\n" + comanda_clean
        else:
            header = "📞 <b>NUEVO PEDIDO POR LLAMADA TELEFÓNICA - RYU</b> 🍣"
            status = "⏳ <b>Estado:</b> 🟡 En Espera de Preparación"

        ticket = (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Fecha de Llamada:</b> {now}\n"
            f"👤 <b>Cliente:</b> {self.caller_name}\n"
            f"📱 <b>Teléfono:</b> {self.caller_phone}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{comanda_clean}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{status}"
        )
        
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": ticket,
            "parse_mode": "HTML"
        }).encode("utf-8")
        
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                print(">>> Comanda enviada a Telegram con éxito.")
        except Exception as e:
            print(f">>> Error enviando a Telegram: {e}")

        # 5. Serialización Protobuf y Persistencia en PostgreSQL / Apache AGE
        try:
            m_tot = re.search(r"Total a cobrar:?\s*</b>?\s*\$?(\d+)", comanda_clean, re.IGNORECASE)
            tot_val = float(m_tot.group(1)) if m_tot else 0.0

            m_ship = re.search(r"Costo de Env[ií]o:?\s*</b>?\s*\$?(\d+)", comanda_clean, re.IGNORECASE)
            ship_val = float(m_ship.group(1)) if m_ship else 0.0

            m_addr = re.search(r"Modalidad y Direcci[oó]n:?\s*</b>?\s*([^\n\r]+)", comanda_clean, re.IGNORECASE)
            addr_val = m_addr.group(1).strip() if m_addr else ""

            m_pay = re.search(r"Forma de pago:?\s*</b>?\s*([^\n\r]+)", comanda_clean, re.IGNORECASE)
            pay_val = m_pay.group(1).strip() if m_pay else "Efectivo"

            # Parsear items individuales
            items_list = []
            for line in comanda_clean.splitlines():
                if line.strip().startswith("•") or line.strip().startswith("-"):
                    item_name_m = re.search(r"[•\-]\s*(?:\d+x\s*)?([^:$]+)", line)
                    price_m = re.search(r"\$(\d+)", line)
                    if item_name_m and price_m:
                        items_list.append({
                            "name": item_name_m.group(1).strip(),
                            "unit_price": float(price_m.group(1)),
                            "quantity": 1,
                            "notes": line.strip()
                        })

            order_payload = {
                "order_id": f"RYU-{int(time.time())}",
                "session_id": self.session_id,
                "customer_phone": self.caller_phone,
                "customer_name": self.caller_name,
                "items": items_list,
                "items_subtotal": max(0.0, tot_val - ship_val),
                "shipping_fee": ship_val,
                "total_amount": tot_val,
                "delivery_type": "domicilio" if "domicilio" in addr_val.lower() else "sucursal",
                "address": addr_val,
                "payment_method": pay_val,
                "is_future_order": is_future_order,
                "scheduled_time": sched_time if is_future_order else "",
                "raw_ticket_text": ticket
            }

            proto_bytes = ProtoService.serialize_order_to_bytes(order_payload)
            db_saved = db_manager.save_order(order_payload, proto_bytes)
            if db_saved:
                print(f"📦 [Protobuf + DB]: Comanda {order_payload['order_id']} serializada ({len(proto_bytes)} bytes) y persistida exitosamente.")

            # 6. Despacho Soft Restaurant (SQL Server) + Impresión Multiestación y Comanda Prioridad IA
            try:
                from soft_restaurant_bridge import dispatch_order
                # Despacho en segundo plano para no demorar la respuesta de audio al cliente
                threading.Thread(
                    target=dispatch_order,
                    args=(order_payload,),
                    daemon=True,
                    name=f"dispatch-{order_payload['order_id']}"
                ).start()
                print(f"🚀 [Soft Restaurant & Comandas]: Despacho en segundo plano iniciado para comanda {order_payload['order_id']}.")
            except Exception as err_sr:
                print(f"⚠️ Aviso despachando a Soft Restaurant / Comandas: {err_sr}")
        except Exception as err_db:
            print(f"Aviso guardando comanda en base de datos: {err_db}")

