"""
======================================================================
RESTAURANTE RYU - SERVIDOR ULTRA RÁPIDO (<1 SEG LATENCIA)
Reconocimiento en tiempo real + Respuesta inmediata + Edge-TTS + Telegram
======================================================================
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import collections
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, Response
import voice_studio_backend
from voice_engine_ryu import (
    RyuVoiceAgent,
    load_restaurant_state,
    save_restaurant_state,
    build_kitchen_dynamic_prompt
)
from security_guard import (
    message_rate_limiter,
    input_sanitizer,
    cleanup_temp_audio_files
)
import schemas_ryu
import yaml

TAGS_METADATA = [
    {
        "name": "Autenticación",
        "description": "Control de acceso seguro para administradores y cajeros mediante tokens criptográficos HMAC-SHA256 y rate limiting anti-fuerza bruta."
    },
    {
        "name": "Estado Operacional",
        "description": "Gestión en tiempo real del estado del restaurante: recepción de pedidos (abierto/cerrado), tiempos estimados y avisos de cocina."
    },
    {
        "name": "Existencias & Catálogo",
        "description": "Control de ingredientes críticos agotados y disponibilidad de platillos en los menús Japonés, Snacks e Italiano."
    },
    {
        "name": "Promociones & Horarios",
        "description": "Administración de promociones diarias (ej. 3x2, descuentos) y horarios dinámicos de menús de día y noche."
    },
    {
        "name": "Condiciones de Entrega",
        "description": "Tarificación y reglas de zonas foráneas en Tequila (El Medineño, San Martín, Magdalena, Tierra de Agave, etc.)."
    },
    {
        "name": "Estudio de Grabación (Voice Studio)",
        "description": "Grabación de voz del dueño, transcodificación a códec G.711 A-law 8kHz y precarga en memoria RAM para latencia 0ms y $0 USD en llamadas."
    },
    {
        "name": "POS Bridge & Impresión",
        "description": "Puente de comunicación bidireccional con terminales de punto de venta (Soft Restaurant) e impresoras térmicas de cocina."
    },
    {
        "name": "Monitor IA & Especificaciones",
        "description": "Inspección del prompt dinámico inyectado al LLM y descarga de especificaciones OpenAPI y arquitectura."
    },
    {
        "name": "Audio & Simulador Web",
        "description": "Simulación interactiva de voz por navegador y transmisión de audios sintetizados o pregrabados."
    }
]

app = FastAPI(
    title="Restaurante Ryu - API de Telefonía IA & Gestión de Pedidos",
    summary="Plataforma de voz inteligente, conmutador SIP VoIP y panel de administración en tiempo real.",
    description="""
# 🍣 Ryu AI Voice Telephony & Restaurant Automation API

Esta API potencia el conmutador telefónico inteligente y el panel administrativo del **Restaurante Ryu** y **Capri Cucina Italiana** en Tequila, Jalisco.

