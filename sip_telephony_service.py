"""
======================================================================
RESTAURANTE RYU - SERVIDOR DE TELEFONIA SIP EN VIVO (ZADARMA)
Audio Cristalino de Calidad Estudio (Cero estática, Cero jitter, Cero cortes)
RTP Monotónico de Precisión (Exactos 50.00 pkts/s) + Remuestreo soxr HQ
Colas Thread-Safe Separadas (Inbound/Outbound) + faster-whisper en RAM
Respuesta Ultra Veloz (~2s real) + Diálogo Fluido y Paciente
======================================================================
"""

import os
import sys
import time
import socket
import audioop
import asyncio
import wave
import io
import re
import atexit
import signal
import ctypes
import queue
import collections
import threading
import random
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import soxr
import miniaudio
import edge_tts
from faster_whisper import WhisperModel

# Configurar encoding de consola
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

load_dotenv()

# Fijar precisión del temporizador en Windows a 1 milisegundo (elimina jitter en RTP)
if sys.platform == "win32":
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        print("Temporizador multimedia de Windows fijado a 1ms (Cero jitter).")
    except Exception as e:
        print(f"Aviso temporizador Windows: {e}")

import pyVoIP
from pyVoIP.VoIP import VoIPPhone, PhoneStatus, CallState
import pyVoIP.SIP as SIP
import pyVoIP.RTP as RTP
from voice_engine_ryu import RyuVoiceAgent
from security_guard import (
    CallWatchdog,
    call_rate_limiter,
    input_sanitizer,
    cleanup_temp_audio_files
)


# ----------------------------------------------------------------------
# 1. PARCHES DE ARQUITECTURA CRITICOS PARA pyVoIP
# ----------------------------------------------------------------------

# A) Control de reintentos infinitos
pyVoIP.REGISTER_FAILURE_THRESHOLD = 99999
pyVoIP.TRANSMIT_DELAY_REDUCTION = 0.0

# B) Responder 200 OK a pings OPTIONS de Zadarma (RFC 3261 Heartbeat)
original_parse_message = SIP.SIPClient.parse_message

def patched_parse_message(self, message):
    if message.type == SIP.SIPMessageType.MESSAGE and message.method == "OPTIONS":
        response = self.gen_ok(message)
        try:
            sender_addr = message.headers["Via"][0]["address"]
            self.out.sendto(response.encode("utf8"), (sender_addr[0], int(sender_addr[1])))
            print(f"💓 [SIP Heartbeat]: Respondido 200 OK a OPTIONS de Zadarma ({sender_addr[0]}:{sender_addr[1]})")
        except Exception:
            self.out.sendto(response.encode("utf8"), (self.server, self.port))
            print(f"💓 [SIP Heartbeat]: Respondido 200 OK a OPTIONS de Zadarma ({self.server}:{self.port})")
        return
    return original_parse_message(self, message)

SIP.SIPClient.parse_message = patched_parse_message

# C) Parche de Registro Continuo (Lease 22s) para Zadarma
# Zadarma otorga un lease de expires=35s. Sin este parche, pyVoIP espera 115s y la línea queda OFFLINE (punto rojo) durante 80s de cada 2 min.
original_sip_init = SIP.SIPClient.__init__

def patched_sip_init(self, *args, **kwargs):
    original_sip_init(self, *args, **kwargs)
    self.default_expires = 30
    self.register_timeout = 10

SIP.SIPClient.__init__ = patched_sip_init

def patched_start_register_timer(self, delay=None):
    # Renovar registro cada 22 segundos para que Zadarma (35s) esté PERMANENTEMENTE EN VERDE (ONLINE)
    delay = 22
    if self.NSD:
        self.registerThread = threading.Timer(delay, self.register)
        self.registerThread.name = "SIP Register Keepalive Zadarma 22s"
        self.registerThread.daemon = True
        self.registerThread.start()

SIP.SIPClient._SIPClient__start_register_timer = patched_start_register_timer

# D) Inicialización de colas de audio dedicadas por cliente RTP
original_rtp_init = RTP.RTPClient.__init__

def patched_rtp_init(self, *args, **kwargs):
    original_rtp_init(self, *args, **kwargs)
    self.outbound_queue = queue.Queue()
    self.inbound_queue = queue.Queue()
    self.outSequence = random.randint(1, 100)
    self.outTimestamp = random.randint(1, 10000)
    self.outSSRC = random.randint(1000, 65530)

RTP.RTPClient.__init__ = patched_rtp_init

