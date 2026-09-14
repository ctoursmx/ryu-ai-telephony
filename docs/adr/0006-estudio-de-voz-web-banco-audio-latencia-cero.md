# ADR-0006: Estudio de Grabación Web (Voice Studio) y Banco de Audio Pregrabado en RAM

* **Estado**: `Aceptada`
* **Fecha**: 2026-09-13
* **Decisores**: Arquitectura de Audio y Dirección de Ryu
* **Contexto Técnico**: `voice_studio_backend.py`, `sip_telephony_service.py`, `templates/admin_dashboard.html`, `audio_clips/`

---

## 1. Contexto y Planteamiento del Problema

Para mejorar la conexión con los clientes de Tequila, se evaluó clonar la voz del dueño con acento local. Sin embargo:
1. **ElevenLabs / PlayHT**: Requieren un plan comercial mensual de alto costo y cobran por cada mil caracteres generados. Para 1,700 llamadas semanales (~7,360 llamadas al mes, promedio 800 caracteres por llamada = ~5.8 millones de caracteres), el costo ascendería a **más de $600 - $900 USD mensuales**.
2. **Latencia de Red TTS**: Llamar a una API externa de voz clonada introduce entre 600 ms y 1,200 ms adicionales en cada turno de la conversación telefónica.

El dueño del restaurante manifestó su total disposición a dedicar el tiempo necesario para pregrabar su voz para los 176 platillos y las frases recurrentes del flujo conversacional, con tal de que quede bien hecho y con costo recurrente cero.

---

## 2. Factores Clave de Decisión

* **Cero costo de voz recurrente ($0.00 USD/mes)** en telefonía en vivo.
* **Cero latencia de síntesis (0 ms)**: Audio pre-cargado directamente en la memoria RAM del servidor.
* **Acento 100% auténtico y natural** de Tequila, Jalisco.
* **Herramienta web cómoda y accesible** desde teléfonos inteligentes (Safari en iPhone y Chrome en Android) y computadoras de escritorio.
* **Respaldo Híbrido**: Cualquier frase o platillo no grabado debe recurrir automáticamente a síntesis neural sin que la llamada falle.

---

## 3. Opciones Consideradas

### Opción A: Clonación en la Nube con ElevenLabs (Opción A previa)
* **Ventajas**: Síntesis dinámica de cualquier texto con la voz clonada.
* **Desventajas**: Costos recurrentes mensuales insostenibles a 1,700 llamadas/semana, latencia elevada.

### Opción B: Voice Studio Web Integrado con Banco de Clips en RAM (Opción B elegida)
* **Ventajas**:
  - Pestaña `🎙️ Estudio de Voz` en `/admin` con teleprompter, grabación por micrófono web y visualizador de onda.
  - Transcodificación en servidor con PyAV y soxr a códec telefónico G.711 A-law (8kHz) y WAV (16kHz).
  - Los archivos `.alaw` se cargan en `AUDIO_CACHE_RAM`, respondiendo con latencia 0 ms.
  - El catálogo de 233 elementos (176 platillos, 25 frases de flujo, 32 números) permite cubrir el 95%+ de las respuestas telefónicas.
* **Desventajas**: Requiere inversión de tiempo inicial para grabar los clips.

---

## 4. Decisión Adoptada

Se implementó la **Opción B**:
1. **Manifiesto Oficial (`voice_studio_manifest.json`)**: Gestiona los 233 elementos clasificados por categoría (`flow`, `japanese`, `snacks`, `italian`, `numbers`).
2. **Transcodificación Automática**: El backend FastAPI recibe el blob de audio de cualquier navegador (`audio/webm`, `audio/mp4`, `audio/ogg`), lo decodifica con PyAV a PCM 16-bit, remuestrea a 8000 Hz con `soxr HQ`, calibra a -1.4 dBFS y genera el archivo `.alaw` y `.wav`.
3. **Caché en RAM en Tiempo Real**: Al guardar un audio, `load_voice_studio_clips()` actualiza la memoria del motor SIP inmediatamente sin necesidad de reiniciar el contenedor.
4. **Fallback Híbrido**: Si una frase o platillo aún está en estado `pending`, `synthesize_speech_alaw()` genera el audio mediante Edge-TTS con la voz `es-MX-DaliaNeural`.

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Costo mensual de síntesis de voz: **$0.00 USD**.
* Latencia de reproducción: **0 ms** (lectura directa desde memoria RAM).
* Respaldo continuo: el usuario puede grabar a su propio ritmo.

---

## 6. Cumplimiento y Verificación

* Pruebas automatizadas en `test_voice_studio_e2e.py` y prueba remota en producción en `test_vps_voice_studio.py`.