### Capacidades Principales:
* **Telefonía SIP/RTP**: Integración con Zadarma (`+52 33 8526 1250`) con audio G.711 A-law a 8000 Hz.
* **Transcripción en RAM**: `faster-whisper` (int8) en CPU local sin costo por llamada.
* **Orquestación LLM**: OpenAI GPT-4o-mini con prompts dinámicos de cocina y auditoría matemática determinística de cuentas.
* **Voice Studio Web**: Banco de clips pregrabados con acento local y latencia 0 ms en RAM.
* **Despacho Multicanal**: Envío instantáneo de comandas a Telegram, WhatsApp y comandera POS.
    """,
    version="2.1.0",
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Gestor de llamadas simultáneas en memoria (soporta 50+ llamadas en paralelo)
active_sessions: dict[str, RyuVoiceAgent] = {}

def get_agent_for_session(session_id: str, caller_phone: str = "+52 33 8526 1250", caller_name: str = "Cliente") -> RyuVoiceAgent:
    if session_id not in active_sessions:
        active_sessions[session_id] = RyuVoiceAgent(caller_phone=caller_phone, caller_name=caller_name)
    return active_sessions[session_id]

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    """Interfaz web de ultra baja latencia con reconocimiento en tiempo real"""
    return """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📞 Llamada Ultra Rápida - Restaurante Ryu</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #0f0f12; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .card { background-color: #1a1a24; border: 1px solid #2d2d3f; border-radius: 20px; }
        .call-btn { width: 90px; height: 90px; border-radius: 50%; font-size: 34px; display: flex; align-items: center; justify-content: center; margin: 0 auto; transition: all 0.2s ease; }
        .chat-bubble { padding: 14px 20px; border-radius: 20px; margin-bottom: 12px; max-width: 82%; font-size: 15px; line-height: 1.4; }
        .bot-bubble { background-color: #262638; border-left: 4px solid #ff4757; color: #fff; align-self: flex-start; }
        .user-bubble { background-color: #2ed573; color: #05260f; align-self: flex-end; font-weight: 600; }
        #chatBox { height: 360px; overflow-y: auto; display: flex; flex-direction: column; padding: 18px; background: #13131c; border-radius: 14px; border: 1px solid #232333; }
        .pulsing { animation: pulse 1.2s infinite; }
        @keyframes pulse { 0% { transform: scale(0.96); box-shadow: 0 0 0 0 rgba(255, 71, 87, 0.7); } 70% { transform: scale(1.04); box-shadow: 0 0 0 16px rgba(255, 71, 87, 0); } 100% { transform: scale(0.96); box-shadow: 0 0 0 0 rgba(255, 71, 87, 0); } }
        .badge-latency { background: #232333; color: #2ed573; padding: 4px 10px; border-radius: 12px; font-size: 12px; }
    </style>
</head>
<body class="p-3 p-md-5">
    <div class="container" style="max-width: 650px;">
        <div class="card p-4 p-md-5 shadow-lg text-center">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <span class="text-danger fw-bold fs-5">🍣 Restaurante Ryu</span>
                <span id="latencyBadge" class="badge-latency">⚡ Modo Tiempo Real</span>
            </div>
            <p class="text-secondary small mb-4">Simulador de Llamada con Detección Instantánea</p>

            <div id="chatBox" class="mb-4 text-start">
                <div class="chat-bubble bot-bubble">
                    📞 <b>RyuBot:</b> ¡Hola, buenas tardes! Gracias por llamar a Ryu en Tequila. Soy tu asistente virtual, ¿qué se te antoja ordenar hoy?
                </div>
            </div>

            <div class="d-flex justify-content-center gap-3 align-items-center mb-3">
                <button id="micBtn" class="btn btn-success call-btn shadow" onclick="toggleCall()">
                    🎙️
                </button>
            </div>
            <p id="statusText" class="text-secondary small fw-medium">Toca el micrófono y empieza a hablar (responderá al instante)</p>

            <div class="input-group mt-3">
                <input type="text" id="textInput" class="form-control bg-dark text-white border-secondary" placeholder="O escribe tu pedido aquí..." onkeypress="handleKey(event)">
                <button class="btn btn-danger" onclick="sendText()">Enviar</button>
            </div>
        </div>
    </div>

    <audio id="audioPlayer" autoplay></audio>

    <script>
        const callSessionId = 'call_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now();
        let recognition;
        let isCalling = false;
        let finalTranscript = '';
        let silenceTimer;

        // Soporte nativo de Web Speech API (transcripción a 0ms sin subir archivos)
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'es-MX';

            recognition.onresult = (event) => {
                let interimTranscript = '';
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }
                
                const currentText = (finalTranscript || interimTranscript).trim();
                if (currentText) {
                    document.getElementById('statusText').innerText = '🗣️ Escuchando: "' + currentText + '"';
                    
                    // Si el usuario hace una pausa de 1 segundo, enviar en automático
                    clearTimeout(silenceTimer);
                    silenceTimer = setTimeout(() => {
                        if (currentText.length > 2) {
                            sendSpeechToServer(currentText);
                            finalTranscript = '';
                        }
                    }, 1100);
                }
            };

            recognition.onerror = (event) => {
                console.warn('Speech recognition error:', event.error);
                document.getElementById('statusText').innerText = 'Presiona el micrófono para hablar';
            };

            recognition.onend = () => {
                if (isCalling) {
                    recognition.start(); // Reconectar si la llamada sigue activa
                }
            };
        }

        function toggleCall() {
            const btn = document.getElementById('micBtn');
            const status = document.getElementById('statusText');

            if (!isCalling) {
                if (!recognition) {
                    alert('Tu navegador no soporta reconocimiento nativo. Te recomendamos usar Google Chrome.');
                    return;
                }
                isCalling = true;
                finalTranscript = '';
                recognition.start();

                btn.classList.remove('btn-success');
                btn.classList.add('btn-danger', 'pulsing');
                btn.innerHTML = '🔴';
                status.innerText = '🎙️ Habla con normalidad. En cuanto hagas una pausa, RyuBot te responderá.';
            } else {
                isCalling = false;
                recognition.stop();
                clearTimeout(silenceTimer);

                btn.classList.remove('btn-danger', 'pulsing');
                btn.classList.add('btn-success');
                btn.innerHTML = '🎙️';
                status.innerText = 'Llamada pausada. Toca el micrófono para hablar.';
            }
        }

        async function sendSpeechToServer(text) {
            const startTime = performance.now();
            document.getElementById('statusText').innerText = '⚡ Pensando respuesta...';

            // Pausar reconocimiento mientras el bot habla para no escucharse a sí mismo
            if (recognition) recognition.stop();

            try {
                const res = await fetch('/api/fast-chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: text, session_id: callSessionId })
                });
                const data = await res.json();
                const latency = Math.round(performance.now() - startTime);
                document.getElementById('latencyBadge').innerText = '⚡ ' + latency + ' ms';

                handleBotReply(text, data.reply_text, data.audio_url);
            } catch (e) {
                console.error(e);
                document.getElementById('statusText').innerText = 'Error de conexión. Intenta de nuevo.';
            }
        }

        async function sendText() {
            const input = document.getElementById('textInput');
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            await sendSpeechToServer(text);
        }

        function handleKey(e) {
            if (e.key === 'Enter') sendText();
        }

        function handleBotReply(userText, botText, audioUrl) {
            const chatBox = document.getElementById('chatBox');
            
            // Mensaje del cliente
            const userBubble = document.createElement('div');
            userBubble.className = 'chat-bubble user-bubble';
            userBubble.innerText = '👤 Tú: ' + userText;
            chatBox.appendChild(userBubble);

            // Respuesta de RyuBot
            const botBubble = document.createElement('div');
            botBubble.className = 'chat-bubble bot-bubble';
            botBubble.innerHTML = '🍣 <b>RyuBot:</b> ' + botText;
            chatBox.appendChild(botBubble);

            chatBox.scrollTop = chatBox.scrollHeight;

            // Reproducir voz mexicana Dalia
            if (audioUrl) {
                const player = document.getElementById('audioPlayer');
                player.src = audioUrl + '?t=' + new Date().getTime();
                player.play();

                player.onended = () => {
                    if (isCalling && recognition) {
                        finalTranscript = '';
                        recognition.start();
                        document.getElementById('statusText').innerText = '🎙️ Te toca hablar...';
                    }
                };
            }
        }
    </script>