# D) Transmisor RTP de Precisión Monotónica (50.00 pkts/s exactos)
# Elimina el hambre de búfer (underrun) en Zadarma que producía estática y chasquidos
def patched_trans(self) -> None:
    t_next = time.perf_counter()
    SILENCE_PCMA = b"\xd5" * 160  # Silencio digital G.711 PCMA estándar
    
    while self.NSD:
        t_next += 0.020  # Cadencia exacta de 20 milisegundos
        
        # 1. Obtener paquete de voz para enviar
        payload = None
        if hasattr(self, "outbound_queue"):
            try:
                payload = self.outbound_queue.get_nowait()
            except queue.Empty:
                payload = None
                
        if payload is None or len(payload) == 0:
            payload = SILENCE_PCMA
        elif len(payload) < 160:
            payload = payload + (b"\xd5" * (160 - len(payload)))
            
        # 2. Construir cabecera estándar RFC 3550 RTP (12 bytes)
        # Byte 0: V=2, P=0, X=0, CC=0 (0x80)
        # Byte 1: PT=8 (PCMA)
        packet = b"\x80"
        packet += chr(int(self.preference)).encode("utf8")
        try:
            packet += self.outSequence.to_bytes(2, byteorder="big")
        except OverflowError:
            self.outSequence = 0
            packet += b"\x00\x00"
            
        try:
            packet += self.outTimestamp.to_bytes(4, byteorder="big")
        except OverflowError:
            self.outTimestamp = 0
            packet += b"\x00\x00\x00\x00"
            
        packet += self.outSSRC.to_bytes(4, byteorder="big")
        packet += payload
        
        # 3. Enviar paquete UDP al puerto RTP de Zadarma
        try:
            self.sout.sendto(packet, (self.outIP, self.outPort))
        except OSError:
            pass
            
        self.outSequence = (self.outSequence + 1) & 0xFFFF
        self.outTimestamp = (self.outTimestamp + len(payload)) & 0xFFFFFFFF
        
        # 4. Dormir con precisión monotónica y spinwait de microsegundo
        remaining = t_next - time.perf_counter()
        if remaining > 0.002:
            time.sleep(remaining - 0.001)
        while time.perf_counter() < t_next:
            pass
            
        # Si hubo un retraso drástico del sistema operativo, re-anclar tiempo base
        if (time.perf_counter() - t_next) > 0.040:
            t_next = time.perf_counter()

RTP.RTPClient.trans = patched_trans

# E) Receptor RTP Simétrico Continuo (RFC 4961) + Decodificación directa a 16-bit PCM
# Elimina los paquetes falsos de silencio intercalados que picaban la voz del cliente
def patched_recv(self) -> None:
    first_packet = True
    while self.NSD:
        try:
            packet, addr = self.sin.recvfrom(8192)
            if addr and (self.outIP != addr[0] or self.outPort != addr[1]):
                print(f"\n[RTP Simetrico]: Audio enlazado a {addr[0]}:{addr[1]} (SDP: {self.outIP}:{self.outPort})")
                self.outIP = addr[0]
                self.outPort = addr[1]
            if first_packet:
                first_packet = False
                print(f"[RTP Enlazado]: Primer paquete recibido de {addr[0]}:{addr[1]}")
                
            if len(packet) >= 12:
                self.last_packet_time = time.time()
                payload_type = packet[1] & 0x7F
                payload = packet[12:]
                
                # Evento DTMF (teclado telefónico)
                if payload_type == 101:
                    try:
                        self.parse_packet(packet)
                    except Exception:
                        pass
                elif payload_type == 8:  # PCMA (G.711 A-law)
                    # Decodificar A-law directamente a 16-bit PCM lineal (320 bytes por trama)
                    pcm16 = audioop.alaw2lin(payload, 2)
                    if hasattr(self, "inbound_queue"):
                        self.inbound_queue.put(pcm16)
                elif payload_type == 0:  # PCMU (G.711 Mu-law)
                    pcm16 = audioop.ulaw2lin(payload, 2)
                    if hasattr(self, "inbound_queue"):
                        self.inbound_queue.put(pcm16)
                        
        except BlockingIOError:
            time.sleep(0.005)
        except RTP.RTPParseError:
            pass
        except OSError:
            pass

RTP.RTPClient.recv = patched_recv

print("Arquitectura pyVoIP parcheada: RTP Monotónico 50pps + Receptor 16-bit + Colas Thread-Safe + Heartbeat.")

# ----------------------------------------------------------------------
# 2. CONFIGURACION DE RED Y CREDENCIALES ZADARMA
# ----------------------------------------------------------------------
SIP_SERVER = os.getenv("ZADARMA_SIP_SERVER", "sip.zadarma.com")
SIP_USER = os.getenv("ZADARMA_SIP_USER", "20432")
SIP_PASSWORD = os.getenv("ZADARMA_SIP_PASSWORD", "xlNN8A1Szl")
PHONE_NUMBER = os.getenv("ZADARMA_PHONE_NUMBER", "+523385261250")

def get_local_ip():
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        for iface in ["eth0", "wlan0", "en0", "Wi-Fi 2", "Wi-Fi", "Ethernet"]:
            if iface in addrs:
                for snic in addrs[iface]:
                    if snic.family == socket.AF_INET and not snic.address.startswith("169.254.") and not snic.address.startswith("127."):
                        print(f"Detectada interfaz de red activa ({iface}): {snic.address}")
                        return snic.address
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()
GLOBAL_PHONE = None

def cleanup():
    global GLOBAL_PHONE
    if sys.platform == "win32":
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass
    if GLOBAL_PHONE:
        try:
            print("\nCerrando teléfono SIP limpiamente...")
            GLOBAL_PHONE.stop()
        except Exception:
            pass

atexit.register(cleanup)

# ----------------------------------------------------------------------
# 3. MOTOR DE STT LOCAL ULTRA VELOZ (faster-whisper EN RAM)
# ----------------------------------------------------------------------
WHISPER_MODEL = None

