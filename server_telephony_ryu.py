"""
======================================================================
RESTAURANTE RYU - SERVIDOR ULTRA RÁPIDO (<1 SEG LATENCIA)
Reconocimiento en tiempo real + Respuesta inmediata + Edge-TTS + Telegram
======================================================================
"""

import os
import json
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
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

app = FastAPI(title="Ryu Voice Telephony Server - Ultra Fast", version="2.0.0")

# Gestor de llamadas simultáneas en memoria (soporta 50+ llamadas en paralelo)
active_sessions: dict[str, RyuVoiceAgent] = {}

def get_agent_for_session(session_id: str, caller_phone: str = "+52 33 8526 1250", caller_name: str = "Cliente") -> RyuVoiceAgent:
    if session_id not in active_sessions:
        active_sessions[session_id] = RyuVoiceAgent(caller_phone=caller_phone, caller_name=caller_name)
    return active_sessions[session_id]

@app.get("/", response_class=HTMLResponse)
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

@app.post("/api/fast-chat")
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
    
    # 4. Síntesis instantánea con Edge-TTS
    audio_filename = f"fast_reply_{session_id}_{int(time.time() * 1000)}.mp3"
    await agent.speak(response_text, audio_filename)
    
    # 5. Mantenimiento automático de disco (elimina audios huérfanos > 5 min)
    cleanup_temp_audio_files(max_age_seconds=300)
    
    total_time = round((time.time() - t0) * 1000)
    print(f">>> [Llamada {session_id[:12]}] [Latencia: {total_time} ms] Cliente: '{user_text}' -> RyuBot: '{response_text[:30]}...'")
    
    return {
        "reply_text": response_text,
        "audio_url": f"/audio/{audio_filename}",
        "order_confirmed": agent.order_confirmed,
        "latency_ms": total_time,
        "session_id": session_id
    }


@app.get("/audio/{filename}")
def get_audio(filename: str):
    if os.path.exists(filename):
        return FileResponse(filename, media_type="audio/mpeg")
    return JSONResponse(status_code=404, content={"error": "Audio no encontrado"})

@app.get("/api/pos/orders/pending")
def api_get_pending_pos_orders(request: Request):
    """
    Endpoint para el agente local de Soft Restaurant en el restaurante de Tequila.
    Retorna la lista de comandas tomadas por la IA que requieren ser inyectadas e impresas.
    """
    secret = os.getenv("POS_BRIDGE_SECRET", "ryu_pos_secret_key_2026")
    auth_header = request.headers.get("X-POS-Token")
    if auth_header != secret and request.query_params.get("token") != secret:
        return JSONResponse(status_code=401, content={"error": "No autorizado para POS Bridge"})

    from soft_restaurant_bridge import get_pending_pos_orders
    orders = get_pending_pos_orders()
    return {"status": "ok", "count": len(orders), "orders": orders}


@app.post("/api/pos/orders/{order_id}/ack")
async def api_ack_pos_order(order_id: str, request: Request):
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
# RUTAS DE ADMINISTRACIÓN EN TIEMPO REAL (STOCK, PROMOCIONES Y HORARIOS)
# ======================================================================

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    """Panel de Control visual para celular y PC"""
    template_path = Path(__file__).parent / "templates" / "admin_dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Plantilla de administración no encontrada en templates/admin_dashboard.html</h1>", status_code=404)

@app.get("/api/state")
def get_state():
    """Retorna el estado dinámico actual"""
    return load_restaurant_state()

@app.post("/api/stock/ingredient")
async def toggle_ingredient(request: Request):
    """Conmuta la disponibilidad de un ingrediente crítico (ej. pulpo, camarón, etc.)"""
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

@app.post("/api/stock/dish")
async def toggle_dish(request: Request):
    """Conmuta la disponibilidad de un platillo específico"""
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

@app.post("/api/promotions")
async def update_promotions(request: Request):
    """Actualiza las promociones del día aplicadas en la IA"""
    data = await request.json()
    promotions = data.get("promotions", [])
    
    state = load_restaurant_state()
    state["daily_promotions"] = promotions
    save_restaurant_state(state)
    return state

@app.post("/api/announcement")
async def update_announcement(request: Request):
    """Actualiza avisos de demora, apertura o notas de cocina"""
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

@app.get("/api/menu-items")
def get_menu_items():
    """Catálogo aplanado de todos los platillos para el buscador del dashboard"""
    menu_path = Path(__file__).parent / "menu_ryu.json"
    items = []
    if menu_path.exists():
        try:
            with open(menu_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                menu = data.get("menu", {})
                for section_name, section_content in menu.items():
                    if isinstance(section_content, dict):
                        for cat_name, dish_list in section_content.items():
                            if isinstance(dish_list, list):
                                for d in dish_list:
                                    if isinstance(d, dict) and "name" in d:
                                        items.append({
                                            "id": d.get("id", ""),
                                            "name": d.get("name", ""),
                                            "category": cat_name.replace("_", " ").capitalize(),
                                            "price": d.get("price", 0)
                                        })
                            elif cat_name == "paninis_y_pitas" and isinstance(dish_list, dict):
                                for esp in dish_list.get("especialidades", []):
                                    items.append({
                                        "id": esp.get("id", ""),
                                        "name": f"Panini {esp.get('name', '')}",
                                        "category": "Paninis y Pitas",
                                        "price": 100
                                    })
                                    items.append({
                                        "id": esp.get("id", "") + "_p",
                                        "name": f"Pita {esp.get('name', '')}",
                                        "category": "Paninis y Pitas",
                                        "price": 120
                                    })
        except Exception as e:
            print(f"Error al leer menu_ryu.json: {e}")
    return items

@app.get("/api/kitchen-prompt-preview")
def get_kitchen_prompt_preview():
    """Vista previa del bloque de prompt dinámico que la IA lee en cada llamada"""
    prompt = build_kitchen_dynamic_prompt()
    return {"prompt": prompt}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