</body>
</html>
    """

@app.post("/api/fast-chat", tags=["Audio & Simulador Web"], summary="Simula una interacción conversacional completa con RyuBot")
async def fast_chat(request: Request):
    t0 = time.time()
    
    # 1. Blindaje Anti-Spam (Rate Limiter por IP y Sesión)
    client_ip = request.client.host if request.client else "unknown"
    data = await request.json()
    raw_user_text = data.get("text", "")
    session_id = data.get("session_id", "default_call")
    client_key = f"{client_ip}_{session_id}"

    is_allowed, retry_after = message_rate_limiter.check_rate_limit(client_key)
    if not is_allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": f"Demasiadas peticiones. Por seguridad, espera {retry_after} segundos.",
                "retry_after": retry_after
            }
        )

    # 2. Sanitización contra Prompt Flooding / Text Bombing
    user_text = input_sanitizer.sanitize_text(raw_user_text, max_chars=350)
    if not user_text:
        return JSONResponse(status_code=400, content={"error": "Mensaje vacío o no válido"})

    agent = get_agent_for_session(session_id)
    
    # 3. GPT-4o-mini responde con el menú oficial y reglas de presupuesto
    response_text = agent.think_and_respond(user_text)
    
    # 4. Síntesis instantánea con Edge-TTS en storage/temp/
    audio_filename = f"fast_reply_{session_id}_{int(time.time() * 1000)}.mp3"
    temp_storage = Path(__file__).parent / "storage" / "temp"
    temp_storage.mkdir(parents=True, exist_ok=True)
    audio_filepath = str(temp_storage / audio_filename)
    await agent.speak(response_text, audio_filepath)
    
    # 5. Mantenimiento automático de disco (elimina audios huérfanos > 5 min)
    cleanup_temp_audio_files(directory=str(temp_storage), max_age_seconds=300)
    
    total_time = round((time.time() - t0) * 1000)
    print(f">>> [Llamada {session_id[:12]}] [Latencia: {total_time} ms] Cliente: '{user_text}' -> RyuBot: '{response_text[:30]}...'")
    
    return {
        "reply_text": response_text,
        "audio_url": f"/audio/{audio_filename}",
        "order_confirmed": agent.order_confirmed,
        "latency_ms": total_time,
        "session_id": session_id
    }


@app.get("/audio/{filename}", tags=["Audio & Simulador Web"], summary="Descarga o streaming de clip de audio")
def get_audio(filename: str):
    temp_file = Path(__file__).parent / "storage" / "temp" / filename
    if temp_file.exists():
        return FileResponse(str(temp_file), media_type="audio/mpeg")
    if os.path.exists(filename):
        return FileResponse(filename, media_type="audio/mpeg")
    return JSONResponse(status_code=404, content={"error": "Audio no encontrado"})

@app.get("/api/pos/orders/pending", tags=["POS Bridge & Impresión"], summary="Consulta comandas pendientes para Soft Restaurant")
def get_pending_pos_orders(request: Request):
    """Retorna las órdenes pendientes para inyección al sistema Soft Restaurant local."""
    secret = os.getenv("POS_BRIDGE_SECRET", "ryu_pos_secret_key_2026")
    auth_header = request.headers.get("X-POS-Token")
    if auth_header != secret and request.query_params.get("token") != secret:
        return JSONResponse(status_code=401, content={"error": "No autorizado para POS Bridge"})

    from soft_restaurant_bridge import get_pending_pos_orders_sync
    orders = get_pending_pos_orders_sync()
    return {"status": "ok", "orders": orders}


@app.post("/api/pos/orders/{order_id}/ack", tags=["POS Bridge & Impresión"], summary="Confirma inyección de comanda en el POS local")
def acknowledge_pos_order(order_id: str, request: Request):
    """
    Confirma que el pedido ya fue impreso e inyectado en el Soft Restaurant local.
    """
    secret = os.getenv("POS_BRIDGE_SECRET", "ryu_pos_secret_key_2026")
    auth_header = request.headers.get("X-POS-Token")
    if auth_header != secret and request.query_params.get("token") != secret:
        return JSONResponse(status_code=401, content={"error": "No autorizado para POS Bridge"})

    from soft_restaurant_bridge import mark_pos_order_acknowledged
    success = mark_pos_order_acknowledged(order_id, status="INJECTED_LOCAL")
    return {"status": "ok" if success else "error", "order_id": order_id}

# ======================================================================
# AUTENTICACIÓN Y BLINDAJE DE SEGURIDAD PARA EL PANEL DE CONTROL
# ======================================================================

ADMIN_USERNAME = str(os.getenv("ADMIN_USERNAME") or "admin").strip()
ADMIN_PASSWORD = str(os.getenv("ADMIN_PASSWORD") or "ryu_tequila_2026").strip()
ADMIN_SECRET_KEY = str(os.getenv("ADMIN_SECRET_KEY") or "ryu_admin_jwt_secret_token_tequila_2026").strip()

# Rate limiter contra ataques de fuerza bruta en el login (máx 5 intentos fallidos en 10 min por IP)
login_failed_attempts: dict[str, list[float]] = collections.defaultdict(list)

def verify_admin_auth(request: Request) -> bool:
    """Verifica si la petición cuenta con credenciales válidas (Token Bearer, Cookie o Basic Auth)."""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "X-Admin-Token" in request.headers:
        token = request.headers["X-Admin-Token"].strip()
    elif "admin_token" in request.cookies:
        token = request.cookies["admin_token"].strip()

    if token:
        try:
            parts = token.split(":")
            if len(parts) == 3:
                uname, exp_str, sig = parts
                exp_ts = int(exp_str)
                if exp_ts > time.time() and secrets.compare_digest(uname, ADMIN_USERNAME):
                    expected_sig = hmac.new(ADMIN_SECRET_KEY.encode(), f"{uname}:{exp_str}".encode(), hashlib.sha256).hexdigest()
                    if secrets.compare_digest(sig, expected_sig):
                        return True
        except Exception:
            pass

    # Soporte para HTTP Basic Auth estándar
    if auth_header.startswith("Basic "):
        import base64
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            u, p = decoded.split(":", 1)
            if secrets.compare_digest(u, ADMIN_USERNAME) and secrets.compare_digest(p, ADMIN_PASSWORD):
                return True
        except Exception:
            pass

    return False


@app.post("/api/auth/login", tags=["Autenticación"], summary="Inicio de sesión administrativo con protección anti-fuerza bruta")
async def api_auth_login(request: Request):
    """Autenticación de personal del restaurante con protección anti fuerza bruta."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Limpiar intentos viejos (> 10 min)
    login_failed_attempts[client_ip] = [t for t in login_failed_attempts[client_ip] if (now - t) < 600]
    if len(login_failed_attempts[client_ip]) >= 5:
        return JSONResponse(
            status_code=429,
            content={"error": "Demasiados intentos fallidos. Por seguridad, el acceso está bloqueado temporalmente por 10 minutos."}
        )
        
    try:
        data = await request.json()
    except Exception:
        data = {}
        
    u = str(data.get("username", "")).strip()
    p = str(data.get("password", "")).strip()
    
    if secrets.compare_digest(u, ADMIN_USERNAME) and secrets.compare_digest(p, ADMIN_PASSWORD):
        login_failed_attempts[client_ip] = []
        exp_ts = int(now) + 86400 * 30  # Sesión válida por 30 días
        payload = f"{ADMIN_USERNAME}:{exp_ts}"
        sig = hmac.new(ADMIN_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        token = f"{payload}:{sig}"
        
        response = JSONResponse(content={"status": "ok", "token": token, "username": ADMIN_USERNAME})
        response.set_cookie(
            key="admin_token",
            value=token,
            max_age=86400 * 30,
            httponly=True,
            samesite="lax",
            secure=True
        )
        return response
    else:
        login_failed_attempts[client_ip].append(now)
        remaining = max(0, 5 - len(login_failed_attempts[client_ip]))
        return JSONResponse(
            status_code=401,
            content={"error": f"Usuario o contraseña incorrectos. Intentos restantes: {remaining}"}
        )


@app.get("/api/auth/check", tags=["Autenticación"], summary="Verifica validez del token de sesión")
def api_auth_check(request: Request):
    """Verifica si la sesión actual es válida."""
    is_auth = verify_admin_auth(request)
    return {"authenticated": is_auth, "username": ADMIN_USERNAME if is_auth else None}


# ======================================================================
# RUTAS DE ADMINISTRACIÓN EN TIEMPO REAL (STOCK, PROMOCIONES Y HORARIOS)
# ======================================================================

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard():
    """Panel de Control visual para celular y PC"""
    template_path = Path(__file__).parent / "templates" / "admin_dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Plantilla de administración no encontrada en templates/admin_dashboard.html</h1>", status_code=404)