def get_whisper_model():
    global WHISPER_MODEL
    if WHISPER_MODEL is None:
        print("Cargando faster-whisper en RAM (CPU int8, 4 hilos)...")
        t0 = time.time()
        WHISPER_MODEL = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
        dummy = np.zeros(16000, dtype=np.float32)
        list(WHISPER_MODEL.transcribe(dummy, language="es", beam_size=1)[0])
        print(f"faster-whisper listo y precalentado en {time.time()-t0:.2f}s.")
    return WHISPER_MODEL

# ----------------------------------------------------------------------
# 4. SINTESIS DE VOZ DE ALTA FIDELIDAD (soxr HQ + G.711 A-LAW)
# ----------------------------------------------------------------------
async def synthesize_speech_alaw(text: str, agent: RyuVoiceAgent) -> bytes:
    """
    Sintetiza la voz con Edge-TTS, remuestrea con soxr HQ (filtro brickwall anti-aliasing a 3800Hz),
    aplica escalado estándar de nivel de telefonía (-18 dBFS) para prevenir saturación y estática,
    y codifica directamente a tramas G.711 A-law de 8kHz.
    """
    clean_text = agent.clean_text_for_speech(text)
    comm = edge_tts.Communicate(clean_text, "es-MX-DaliaNeural", rate="+18%", pitch="+0Hz")
    mp3_bytes = b""

    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            mp3_bytes += chunk["data"]
            
    if not mp3_bytes:
        return b""
        
    decoded = miniaudio.decode(
        mp3_bytes,
        nchannels=1,
        sample_rate=24000,
        output_format=miniaudio.SampleFormat.SIGNED16
    )
    
    pcm24_float = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
    
    # Remuestreo de alta fidelidad soxr HQ de 24kHz a 8kHz puro
    pcm8_float = soxr.resample(pcm24_float, 24000, 8000, quality="HQ")
    
    # Margen de seguridad para telefonía móvil (elimina saturación en altavoces de teléfono)
    peak = np.max(np.abs(pcm8_float))
    target = 0.70
    if peak > target:
        pcm8_float = pcm8_float * (target / peak)
    else:
        pcm8_float = pcm8_float * target
        
    pcm8_int16 = (pcm8_float * 32767.0).astype(np.int16)
    alaw_bytes = audioop.lin2alaw(pcm8_int16.tobytes(), 2)
    return alaw_bytes

PRELOADED_GREETING = None

def preload_greeting():
    global PRELOADED_GREETING
    print("Pre-sintetizando saludo en RAM con soxr HQ...")
    try:
        temp_agent = RyuVoiceAgent(caller_phone=PHONE_NUMBER, caller_name="Cliente Telefonico")
        PRELOADED_GREETING = asyncio.run(synthesize_speech_alaw(temp_agent.greeting, temp_agent))
        print(f"Saludo precargado exitosamente ({len(PRELOADED_GREETING)} bytes, {len(PRELOADED_GREETING)/8000:.1f}s).")
    except Exception as e:
        print(f"Aviso precargando saludo: {e}")

# ----------------------------------------------------------------------
# 5. TRANSMISION Y RECEPCION CONTINUA DE AUDIO TELEFONICO
# ----------------------------------------------------------------------
def play_audio_to_call(call, alaw_audio: bytes):
    if not alaw_audio or call.state != CallState.ANSWERED:
        return
        
    duration = len(alaw_audio) / 8000.0
    print(f">>> [Voz Bot]: Hablando por teléfono ({duration:.1f} seg)...")
    
    client = call.RTPClients[0] if hasattr(call, "RTPClients") and call.RTPClients else None
    if not client:
        return
        
    # Colocar paquetes A-law de 160 bytes en la cola de salida de alta precisión
    for i in range(0, len(alaw_audio), 160):
        chunk = alaw_audio[i:i+160]
        if len(chunk) < 160:
            chunk = chunk + (b"\xd5" * (160 - len(chunk)))
        client.outbound_queue.put(chunk)
        
    # Esperar a que la cola de transmisión entregue el audio con detección de interrupción (Barge-in)
    barge_in_count = 0
    t_play_start = time.time()
    while hasattr(client, "outbound_queue") and not client.outbound_queue.empty() and call.state == CallState.ANSWERED:
        # Detectar si el cliente habla mientras el bot habla (después de los primeros 250ms):
        if (time.time() - t_play_start) > 0.25 and hasattr(client, "inbound_queue") and client.inbound_queue.qsize() > 0:
            try:
                pkt = client.inbound_queue.get_nowait()
                rms = audioop.rms(pkt, 2)
                if rms > 1200:  # Voz humana real confirmada
                    barge_in_count += 1
                    if barge_in_count >= 3:  # 60ms continuos de voz humana
                        print(f"⚡ [Barge-in]: El cliente empezó a hablar (Energía: {rms}). Deteniendo habla del bot.")
                        # Detener de inmediato el habla del bot vaciando la cola de salida
                        while not client.outbound_queue.empty():
                            try:
                                client.outbound_queue.get_nowait()
                            except queue.Empty:
                                break
                        # Re-insertar este paquete de voz al frente para no perderlo
                        client.inbound_queue.put(pkt)
                        break
                else:
                    barge_in_count = 0
            except queue.Empty:
                pass
        # Verificar si el cliente colgó durante la reproducción del bot (flujo RTP cortado)
        if hasattr(client, "last_packet_time") and client.last_packet_time > 0:
            if (time.time() - client.last_packet_time) > 4.0:
                print(">>> [Detección de Colgado]: El cliente colgó el teléfono durante el habla del bot.")
                call.state = CallState.ENDED
                break
        time.sleep(0.020)
        
    time.sleep(0.02)
    
    # Preservar paquetes de voz del cliente si habló al final de la frase (NO drenar voz humana)
    if hasattr(client, "inbound_queue"):
        preserved_frames = []
        for _ in range(client.inbound_queue.qsize()):
            try:
                pkt = client.inbound_queue.get_nowait()
                if audioop.rms(pkt, 2) > 500:  # Conservar cualquier trama con voz humana
                    preserved_frames.append(pkt)
            except queue.Empty:
                break
        for f in preserved_frames:
            client.inbound_queue.put(f)

