# ADR-0009: Estrategia de Fallback y Control de Latencia para el Motor de Voz

* **Estado**: `Aceptada`
* **Fecha**: 2026-09-13
* **Decisores**: Arquitectura de Telefonía Ryu & Sistemas de Tiempo Real
* **Contexto Técnico**: `voice_engine_ryu.py`, `sip_telephony_service.py`, `voice_studio_backend.py`, Integración de Voz Clonada

---

## 1. Contexto y Planteamiento del Problema

El conmutador telefónico de Restaurante Ryu y Capri Cucina Italiana atiende aproximadamente **1,700 llamadas semanales** en Tequila, Jalisco. Para ofrecer una experiencia cálida, familiar y de confianza a los clientes locales, se busca proyectar la voz con el acento típico de la región mediante clonación de voz o audios pregrabados.

Sin embargo, en telefonía SIP en vivo sobre RTP analógico (G.711 A-law 8kHz), el silencio o "dead air" superior a **1,000 ms (1 segundo)** provoca que el cliente piense que la llamada se cortó ("¿bueno, bueno?"), cuelgue o hable encima del sistema (interrumpiendo la conversación).

Los motores de voz clonada (como ElevenLabs, XTTS v2 o F5-TTS en GPUs remotas) presentan dos grandes riesgos operacionales:
1. **Latencia variable por red y GPU**: En horas pico o saturación de cola, la inferencia y transferencia de audio puede tardar entre 1.2s y 3.5s, superando el umbral admisible de telefonía conversacional.
2. **Costo por minuto y fallos de servicio**: APIs externas pueden experimentar intermitencias de red, errores HTTP 504 Gateway Timeout o agotar cuotas mensuales.

Es indispensable contar con una estrategia determinista de control de latencia, timeouts estrictos y degradación elegante (graceful degradation) que garantice que ninguna llamada sufra retrasos perceptibles.

---

## 2. Factores Clave de Decisión (Drivers Arquitectónicos)

* **Latencia máxima admisible de síntesis**: El tiempo desde que el LLM genera el texto hasta que el primer paquete RTP de audio sale hacia el cliente no debe superar los **800 ms**.
* **Cero silencios muertos (Zero Dead Air)**: Si una respuesta dinámica compleja requiere tiempo de cómputo adicional, el sistema debe emitir una señal acústica o frase verbal de espera natural en menos de 400 ms.
* **Resiliencia ante caídas de red o GPU**: Si el motor de voz clonada se desconecta, falla o satura su cola, el conmutador telefónico debe continuar atendiendo la llamada sin interrupción.
* **Eficiencia de costos ($0.00 USD en frases frecuentes)**: Maximizar el uso de clips de audio locales pregrabados y precargados en memoria RAM.

---

## 3. Opciones Consideradas

### Opción A: Depender Exclusivamente de la API de Voz Clonada
* **Descripción**: Enviar cada respuesta del agente conversacional directamente a la API de clonación de voz (ej. ElevenLabs o servidor GPU local).
* **Ventajas**: Toda la llamada suena con la voz clonada.
* **Desventajas**: Latencia impredecible (>1.5s en muchas consultas), alto costo recurrente en llamadas masivas ($150 - $400 USD/mes), riesgo crítico de punto único de falla (si la API falla, el conmutador se enmudece).

### Opción B: Modelo Híbrido Escalonado con Circuit Breaker y Timeout a 800 ms (Elegida)
* **Descripción**: Arquitectura de 3 niveles con watchdog de latencia:
  1. **Nivel 1 (Banco Pregrabado en RAM - 0 ms)**: Para el 80% de los turnos previsibles (saludo, menú, dirección, preguntas de confirmación, números, nombres de los 170 platillos), se reproduce el clip G.711 A-law directamente desde la RAM.
  2. **Nivel 2 (Voz Clonada con Timeout a 800 ms)**: Para respuestas dinámicas no pregrabadas, se solicita la síntesis al motor clonado con un límite estricto de timeout de **800 ms**.
  3. **Nivel 3 (Fallback Automático a Frases de Espera o TTS Ultrarrápido)**: Si el motor de voz clonada no entrega el primer byte en 800 ms o devuelve error:
     - **3A**: Inyección inmediata de frase de espera en la voz del dueño ("Permíteme un segundito...", "Con gusto, déjame revisar con cocina...") para ganar tiempo sin silencio.
     - **3B**: Salto transparente a Microsoft Edge-TTS (`es-MX-DaliaNeural`), el cual responde en ~250-350 ms y se transcodifica en RAM a 8kHz G.711 A-law.