@app.get("/api/state", tags=["Estado Operacional"], summary="Consulta el estado dinámico actual del restaurante")
def get_state():
    """Retorna el estado dinámico actual del restaurante"""
    return load_restaurant_state()

@app.post("/api/stock/ingredient", tags=["Existencias & Catálogo"], summary="Conmuta disponibilidad de un ingrediente crítico")
async def toggle_ingredient(request: Request):
    """Conmuta la disponibilidad de un ingrediente crítico (ej. pulpo, camarón, etc.)"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado. Inicia sesión para modificar existencias."})
        
    data = await request.json()
    ing_id = str(data.get("ingredient_id", "")).strip().lower()
    available = bool(data.get("available", True))
    
    state = load_restaurant_state()
    unavail = state.get("unavailable_ingredients", [])
    
    if available:
        if ing_id in unavail:
            unavail.remove(ing_id)
    else:
        if ing_id and ing_id not in unavail:
            unavail.append(ing_id)
            
    state["unavailable_ingredients"] = unavail
    save_restaurant_state(state)
    return state

@app.post("/api/stock/dish", tags=["Existencias & Catálogo"], summary="Habilita o deshabilita un platillo del menú")
async def toggle_dish(request: Request):
    """Conmuta la disponibilidad de un platillo específico"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado. Inicia sesión para modificar platillos."})
        
    data = await request.json()
    dish_name = str(data.get("dish_name", "")).strip()
    available = bool(data.get("available", True))
    
    state = load_restaurant_state()
    unavail = state.get("unavailable_dishes", [])
    
    if available:
        if dish_name in unavail:
            unavail.remove(dish_name)
    else:
        if dish_name and dish_name not in unavail:
            unavail.append(dish_name)
            
    state["unavailable_dishes"] = unavail
    save_restaurant_state(state)
    return state

@app.post("/api/promotions", tags=["Promociones & Horarios"], summary="Actualiza promociones y reglas especiales")
async def update_promotions(request: Request):
    """Actualiza las promociones del día aplicadas en la IA"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado. Inicia sesión para actualizar promociones."})
        
    data = await request.json()
    promotions = data.get("promotions", [])
    
    state = load_restaurant_state()
    state["daily_promotions"] = promotions
    save_restaurant_state(state)
    return state

@app.post("/api/announcement", tags=["Estado Operacional"], summary="Actualiza tiempos estimados y avisos de cocina")
async def update_announcement(request: Request):
    """Actualiza avisos de demora, apertura o notas de cocina"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado. Inicia sesión para cambiar avisos."})
        
    data = await request.json()
    state = load_restaurant_state()
    
    if "is_open" in data:
        state["is_open"] = bool(data["is_open"])
    if "service_override" in data:
        state["service_override"] = str(data["service_override"]).strip()
    if "prep_time_override" in data:
        state["prep_time_override"] = str(data["prep_time_override"]).strip()
        
    save_restaurant_state(state)
    return state

CATEGORY_NAMES = {
    # Japanese
    "entremeses": "Entremeses",
    "kushiage_brochetas": "Kushiages (Brochetas)",
    "ensaladas": "Ensaladas Frescas",
    "sashimi": "Sashimi",
    "nigiris": "Nigiris Tradicionales",
    "sopas": "Sopas & Ramen",
    "yakimeshi": "Arroz Yakimeshi",
    "teppanyaki_teriyaki": "Teppanyaki & Teriyaki",
    "platillos_fuertes": "Platillos Fuertes",
    "sushi_rollos": "Rollos de Sushi",
    
    # Italian
    "platillos": "Platillos Tradicionales",
    "paninis_y_pitas": "Paninis y Pitas Artesanales",
    "ensaladas_italianas": "Ensaladas Italianas",
    "sodas_italianas": "Sodas Italianas con Boba",
    
    # Snacks
    "paquetes_y_promos": "Paquetes & Promos",
    "hamburguesas": "Hamburguesas",
    "hot_dogs": "Hot Dogs",
    "tortas": "Tortas de Pierna",
    "snacks_fritos_y_papas": "Snacks Fritos & Papas",
    "toppings_extras": "Toppings Extras",
    "bebidas": "Bebidas & Refrescos",
    "postres": "Postres & Helados"
}