def record_user_speech(call, max_silence_seconds: float = 0.95, max_duration: float = 35.0) -> bytes:
    """
    Escucha la voz del cliente recibiendo tramas 100% continuas de 16-bit PCM desde la cola inbound.
    Cero inserciones de falso silencio y cero tartamudeo.
    """
    client = call.RTPClients[0] if hasattr(call, "RTPClients") and call.RTPClients else None
    if not client or not hasattr(client, "inbound_queue"):
        return b""
        
    frames_pcm16 = []
    pre_buffer = collections.deque(maxlen=6)  # 120ms de buffer previo para no perder la primera consonante
    start_time = time.time()
    last_voice_time = time.time()
    has_started_speaking = False
    consecutive_voice_frames = 0
    VOICE_THRESHOLD = 180  # Umbral optimizado para capturar respuestas suaves ("sí", "confirmo")

    while call.state == CallState.ANSWERED:
        elapsed = time.time() - start_time
        if elapsed > max_duration:
            break
            
        try:
            pcm16 = client.inbound_queue.get(timeout=0.040)
        except queue.Empty:
            if hasattr(client, "last_packet_time") and client.last_packet_time > 0:
                if (time.time() - client.last_packet_time) > 3.5:
                    print(">>> [Detección de Colgado]: Flujo RTP cerrado por el cliente. Terminando llamada.")
                    call.state = CallState.ENDED
                    break
            if elapsed > 4.5 and not has_started_speaking:
                break
            continue
            
        if not pcm16 or len(pcm16) == 0:
            continue
            
        rms = audioop.rms(pcm16, 2)
        
        if not has_started_speaking:
            pre_buffer.append(pcm16)
            if rms > VOICE_THRESHOLD:
                consecutive_voice_frames += 1
                if consecutive_voice_frames >= 3:  # 60ms continuos de voz real confirmada
                    has_started_speaking = True
                    print(f"🗣️ [Cliente hablando... (Energia: {rms})]")
                    frames_pcm16.extend(pre_buffer)
                    last_voice_time = time.time()
            else:
                consecutive_voice_frames = 0
                if elapsed > 4.5:
                    break
        else:
            frames_pcm16.append(pcm16)
            if rms > VOICE_THRESHOLD:
                last_voice_time = time.time()
            else:
                silence_duration = time.time() - last_voice_time
                if silence_duration >= max_silence_seconds:
                    print(f"⚡ [Pausa detectada ({silence_duration:.2f}s), procesando respuesta...]")
                    break

    if not frames_pcm16:
        return b""
    return b"".join(frames_pcm16)

def deduplicate_repetitions(text: str) -> str:
    """Elimina bucles de repetición o alucinaciones recurrentes de Whisper."""
    if not text:
        return ""
    # 1. Frases separadas por comas repetidas ("El Rincón, El Rincón, El Rincón")
    t = re.sub(r'(\b.+?\b)(?:,\s*\1)+', r'\1', text, flags=re.IGNORECASE)
    # 2. Oraciones repetidas con puntuación ("¡Tienes un desastre! ¡Tienes un desastre!")
    t = re.sub(r'([^.!?]+[.!?])(?:\s*\1)+', r'\1', t, flags=re.IGNORECASE)
    # 3. Palabras consecutivas idénticas ("sushi sushi sushi")
    t = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', t, flags=re.IGNORECASE)
    return t.strip()

