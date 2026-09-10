"""
======================================================================
RESTAURANTE RYU - SERVIDOR ULTRA RÁPIDO (<1 SEG LATENCIA)
Reconocimiento en tiempo real + Respuesta inmediata + Edge-TTS + Telegram
======================================================================
"""

import os
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from voice_engine_ryu import RyuVoiceAgent
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