def get_full_hierarchical_menu():
    menu_path = Path(__file__).parent / "menu_ryu.json"
    state = load_restaurant_state()
    dish_overrides = state.get("dish_overrides", {})
    unavailable_dishes = set(state.get("unavailable_dishes", []))

    if not menu_path.exists():
        return {"schedules": {}, "menus": {}}

    try:
        with open(menu_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error leyendo menu_ryu.json: {e}")
        return {"schedules": {}, "menus": {}}

    schedules = state.get("schedules_override") or data.get("schedules", {})
    menu_raw = data.get("menu", {})
    result_menus = {}

    menu_meta = {
        "japanese": {
            "title": "Comida Japonesa & General",
            "icon": "🍣",
            "schedule_label": schedules.get("japanese", {}).get("description", "1:00 PM a 6:30 PM (L-D)")
        },
        "snacks": {
            "title": "Snacks, Hamburguesas & Hot Dogs",
            "icon": "🍔",
            "schedule_label": schedules.get("snacks", {}).get("description", "6:30 PM a 10:30 PM (L-D)")
        },
        "italian": {
            "title": "Comida Italiana (Capri Cucina)",
            "icon": "🍕",
            "schedule_label": schedules.get("italian", {}).get("description", "1:00 PM a 6:30 PM (Viernes, Sábados y Domingos)")
        }
    }

    for menu_key in ["japanese", "snacks", "italian"]:
        meta = menu_meta.get(menu_key, {})
        section_content = menu_raw.get(menu_key, {})
        categories = []

        if isinstance(section_content, dict):
            for cat_key, items in section_content.items():
                cat_name = CATEGORY_NAMES.get(cat_key, cat_key.replace("_", " ").capitalize())
                dishes = []

                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict) and "name" in it:
                            dish_id = it.get("id", f"{menu_key}_{cat_key}_{len(dishes)}")
                            ov = dish_overrides.get(dish_id, {})
                            
                            name = ov.get("name", it.get("name"))
                            price = ov.get("price", it.get("price", 0))
                            desc = ov.get("description", it.get("description", ""))
                            sched_mode = ov.get("schedule_mode", "menu_default")
                            custom_start = ov.get("custom_start", "")
                            custom_end = ov.get("custom_end", "")
                            
                            is_active = ov.get("is_active", True)
                            if name in unavailable_dishes:
                                is_active = False

                            dishes.append({
                                "id": dish_id,
                                "name": name,
                                "price": price,
                                "description": desc,
                                "menu_key": menu_key,
                                "category_key": cat_key,
                                "category_name": cat_name,
                                "schedule_mode": sched_mode,
                                "custom_start": custom_start,
                                "custom_end": custom_end,
                                "is_active": is_active
                            })
                elif cat_key == "paninis_y_pitas" and isinstance(items, dict):
                    desc_templates = {
                        "BBQ": "Fajitas de pollo en salsa BBQ artesanal con queso gratinado. Incluye papas a la francesa.",
                        "Chipotle": "Fajitas de pollo en cremosa salsa chipotle con queso gratinado. Incluye papas a la francesa.",
                        "Cheesesteak": "Finas tiras de res salteadas con cebolla y queso gratinado. Incluye papas a la francesa.",
                        "Pollo Clásico": "Pechuga de pollo a la plancha a las finas hierbas con queso gratinado. Incluye papas a la francesa.",
                        "Pollo Crispy": "Tiras de pollo crujiente empanizado con queso gratinado. Incluye papas a la francesa.",
                        "Carnes Frías": "Jamón de pierna, salami y queso derretido artesanal. Incluye papas a la francesa."
                    }
                    for esp in items.get("especialidades", []):
                        esp_name = esp.get("name", "")
                        base_desc = desc_templates.get(esp_name, "Deliciosa especialidad con queso derretido y papas a la francesa.")
                        
                        p_id = f"{esp.get('id', 'it')}_panini"
                        p_ov = dish_overrides.get(p_id, {})
                        p_name = p_ov.get("name", f"Panini {esp_name}")
                        p_active = p_ov.get("is_active", True)
                        if p_name in unavailable_dishes:
                            p_active = False

                        dishes.append({
                            "id": p_id,
                            "name": p_name,
                            "price": p_ov.get("price", 100),
                            "description": p_ov.get("description", f"{base_desc} Servido en pan panini rústico crujiente."),
                            "menu_key": menu_key,
                            "category_key": cat_key,
                            "category_name": cat_name,
                            "schedule_mode": p_ov.get("schedule_mode", "menu_default"),
                            "custom_start": p_ov.get("custom_start", ""),
                            "custom_end": p_ov.get("custom_end", ""),
                            "is_active": p_active
                        })

                        pita_id = f"{esp.get('id', 'it')}_pita"
                        pita_ov = dish_overrides.get(pita_id, {})
                        pita_name = pita_ov.get("name", f"Pita {esp_name}")
                        pita_active = pita_ov.get("is_active", True)
                        if pita_name in unavailable_dishes:
                            pita_active = False

                        dishes.append({
                            "id": pita_id,
                            "name": pita_name,
                            "price": pita_ov.get("price", 120),
                            "description": pita_ov.get("description", f"{base_desc} Servido en pan pita artesanal suave."),
                            "menu_key": menu_key,
                            "category_key": cat_key,
                            "category_name": cat_name,
                            "schedule_mode": pita_ov.get("schedule_mode", "menu_default"),
                            "custom_start": pita_ov.get("custom_start", ""),
                            "custom_end": pita_ov.get("custom_end", ""),
                            "is_active": pita_active
                        })

                if dishes:
                    dishes.sort(key=lambda d: d.get("name", "").lower())
                    categories.append({
                        "id": cat_key,
                        "name": cat_name,
                        "count": len(dishes),
                        "dishes": dishes
                    })

        categories.sort(key=lambda c: c.get("name", "").lower())
        total_dishes = sum(len(c["dishes"]) for c in categories)
        result_menus[menu_key] = {
            "title": meta.get("title"),
            "icon": meta.get("icon"),
            "schedule_label": meta.get("schedule_label"),
            "total_dishes": total_dishes,
            "categories": categories
        }

    return {
        "schedules": schedules,
        "menus": result_menus
    }