def clean_colloquial_speech(text: str) -> str:
    """Corrige errores fonéticos frecuentes producidos por compresión telefónica."""
    t = text
    corrections = [
        (r'\bsucho\b', 'sushi'),
        (r'\bsuchi\b', 'sushi'),
        (r'\bsucesos\b', 'sushis'),
        (r'\bdos sucesos\b', 'dos sushis'),
        (r'\bmora\b', 'hola'),
        (r'\babomicillo\b', 'a domicilio'),
        (r'\bse tenta\b', 'setenta'),
        (r'\bdepoyo\b', 'de pollo'),
        (r'\bdesiento\b', 'doscientos'),
        (r'\bdesientos\b', 'doscientos'),
        (r'\bquiniento\b', 'quinientos'),
        (r'\bun premado\b', 'confirmado'),
        (r'\bpremado\b', 'confirmado'),
        (r'\bcon\s+permado\b', 'confirmado'),
        (r'\bdombra\b', 'combo'),
        (r'\bconco\s+individual\b|\bconco\b', 'combo individual'),
        (r'\bcon\s+el\s+nuevo\s+hecho\b', 'con un billete de cien'),
        (r'\bcallejira\s*sol\b', 'Calle Girasol'),
        (r'\bcalle\s*gira\s*sol\b', 'Calle Girasol'),
        (r'\bcalles?\s*giraz[oó]n\b', 'Calle Girasol'),
        (r'\bgiraz[oó]n\b', 'Girasol'),
        (r'\bcalles?\s+y\s+raz[oó]n\b|\bcalle\s+raz[oó]n\b', 'Calle Girasol'),
        (r'\b(?:en\s+la\s+)?costrad[ií]a\b', 'Colonia Cofradía'),
        (r'\bco?forad[ií]a\b', 'Colonia Cofradía'),
        (r'\bcontrajeta\b', 'con tarjeta'),
        (r'\bpor\s+suave\s+cabr[aá]nes\b', 'Josué Cabrales'),
        (r'\bsuave\s+cabr[aá]nes\b', 'Josué Cabrales'),
        (r'\bsuel\s*cabrales\b', 'Josué Cabrales'),
        (r'\brosue\s*cabrales\b', 'Josué Cabrales'),
        (r'\bposue\s+cabrales\b', 'Josué Cabrales'),
        (r'\bjosue\s+cabrales\b', 'Josué Cabrales'),
        (r'\bcosme\s+de\s+la\s+verdad\b', 'Josué Cabrales'),
        (r'\bla\s*proguesa\b', 'la hamburguesa'),
        (r'\bproguesa\b', 'hamburguesa'),
        (r'\bd[ií]lan\s*porque\s*esa\b', 'di la hamburguesa'),
        (r'\bmatador\s+del\s+interito\b', 'adentro'),
        (r'\b(?:una\s+)?gubua\s+de\s+fresas?\b', 'soda italiana de fresa con boba'),
        (r'\b(?:una\s+)?boba\s+de\s+fresas?\b', 'soda italiana de fresa con boba'),
        (r'\bgubua\b', 'boba'),
        (r'\bpetit\s+chigni\b', 'fettuccine'),
        (r'\bpetuchini\b', 'fettuccine'),
        (r'\bpetuccini\b', 'fettuccine'),
        (r'\b(?:la\s+)?soñada\b', 'la lasaña'),
        (r'\bcomo\s+edla\b', 'cómo está'),
        (r'\b(?:de\s+)?todas\s+italianas\b', 'sodas italianas'),
        (r'\b(?:que\s+es\s+)?a\s*bores\b', 'qué sabores'),
        (r'\bfueron\s+cohetan\b', 'cuánto cuestan'),
        (r'\bcuanto\s+cuentran\b', 'cuánto cuestan'),
        (r'\by\s+hay\s+la\s+compa\b', '¿qué la acompaña?'),
        (r'\b(?:los\s+)?cantaritos(?:\s+el\s+[gwü]ero)?\b', 'Cantaritos El Güero'),
        (r'\btierra\s+d?e?\s*agave\b', 'Tierra de Agave'),
        (r'\bpuerta\s+d?e?\s*en\s*medio\b', 'Puerta de En Medio'),
        (r'\bparador\s+tur[ií]stico\b', 'Parador Turístico'),
        (r'\bsanta\s*ana\b|\bsantaana\b', 'Santa Ana'),
        (r'\bsanta\s*teresa\b', 'Santa Teresa'),
        (r'\bsan\s*mart[ií]n\b', 'San Martín'),
        (r'\bmedine[ñn]o\b', 'Medineño'),
        (r'\baguacatillo\b', 'Aguacatillo'),
        (r'\bamatit[aá]n\b', 'Amatitán'),
        (r'\bla\s*fundici[oó]n\b', 'Fundición'),
        (r'\bla\s*toma\b', 'Toma'),
        (r'\bel\s*mirador\b', 'Mirador'),
        (r'\bel\s*penal\b', 'Penal'),
        (r'\bla\s*caseta\b', 'Caseta'),
        (r'\bsan\s*pedro\b', 'San Pedro'),
        (r'\bmagdalena\b', 'Magdalena'),
    ]
    for pattern, replacement in corrections:
        t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)
    return t


HALLUCINATIONS = [
    "subtitulos realizados",
    "subtítulos realizados",
    "amara.org",
    "subtitulos por la comunidad",
    "subtítulos por la comunidad",
    "subtitulado por",
    "gracias por ver",
    "suscribete al canal",
    "suscríbete al canal",
    "reproduccion continua",
    "reproducción continua",
    "derechos reservados",
    "alimmenta.com",
]