---

## 4. Decisión Adoptada

Se adopta la **Opción B**: un protocolo escalonado de 3 niveles con **Circuit Breaker** y **Watchdog de Timeout de 800 ms**:

```
                              [Texto a Pronunciar]
                                       |
                     ¿Existe clip pregrabado en RAM?
                                  /         \
                            SÍ   /           \  NO
                                /             \
                   [NIVEL 1: 0ms RAM]    [NIVEL 2: Motor Voz Clonada]
                   Audio pregrabado       Watchdog: Timeout a 800 ms
                   del dueño (G.711)                  |
                                         ¿Respondió en <800 ms?
                                            /           \
                                      SÍ   /             \  NO / ERROR
                                          /               \
                             [Transmitir Audio]    [NIVEL 3: Fallback Rápido]
                             Voz Clonada OK        1. Reproducir frase de espera pregrabada
                                                   2. O sintetizar vía Edge-TTS (<350 ms)
```

### Reglas de Implementación del Protocolo:
1. **Timeout Watchdog (`asyncio.wait_for(timeout=0.8)`)**: Toda llamada al motor de clonación estará envuelta en un temporizador de cancelación de 800 ms.
2. **Circuit Breaker Automático**: Si el motor de voz clonada falla o supera el timeout en 3 ocasiones consecutivas dentro de una misma ventana de 5 minutos, el Circuit Breaker pasa al estado `OPEN` (Abierto) durante 60 segundos, enviando todas las solicitudes dinámicas directamente al fallback sin penalizar las llamadas activas.
3. **Frases de Relleno Acústico (Fillers Naturales)**: Se mantienen en RAM clips cortos pregrabados con entonación natural de Tequila:
   - `filler_01.alaw`: "A ver, permíteme tantito..."
   - `filler_02.alaw`: "Claro que sí, déjame checar con cocina..."
   - `filler_03.alaw`: "Un segundito por favor..."

---

## 5. Consecuencias y Compromisos (Trade-offs)

### Impactos Positivos
* **Garantía Estricta de Latencia**: Ninguna respuesta telefónica experimentará una pausa superior a 850 ms, erradicando el "dead air" y la frustración del cliente.
* **Continuidad Operativa al 100%**: Caídas de GPUs o APIs de clonación son transparentes para el cliente; el conmutador nunca cuelga ni enmudece.
* **Costo Controlado**: Más del 80% del audio se sirve desde el Voice Studio local en RAM a $0.00 USD.

### Impactos Negativos o Deuda Técnica Asumida
* **Variación de Timbre en Fallback Nivel 3**: Si ocurre una contingencia y se activa el fallback a Edge-TTS (`es-MX-DaliaNeural`), el cliente notará un cambio momentáneo de voz. Sin embargo, esto es infinitamente preferible a un corte o silencio de 3 segundos en la línea telefónica.

---

## 6. Cumplimiento y Verificación

* **Smoke Tests**: Pruebas sin red en `tests/run_smoke_tests.py` validan que la arquitectura de estados e imports soporte los controladores de fallback.
* **Auditoría de ADRs**: `python tools/adr.py audit` valida que este documento esté indexado y cumpla con la estructura formal.
* **Métricas de Latencia**: Telemetría en `server_telephony_ryu.py` y `sip_telephony_service.py` registrando el tiempo de sintetización (`tts_latency_ms`) en los logs estructurados JSONL.

---

## 7. Referencias y Enlaces

* **ADR-0002**: Pipeline de Audio G.711 A-law 8kHz con Remuestreador soxr HQ
* **ADR-0006**: Estudio de Grabación Web (Voice Studio) con Acento Local
* **Contrato de Telefonía Open Spec**: `docs/specs/telephony-spec.yaml`
* **Código de Audio y Síntesis**: `voice_engine_ryu.py` y `voice_studio_backend.py`