@app.get("/api/menu/full", tags=["Existencias & Catálogo"], summary="Catálogo jerárquico completo de platillos y precios")
def api_get_full_menu():
    """Retorna la jerarquía completa de los 3 menús con categorías, platillos, precios y horarios."""
    return get_full_hierarchical_menu()

@app.post("/api/menu/dish/update", tags=["Existencias & Catálogo"], summary="Edita atributos de un platillo del catálogo")
async def api_update_dish(request: Request):
    """Actualiza nombre, precio, descripción, horario y disponibilidad de un platillo específico."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para editar platillos."})

    data = await request.json()
    dish_id = str(data.get("dish_id", "")).strip()
    if not dish_id:
        return JSONResponse(status_code=400, content={"error": "Falta el ID del platillo (dish_id)"})

    state = load_restaurant_state()
    dish_overrides = state.setdefault("dish_overrides", {})
    unavailable_dishes = state.setdefault("unavailable_dishes", [])

    new_name = str(data.get("name", "")).strip()
    try:
        new_price = float(data.get("price", 0))
    except (ValueError, TypeError):
        new_price = 0.0
    new_desc = str(data.get("description", "")).strip()
    new_sched_mode = str(data.get("schedule_mode", "menu_default")).strip()
    custom_start = str(data.get("custom_start", "")).strip()
    custom_end = str(data.get("custom_end", "")).strip()
    is_active = bool(data.get("is_active", True))

    current_ov = dish_overrides.get(dish_id, {})
    old_name = current_ov.get("name", new_name)

    # Actualizar estado de disponibilidad
    if not is_active:
        if new_name and new_name not in unavailable_dishes:
            unavailable_dishes.append(new_name)
    else:
        if new_name in unavailable_dishes:
            unavailable_dishes.remove(new_name)
        if old_name in unavailable_dishes:
            unavailable_dishes.remove(old_name)

    dish_overrides[dish_id] = {
        "name": new_name,
        "price": new_price,
        "description": new_desc,
        "schedule_mode": new_sched_mode,
        "custom_start": custom_start,
        "custom_end": custom_end,
        "is_active": is_active,
        "_updated_at": time.time()
    }

    # También actualizar menu_ryu.json directamente para persistencia estricta
    menu_path = Path(__file__).parent / "menu_ryu.json"
    if menu_path.exists():
        try:
            with open(menu_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            # Buscar el platillo por ID en las secciones
            updated_raw = False
            for sec_name, sec_dict in raw_data.get("menu", {}).items():
                if isinstance(sec_dict, dict):
                    for cat_name, items_list in sec_dict.items():
                        if isinstance(items_list, list):
                            for d in items_list:
                                if isinstance(d, dict) and d.get("id") == dish_id:
                                    if new_name: d["name"] = new_name
                                    d["price"] = new_price
                                    if new_desc: d["description"] = new_desc
                                    updated_raw = True
                                    break
            if updated_raw:
                with open(menu_path, "w", encoding="utf-8") as f:
                    json.dump(raw_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Aviso al sincronizar menu_ryu.json: {e}")

    save_restaurant_state(state)
    return {"status": "ok", "dish_id": dish_id, "dish": dish_overrides[dish_id]}

@app.get("/api/menu/schedules", tags=["Promociones & Horarios"], summary="Consulta horarios de servicio de menús")
def api_get_schedules():
    """Retorna los horarios de los 3 menús."""
    state = load_restaurant_state()
    if state.get("schedules_override"):
        return state["schedules_override"]
    menu_path = Path(__file__).parent / "menu_ryu.json"
    if menu_path.exists():
        try:
            with open(menu_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("schedules", {})
        except Exception:
            pass
    return {}

@app.post("/api/menu/schedules", tags=["Promociones & Horarios"], summary="Modifica horarios de servicio de menús")
async def api_update_schedules(request: Request):
    """Actualiza los horarios de disponibilidad de los 3 menús."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para cambiar horarios."})

    data = await request.json()
    menu_path = Path(__file__).parent / "menu_ryu.json"
    if menu_path.exists():
        try:
            with open(menu_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            if "schedules" not in raw_data:
                raw_data["schedules"] = {}
            for k in ["japanese", "italian", "snacks"]:
                if k in data:
                    raw_data["schedules"][k] = data[k]
            with open(menu_path, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Error guardando horarios: {e}"})

    state = load_restaurant_state()
    state["schedules_override"] = data
    save_restaurant_state(state)
    return {"status": "ok", "schedules": data}

@app.get("/api/ingredients", tags=["Existencias & Catálogo"], summary="Lista de ingredientes con sustitutos y platillos afectados")
def api_get_ingredients():
    """Retorna el catálogo de 45+ ingredientes con estado de disponibilidad en tiempo real."""
    state = load_restaurant_state()
    catalog = state.get("ingredient_catalog", [])
    unavailable = set(state.get("unavailable_ingredients", []))
    
    enriched = []
    for ing in catalog:
        ing_id = ing.get("id", "").strip().lower()
        enriched.append({
            **ing,
            "available": ing_id not in unavailable
        })
        
    enriched.sort(key=lambda x: x.get("name", "").lower())
    return {
        "ingredients": enriched,
        "unavailable_count": len(unavailable),
        "total_count": len(enriched)
    }

@app.post("/api/ingredients/save", tags=["Existencias & Catálogo"], summary="Registra o actualiza un ingrediente en catálogo")
async def api_save_ingredient(request: Request):
    """Agrega o actualiza un ingrediente en el catálogo oficial."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para modificar ingredientes."})

    data = await request.json()
    ing_id = str(data.get("id", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "General")).strip()
    substitute = str(data.get("substitute", "otra opción disponible")).strip()
    affected = str(data.get("affected_dishes", "")).strip()

    if not ing_id or not name:
        return JSONResponse(status_code=400, content={"error": "ID y Nombre son obligatorios"})

    state = load_restaurant_state()
    catalog = state.setdefault("ingredient_catalog", [])
    
    found = False
    for ing in catalog:
        if ing.get("id") == ing_id:
            ing["name"] = name
            ing["category"] = category
            ing["substitute"] = substitute
            ing["affected_dishes"] = affected
            found = True
            break
            
    if not found:
        catalog.append({
            "id": ing_id,
            "name": name,
            "category": category,
            "substitute": substitute,
            "affected_dishes": affected
        })

    save_restaurant_state(state)
    return {"status": "ok", "ingredient": {"id": ing_id, "name": name, "category": category, "substitute": substitute, "affected_dishes": affected}}

# ======================================================================
# GESTIÓN DINÁMICA DE CONDICIONES DE ENTREGA Y TARIFAS ESPECIALES
# ======================================================================

def _ensure_delivery_settings():
    state = load_restaurant_state()
    del_settings = state.get("delivery_settings")
    if not del_settings or not isinstance(del_settings, dict):
        menu_path = Path(__file__).parent / "menu_ryu.json"
        raw_zones = []
        if menu_path.exists():
            try:
                with open(menu_path, "r", encoding="utf-8") as f:
                    mdata = json.load(f)
                    raw_zones = mdata.get("service_policies", {}).get("delivery_rules", {}).get("special_remote_zones", [])
            except Exception:
                pass
        special_zones = []
        for z in raw_zones:
            special_zones.append({
                "id": z.get("zone_id", f"zon_{len(special_zones)+1:02d}"),
                "name": z.get("name", ""),
                "fee": float(z.get("fee", 0.0)),
                "enabled": True,
                "aliases": z.get("aliases", []),
                "notes": "Tarifa especial foránea"
            })
        special_zones.sort(key=lambda x: x.get("name", "").lower())
        del_settings = {
            "urban_daytime_fee": 0.0,
            "night_surcharge_enabled": True,
            "night_surcharge_mode": "auto",
            "night_surcharge_time": "19:00",
            "night_surcharge_fee": 15.0,
            "special_zones": special_zones
        }
        state["delivery_settings"] = del_settings
        save_restaurant_state(state)
    return del_settings

@app.get("/api/delivery-settings", tags=["Condiciones de Entrega"], summary="Consulta condiciones de entrega y catálogo de zonas especiales")
def api_get_delivery_settings():
    """Retorna las condiciones de entrega, recargo nocturno y catálogo de zonas especiales."""
    settings = _ensure_delivery_settings()
    from voice_engine_ryu import get_delivery_conditions_summary
    summary, is_night_active = get_delivery_conditions_summary(load_restaurant_state())
    return {
        "status": "ok",
        "settings": settings,
        "current_status": {
            "is_night_active": is_night_active,
            "summary_text": summary
        }
    }

@app.post("/api/delivery-settings", tags=["Condiciones de Entrega"], summary="Actualiza configuración general de entregas")
async def api_update_delivery_settings(request: Request):
    """Actualiza la configuración general de entrega (tarifas, horas y modos)."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para modificar condiciones de entrega."})

    data = await request.json()
    state = load_restaurant_state()
    settings = state.setdefault("delivery_settings", _ensure_delivery_settings())

    if "urban_daytime_fee" in data:
        try: settings["urban_daytime_fee"] = float(data["urban_daytime_fee"])
        except (ValueError, TypeError): pass
    if "night_surcharge_enabled" in data:
        settings["night_surcharge_enabled"] = bool(data["night_surcharge_enabled"])
    if "night_surcharge_mode" in data:
        settings["night_surcharge_mode"] = str(data["night_surcharge_mode"]).strip() # "auto", "forced_on", "forced_off"
    if "night_surcharge_time" in data:
        settings["night_surcharge_time"] = str(data["night_surcharge_time"]).strip()
    if "night_surcharge_fee" in data:
        try: settings["night_surcharge_fee"] = float(data["night_surcharge_fee"])
        except (ValueError, TypeError): pass
    if "special_zones" in data and isinstance(data["special_zones"], list):
        settings["special_zones"] = data["special_zones"]
        settings["special_zones"].sort(key=lambda x: x.get("name", "").lower())

    save_restaurant_state(state)
    return {"status": "ok", "settings": settings}