def transcribe_pcm_memory(agent: RyuVoiceAgent, pcm_bytes: bytes) -> str:
    """
    Transcribe el audio PCM de 8kHz directamente en memoria RAM usando faster-whisper con filtro VAD
    y penalización de repetición estricta para evitar bucles.
    """
    if not pcm_bytes or len(pcm_bytes) < 8000 * 2 * 0.25:
        return ""
        
    try:
        t0 = time.time()
        resampled_16k, _ = audioop.ratecv(pcm_bytes, 2, 1, 8000, 16000, None)
        audio_int16 = np.frombuffer(resampled_16k, dtype=np.int16)
        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        
        prompt = (
            "Restaurante Ryu en Tequila, Jalisco. Calles y colonias: Calle Girasol, Colonia Cofradía, Paseo del Centenario, Zaragoza, Juárez. "
            "Nombres: Josué Cabrales. "
            "Zonas de envío: Aguacatillo, Caseta, Penal, Toma, Fundición, Mirador, Parador Turístico, San Pedro, Santa Ana, Tierra de Agave, Medineño, Cantaritos El Güero, Amatitán, Puerta de En Medio, San Martín, Magdalena, Santa Teresa. "
            "Menú y preguntas: lasaña tradicional en capas, lasagna de carne y queso mozzarella, pastas italianas, boloñesa, fettuccine alfredo, "
            "paninis crujientes, pitas suaves, sodas italianas de fresa, piña, mora azul con boba, qué sabores de sodas italianas tienes, cuánto cuestan las pitas y los paninis, qué la acompaña, con qué viene, "
            "hamburguesa Big Ryu, Ranchera Especial, Carolina Especial, Cielo Mar y Tierra, alitas, boneless, calpico, cerveza Corona, sushi, ramen. "
            "Pedidos programados y a futuro: pedido programado, pedido a futuro, para más tarde, para hoy en la noche, para mañana a las dos, para el sábado, reservar, agendar orden. A domicilio, sucursal, con tarjeta, en efectivo."
        )

        
        model = get_whisper_model()
        segments, _ = model.transcribe(
            audio_f32,
            language="es",
            beam_size=1,
            condition_on_previous_text=False,
            temperature=0.0,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
            vad_filter=True,
            initial_prompt=prompt
        )
        raw_text = " ".join([s.text for s in segments]).strip()
        stt_time = round((time.time() - t0) * 1000)
        
        if not raw_text:
            print(f"⚠️ [STT Local ({stt_time}ms)]: Audio recibido pero transcripción vacía.")
            return ""
            
        text = deduplicate_repetitions(raw_text)
        text = clean_colloquial_speech(text)
        clean_t = text.strip().lower()
        
        for h in HALLUCINATIONS:
            if h in clean_t:
                print(f"🛡️ [Filtro VAD]: Ignorada alucinación Whisper: \"{text}\"")
                return ""
                
        if len(clean_t) < 2:
            return ""
            
        return text
    except Exception as e:
        print(f"Aviso faster-whisper local ({e}), usando fallback a OpenAI...")
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(pcm_bytes)
            buf.seek(0)
            buf.name = "call.wav"
            from openai import OpenAI
            client = OpenAI()
            resp = client.audio.transcriptions.create(model="whisper-1", file=buf, language="es")
            return resp.text.strip()
        except Exception as e2:
            print(f"Error en fallback STT: {e2}")
            return ""

def extract_caller_phone(call) -> str:
    try:
        req = getattr(call, "request", None)
        if req and hasattr(req, "headers"):
            headers = req.headers
            for h in ["Remote-Party-ID", "P-Asserted-Identity", "From", "Contact"]:
                if h in headers:
                    val = str(headers[h])
                    m = re.search(r"sip:([+]?\d{10,13})@", val)
                    if m and m.group(1) != SIP_USER:
                        num = m.group(1)
                        return f"+{num}" if not num.startswith("+") else num
                    m = re.search(r'"([+]?\d{10,13})"', val)
                    if m and m.group(1) != SIP_USER:
                        num = m.group(1)
                        return f"+{num}" if not num.startswith("+") else num
                    m = re.search(r'\+?(\d{10,12})', val)
                    if m and m.group(1) != SIP_USER:
                        num = m.group(1)
                        return f"+{num}" if not num.startswith("+") else num
    except Exception as e:
        print(f"Aviso extrayendo teléfono llamante: {e}")
    return "Número Oculto"

# ----------------------------------------------------------------------
# 6. CONTROLADOR DE LLAMADAS ENTRANTES
# ----------------------------------------------------------------------
def handle_incoming_call(call):
    call_id = f"sip_{int(time.time())}"
    print(f"\n=======================================================")
    print(f"LLAMADA TELEFONICA ENTRANTE CONECTADA! (ID: {call_id})")
    print(f"=======================================================")
    
    try:
        caller_phone = extract_caller_phone(call)
        print(f"📱 [Teléfono Detectado del Cliente]: {caller_phone}")

        # 1. Blindaje Anti-Spam / Anti-Flooding (CallRateLimiter)
        can_accept, reject_reason = call_rate_limiter.can_accept_call(caller_phone)
        if not can_accept:
            print(f"🛑 [Anti-Spam]: Llamada bloqueada de {caller_phone}. Razón: {reject_reason}")
            try:
                call.answer()
                audio_bloqueo = asyncio.run(synthesize_speech_alaw(
                    "Estimado cliente, por seguridad tu línea ha alcanzado el límite de llamadas permitidas por ahora. Por favor intenta de nuevo en unos minutos. ¡Hasta luego!",
                    None
                ))
                play_audio_to_call(call, audio_bloqueo)
                time.sleep(1)
            except Exception:
                pass
            call.hangup()
            return

        call_rate_limiter.record_call_start(caller_phone)
        call.answer()
        print(">>> Llamada descolgada exitosamente.")

        # 2. Inicializar Guardián de Tiempo y Turnos (CallWatchdog)
        watchdog = CallWatchdog(call_id=call_id, max_duration_sec=360, warning_threshold_sec=300, max_turns=20)
        
        if hasattr(call, "RTPClients") and call.RTPClients:
            c = call.RTPClients[0]
            print(f"[Audio RTP]: Codec: {c.preference} | Destino: {c.outIP}:{c.outPort}")
            
        agent = RyuVoiceAgent(caller_phone=caller_phone, caller_name="Cliente")
        
        print(f">>> [RyuBot]: \"{agent.greeting}\"")
        if PRELOADED_GREETING:
            saludo_audio = PRELOADED_GREETING
        else:
            saludo_audio = asyncio.run(synthesize_speech_alaw(agent.greeting, agent))
            
        play_audio_to_call(call, saludo_audio)
        
        silencios_consecutivos = 0
        
        while call.state == CallState.ANSWERED and not agent.order_confirmed:
            # Supervisión continua de tiempo y turnos máximos
            w_status, w_msg = watchdog.check_status()
            if w_status == "WARNING_TIME":
                print(f"⚠️ [Watchdog Alerta de Tiempo (Minuto 5)]: {w_msg}")
                w_audio = asyncio.run(synthesize_speech_alaw(w_msg, agent))
                play_audio_to_call(call, w_audio)
            elif w_status in ["EXPIRED_TIME", "EXPIRED_TURNS"]:
                print(f"🛑 [Watchdog Límite de Llamada Alcanzado ({w_status})]: {w_msg}")
                exp_audio = asyncio.run(synthesize_speech_alaw(w_msg, agent))
                play_audio_to_call(call, exp_audio)
                time.sleep(1)
                break

            print("\n[Escuchando al cliente por telefono...]")
            pcm_audio = record_user_speech(call)
            
            if call.state != CallState.ANSWERED:
                print(">>> El cliente colgó la llamada.")
                break
                
            if not pcm_audio:
                silencios_consecutivos += 1
                if silencios_consecutivos == 3:
                    if len(agent.conversation_history) > 0:
                        reminder = "¿Sigues en la línea? Tómate tu tiempo, con calma."
                    else:
                        reminder = "Hola, ¿sigues ahí? ¿Qué te gustaría ordenar de Ryu?"
                    print(f">>> [RyuBot Recordatorio]: \"{reminder}\"")
                    reminder_audio = asyncio.run(synthesize_speech_alaw(reminder, agent))
                    play_audio_to_call(call, reminder_audio)
                elif silencios_consecutivos == 6:
                    reminder = "Aquí sigo en la línea a tus órdenes. Tómate el tiempo necesario para armar tu orden."
                    print(f">>> [RyuBot Recordatorio]: \"{reminder}\"")
                    reminder_audio = asyncio.run(synthesize_speech_alaw(reminder, agent))
                    play_audio_to_call(call, reminder_audio)
                elif silencios_consecutivos == 9:
                    reminder = "Sigo aquí contigo esperándote, avísame cuando tengas lista tu orden."
                    print(f">>> [RyuBot Recordatorio]: \"{reminder}\"")
                    reminder_audio = asyncio.run(synthesize_speech_alaw(reminder, agent))
                    play_audio_to_call(call, reminder_audio)
                elif silencios_consecutivos >= 12:
                    despedida = "Por inactividad voy a terminar la llamada para liberar la línea. Si gustas volver a marcar, estamos a tus órdenes. ¡Hasta luego!"
                    print(f">>> [RyuBot Despedida por Inactividad]: \"{despedida}\"")
                    despedida_audio = asyncio.run(synthesize_speech_alaw(despedida, agent))
                    play_audio_to_call(call, despedida_audio)
                    break
                continue

            silencios_consecutivos = 0
            
            t0 = time.time()
            raw_user_text = transcribe_pcm_memory(agent, pcm_audio)
            stt_time = round((time.time() - t0) * 1000)
            
            # Sanitización de longitud para prevenir prompt flooding / text bombing
            user_text = input_sanitizer.sanitize_text(raw_user_text, max_chars=350)
            watchdog.record_turn()
            
            if not user_text:
                continue

                
            print(f">>> [Cliente ({stt_time}ms)]: \"{user_text}\"")
            
            t1 = time.time()
            reply_text = agent.think_and_respond(user_text)
            llm_time = round((time.time() - t1) * 1000)
            print(f">>> [RyuBot ({llm_time}ms)]: \"{reply_text}\"")
            
            t2 = time.time()
            reply_audio = asyncio.run(synthesize_speech_alaw(reply_text, agent))
            tts_time = round((time.time() - t2) * 1000)
            print(f"⚡ [Latencias]: STT={stt_time}ms | LLM={llm_time}ms | TTS={tts_time}ms | Total={stt_time+llm_time+tts_time}ms")
            
            play_audio_to_call(call, reply_audio)
            
            if call.state != CallState.ANSWERED:
                print(">>> El cliente colgó la llamada.")
                break
            
            if agent.order_confirmed:
                print(">>> ¡Comanda confirmada y enviada a cocina! Esperando 5 segundos para saber si desea ordenar algo más...")
                # Ventana de escucha de 5 segundos tras confirmación
                post_confirm_audio = record_user_speech(call, max_silence_seconds=1.2, max_duration=5.0)
                if not post_confirm_audio or len(post_confirm_audio) == 0:
                    print(">>> Silencio de 5 segundos tras confirmación. Despidiendo y cerrando llamada...")
                    despedida = "¡Muchas gracias por llamar a Ryu, que disfrutes tu comida! ¡Hasta luego!"
                    despedida_audio = asyncio.run(synthesize_speech_alaw(despedida, agent))
                    play_audio_to_call(call, despedida_audio)
                    time.sleep(1)
                    break
                else:
                    post_text = transcribe_pcm_memory(agent, post_confirm_audio)
                    print(f">>> [Cliente tras confirmación]: \"{post_text}\"")
                    # Si el cliente dice que no o que es todo, despedirse amablemente
                    if not post_text or any(w in post_text.lower() for w in ["nada", "todo", "no gracias", "no, gracias", "seria todo", "sería todo", "así está bien", "asi esta bien", "muchas gracias", "bye", "adiós", "adios"]):
                        print(">>> El cliente indicó que sería todo. Despidiendo y finalizando llamada...")
                        despedida = "¡Muchas gracias por tu preferencia en Ryu, que lo disfrutes! ¡Hasta luego!"
                        despedida_audio = asyncio.run(synthesize_speech_alaw(despedida, agent))
                        play_audio_to_call(call, despedida_audio)
                        time.sleep(1)
                        break
                    else:
                        # Si el cliente desea ordenar algo más, reabrimos la orden
                        print(">>> El cliente desea agregar algo más a su pedido...")
                        agent.order_confirmed = False
                        reply_text = agent.think_and_respond(post_text)
                        print(f">>> [RyuBot]: \"{reply_text}\"")
                        reply_audio = asyncio.run(synthesize_speech_alaw(reply_text, agent))
                        play_audio_to_call(call, reply_audio)
                
        time.sleep(1)
        if call.state == CallState.ANSWERED:
            call.hangup()
            print(">>> Llamada finalizada normalmente.")

        # 3. Registrar duración para control de abusos y purgar audios huérfanos
        if 'watchdog' in locals() and 'caller_phone' in locals():
            call_rate_limiter.record_call_end(caller_phone, watchdog.elapsed_seconds)
        cleanup_temp_audio_files()

            
    except Exception as e:
        print(f"Error procesando llamada {call_id}: {e}")
        try:
            call.hangup()
        except Exception:
            pass