@app.post("/api/delivery-settings/zone/toggle", tags=["Condiciones de Entrega"], summary="Activa o desactiva la tarifa de una zona especial")
async def api_toggle_delivery_zone(request: Request):
    """Activa o desactiva la tarifa especial de una zona en tiempo real."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado."})

    data = await request.json()
    zone_id = str(data.get("zone_id", "")).strip()
    enabled = bool(data.get("enabled", True))

    state = load_restaurant_state()
    settings = state.setdefault("delivery_settings", _ensure_delivery_settings())
    found = False
    for z in settings.get("special_zones", []):
        if z.get("id") == zone_id:
            z["enabled"] = enabled
            found = True
            break

    if not found:
        return JSONResponse(status_code=404, content={"error": "Zona no encontrada."})

    save_restaurant_state(state)
    return {"status": "ok", "zone_id": zone_id, "enabled": enabled}

@app.post("/api/delivery-settings/zone/save", tags=["Condiciones de Entrega"], summary="Crea o actualiza una zona especial de entrega")
async def api_save_delivery_zone(request: Request):
    """Crea o actualiza una zona especial de entrega con su costo y alias."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado."})

    data = await request.json()
    name = str(data.get("name", "")).strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "El nombre de la zona es obligatorio."})

    zone_id = str(data.get("id", "")).strip()
    if not zone_id:
        zone_id = f"zon_{int(time.time())}"

    try:
        fee = float(data.get("fee", 0.0))
    except (ValueError, TypeError):
        fee = 0.0

    raw_aliases = data.get("aliases", [])
    if isinstance(raw_aliases, str):
        aliases = [a.strip() for a in raw_aliases.split(",") if a.strip()]
    elif isinstance(raw_aliases, list):
        aliases = [str(a).strip() for a in raw_aliases if str(a).strip()]
    else:
        aliases = []

    notes = str(data.get("notes", "")).strip()
    enabled = bool(data.get("enabled", True))

    state = load_restaurant_state()
    settings = state.setdefault("delivery_settings", _ensure_delivery_settings())
    zones = settings.setdefault("special_zones", [])

    found = False
    for z in zones:
        if z.get("id") == zone_id:
            z["name"] = name
            z["fee"] = fee
            z["enabled"] = enabled
            z["aliases"] = aliases
            z["notes"] = notes
            found = True
            break

    if not found:
        zones.append({
            "id": zone_id,
            "name": name,
            "fee": fee,
            "enabled": enabled,
            "aliases": aliases,
            "notes": notes
        })

    zones.sort(key=lambda x: x.get("name", "").lower())
    save_restaurant_state(state)
    return {"status": "ok", "zone": {"id": zone_id, "name": name, "fee": fee, "enabled": enabled, "aliases": aliases, "notes": notes}}

@app.delete("/api/delivery-settings/zone/{zone_id}", tags=["Condiciones de Entrega"], summary="Elimina una zona especial de entrega")
async def api_delete_delivery_zone(zone_id: str, request: Request):
    """Elimina una zona especial de entrega."""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado."})

    state = load_restaurant_state()
    settings = state.setdefault("delivery_settings", _ensure_delivery_settings())
    zones = settings.setdefault("special_zones", [])

    before_len = len(zones)
    settings["special_zones"] = [z for z in zones if z.get("id") != zone_id]

    if len(settings["special_zones"]) == before_len:
        return JSONResponse(status_code=404, content={"error": "Zona no encontrada."})

    save_restaurant_state(state)
    return {"status": "ok", "deleted_zone_id": zone_id}

@app.get("/api/menu-items", tags=["Existencias & Catálogo"], summary="Catálogo consolidado de platillos para el buscador")
def get_menu_items():
    """Catálogo aplanado de todos los platillos para el buscador del dashboard"""
    full_menu = get_full_hierarchical_menu()
    items = []
    for menu_key, m_info in full_menu.get("menus", {}).items():
        for cat in m_info.get("categories", []):
            for d in cat.get("dishes", []):
                items.append({
                    "id": d["id"],
                    "name": d["name"],
                    "category": cat["name"],
                    "price": d["price"],
                    "menu": m_info["title"]
                })
    return items

@app.get("/api/kitchen-prompt-preview", tags=["Monitor IA & Especificaciones"], summary="Vista previa del prompt dinámico inyectado al LLM")
def get_kitchen_prompt_preview(request: Request):
    """Vista previa del bloque de prompt dinámico que la IA lee en cada llamada (requiere auth)"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para ver el prompt interno."})
    prompt = build_kitchen_dynamic_prompt()
    return {"prompt": prompt}


# ======================================================================
# RUTAS DEL ESTUDIO DE GRABACIÓN DE VOZ (VOICE STUDIO)
# ======================================================================

@app.get("/api/voice-studio/manifest", tags=["Estudio de Grabación (Voice Studio)"], summary="Manifiesto del catálogo con estado de grabación")
def api_voice_studio_manifest():
    """Retorna el catálogo completo con el estado de grabación de cada ítem"""
    return voice_studio_backend.get_manifest_data()

@app.post("/api/voice-studio/upload", tags=["Estudio de Grabación (Voice Studio)"], summary="Sube y transcodifica un clip de voz a G.711 A-law 8kHz")
async def api_voice_studio_upload(
    request: Request,
    item_id: str = Form(...),
    audio_file: UploadFile = File(...)
):
    """Recibe la grabación del navegador y la transcodifica a G.711 A-law 8000Hz"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para grabar voz."})

    try:
        raw_audio = await audio_file.read()
        result = voice_studio_backend.save_item_recording(item_id, raw_audio)
        return result
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.get("/api/voice-studio/audio/{item_id}", tags=["Estudio de Grabación (Voice Studio)"], summary="Reproduce el archivo WAV de alta fidelidad en el navegador")
def api_voice_studio_audio(item_id: str):
    """Reproduce el audio WAV de alta fidelidad en el navegador"""
    wav_path = voice_studio_backend.AUDIO_DIR / f"{item_id}.wav"
    if not wav_path.exists():
        return JSONResponse(status_code=404, content={"error": "Audio no encontrado."})
    return FileResponse(str(wav_path), media_type="audio/wav")

@app.delete("/api/voice-studio/audio/{item_id}", tags=["Estudio de Grabación (Voice Studio)"], summary="Elimina una grabación para re-grabarla")
def api_voice_studio_delete(item_id: str, request: Request):
    """Elimina una grabación para re-grabarla"""
    if not verify_admin_auth(request):
        return JSONResponse(status_code=401, content={"error": "No autorizado para eliminar audios."})
    return voice_studio_backend.delete_item_recording(item_id)

@app.post("/api/voice-studio/test-preview", tags=["Estudio de Grabación (Voice Studio)"], summary="Concatena clips seleccionados para escuchar la comanda continua")
async def api_voice_studio_preview(request: Request):
    """Concatena clips seleccionados para escuchar la orden completa"""
    data = await request.json()
    item_ids = data.get("item_ids", [])
    try:
        wav_bytes = voice_studio_backend.concatenate_clips_wav(item_ids)
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


# ======================================================================
# EXPORTACIÓN DINÁMICA DE ESPECIFICACIÓN OPENAPI (YAML / JSON)
# ======================================================================

@app.get("/api/openapi.yaml", tags=["Monitor IA & Especificaciones"], summary="Descarga la especificación formal OpenAPI 3.1 en formato YAML")
@app.get("/openapi.yaml", include_in_schema=False)
def get_openapi_yaml():
    """Retorna la especificación OpenAPI completa en formato YAML estándar para Swagger Editor y CI/CD."""
    openapi_schema = app.openapi()
    yaml_spec = yaml.dump(openapi_schema, sort_keys=False, allow_unicode=True)
    return Response(content=yaml_spec, media_type="application/x-yaml")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