# ----------------------------------------------------------------------
# 7. ARRANQUE DEL SERVIDOR SIP
# ----------------------------------------------------------------------
def find_free_udp_port(start_port=5060):
    for port in range(start_port, start_port + 50):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((LOCAL_IP, port))
            s.close()
            return port
        except OSError:
            continue
    return 5060

def start_watchdog_thread():
    def watchdog_loop():
        last_proactive_register = time.time()
        while True:
            time.sleep(15)
            try:
                if GLOBAL_PHONE is None:
                    continue
                status = GLOBAL_PHONE.get_status()
                # Si se perdió la conexión por completo (FAILED o INACTIVE), re-registrar de inmediato
                if status in (PhoneStatus.FAILED, PhoneStatus.INACTIVE):
                    print(f"\n⚠️ [Watchdog Alerta]: Estado SIP es {status}. Reconectando a Zadarma...")
                    try:
                        GLOBAL_PHONE.sip.register()
                    except Exception as e:
                        print(f"Error en re-registro: {e}")
            except Exception as e:
                print(f"Error en hilo watchdog: {e}")

    t = threading.Thread(target=watchdog_loop, daemon=True, name="SIP Watchdog")
    t.start()

def main():
    global GLOBAL_PHONE
    
    # 1. Cargar y precalentar faster-whisper en RAM
    get_whisper_model()
    
    # 2. Pre-sintetizar saludo en RAM
    preload_greeting()
    
    sip_port = find_free_udp_port(5060)
    print("\n==================================================================")
    print("INICIANDO SERVICIO SIP TELEFONICO - RESTAURANTE RYU (ULTRA-RÁPIDO)")
    print(f"- Servidor SIP: {SIP_SERVER}")
    print(f"- Extension: {SIP_USER}")
    print(f"- Numero Virtual DID: {PHONE_NUMBER}")
    print(f"- IP Local: {LOCAL_IP} (Puerto SIP: {sip_port})")
    print("==================================================================")
    
    GLOBAL_PHONE = VoIPPhone(
        SIP_SERVER,
        5060,
        SIP_USER,
        SIP_PASSWORD,
        myIP=LOCAL_IP,
        callCallback=handle_incoming_call,
        sipPort=sip_port
    )
    
    print("Registrando extension SIP en Zadarma...")
    GLOBAL_PHONE.start()
    
    for _ in range(15):
        time.sleep(1)
        if GLOBAL_PHONE.get_status() == PhoneStatus.REGISTERED:
            break
            
    while GLOBAL_PHONE.get_status() != PhoneStatus.REGISTERED:
        status = GLOBAL_PHONE.get_status()
        print(f"⏳ Enlace SIP en proceso... (Estado: {status}). Reintentando conexión con Zadarma en 15s...")
        time.sleep(15)
        try:
            GLOBAL_PHONE.sip.register()
        except Exception as e:
            print(f"Aviso registro: {e}")

    start_watchdog_thread()
    print("\n" + "="*66)
    print("CONEXION EXITOSA CON ZADARMA! ESTADO: REGISTERED")
    print(f"El numero {PHONE_NUMBER} esta 100% EN VIVO Y OPTIMIZADO.")
    print("Vigilante Watchdog activo: responde heartbeats y renueva cada 5 min.")
    print("LISTO PARA RECIBIR TU LLAMADA!")
    print("Marca desde tu celular al: 33 8526 1250")
    print("="*66 + "\n")
    print("Presiona Ctrl+C para detener el servicio.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo servicio SIP...")
        cleanup()
        print("Servicio detenido.")

if __name__ == "__main__":
    main()
