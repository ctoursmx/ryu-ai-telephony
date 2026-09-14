# ADR-0010: Implementación de Circuit Breaker y Observabilidad en Tiempo Real (Nivel 5)

* **Estado**: `Aceptada`
* **Fecha**: 2026-09-13
* **Decisores**: Arquitecto de Sistemas de Tiempo Real & Ingeniero Principal SRE/DevOps
* **Contexto Técnico**: `circuit_breaker.py`, `voice_engine_ryu.py`, `sip_telephony_service.py`, `server_telephony_ryu.py`, `tests/stress_test_telephony.py`, `.github/workflows/cd.yml`

---

## 1. Contexto y Planteamiento del Problema

El conmutador telefónico con inteligencia artificial del Restaurante Ryu gestiona llamadas en vivo sobre RTP/SIP conectando a la troncal Zadarma con el número virtual `+52 33 8526 1250`. 
En un entorno de producción que atiende pedidos en horarios pico, cualquier fluctuación transitoria en APIs externas de síntesis de voz (Edge-TTS o ElevenLabs), picos de jitter o latencia superiores a 800ms pueden provocar silencios incómodos o desconexión abrupta de la llamada por parte del usuario.

Para alcanzar el **Nivel 5 de Madurez Arquitectónica (Resiliencia Activa, Observabilidad en Vivo y Simulación de Estrés)** sin incurrir en costos de licenciamiento ($0 USD de costo operativo), se requiere:
1. Aislar las fallas de síntesis de voz mediante un patrón **Circuit Breaker** reactivo y no bloqueante.
2. Exponer telemetría viva del servicio, memoria y troncal SIP mediante un endpoint de salud (`/health`) apto para monitores externos gratuitos (UptimeRobot, BetterStack).
3. Integrar observabilidad de excepciones en tiempo real mediante **Sentry** de forma estrictamente condicional y no intrusiva.
4. Validar la estabilidad bajo alta carga mediante un simulador de estrés asíncrono (`asyncio`) que emule hasta 50 llamadas simultáneas.
5. Diseñar el pipeline de despliegue continuo (CD) con compuerta de calidad automatizada en GitHub Actions.

---

## 2. Factores Clave de Decisión (Drivers Arquitectónicos)

* **Cero Caídas en Llamadas en Vivo**: Si la síntesis de voz se degrada o tarda más de 800ms, la llamada debe continuar sin silencios usando audios pregrabados o en memoria RAM.
* **Costo Operativo de $0.00 USD**: Todas las herramientas de resiliencia, monitoreo y telemetría deben aprovechar capas gratuitas o utilerías nativas de Python (`psutil`, Sentry Developer Free Tier, UptimeRobot 60s pings).
* **No Invasividad y Compatibilidad**: El núcleo SIP de `pyVoIP`, los sockets UDP y la lógica de negocio deben permanecer intactos.
* **Observabilidad Condicional**: Si las variables de telemetría no están configuradas, el sistema debe operar con total normalidad sin emitir advertencias críticas.
* **Capacidad Concurrente Demostrable**: La máquina de estados FSM y el subsistema de comandas deben soportar 50 llamadas simultáneas con latencia menor a 1ms por turno.

---

## 3. Opciones Consideradas

### Opción A: Reintentos Lineales Bloqueantes y APM Comercial
* **Descripción**: Implementar bucles de reintento (`retry` con backoff exponencial) para la síntesis de audio y contratar suites comerciales de observabilidad (Datadog, New Relic).
* **Ventajas**: Fácil de programar mediante decoradores estándar.
* **Desventajas**: Los reintentos lineales acumulan latencia (2 a 4 segundos de silencio), colapsando el canal de audio telefónico. Las herramientas APM comerciales implican suscripciones mensuales incompatibles con el presupuesto de $0 USD.

### Opción B: Circuit Breaker Desacoplado + Health Check + Sentry Condicional + Simulador Asyncio (Elegida)
* **Descripción**:
  1. Diseñar `circuit_breaker.py` con estados formales `CLOSED`, `OPEN` y `HALF_OPEN`, con umbral de 3 fallos consecutivos y timeout estricto de 800ms.
  2. Al dispararse a `OPEN`, desviar instantáneamente el tráfico de voz al banco de audios en memoria RAM (`AUDIO_CACHE_RAM`) o audios pregrabados.
  3. Exponer `GET /health` en FastAPI con métricas de RSS de proceso (`psutil`), memoria del sistema, estado del registro SIP Zadarma y estadísticas del Circuit Breaker.
  4. Integrar condicionalmente `sentry-sdk` en `server_telephony_ryu.py` supeditado a la existencia de `SENTRY_DSN`.
  5. Crear `tests/stress_test_telephony.py` con `asyncio.gather` para simular 10, 25 y 50 llamadas concurrentes deterministas.
  6. Añadir `.github/workflows/cd.yml` para despliegue automatizado por SSH tras pasar compuertas de calidad.
* **Ventajas**:
  - Resiliencia activa inmediata: el cliente nunca experimenta una llamada muda ni colgada.
  - $0 USD de costo operativo recurrente.
  - Monitoreo 24/7 integrable con servicios externos cada 60 segundos.
  - Cobertura de estrés validada matemáticamente.
* **Desventajas**: Requiere pruebas unitarias dedicadas para las transiciones de estado del Circuit Breaker.

---

## 4. Decisión Adoptada

Se adoptó la **Opción B**. El módulo utilitario `circuit_breaker.py` envuelve todas las llamadas de síntesis tanto en `voice_engine_ryu.py` (`speak()`) como en `sip_telephony_service.py` (`synthesize_speech_alaw()`). 
Si una llamada de voz excede 800ms o arroja excepción 3 veces consecutivas, el circuito conmuta a `OPEN` y entrega el saludo o frases precargadas en RAM de forma instantánea. Tras 15 segundos de enfriamiento (`recovery_timeout`), el circuito transiciona a `HALF_OPEN` para una prueba controlada y, si tiene éxito, se restablece a `CLOSED`.

El servidor HTTP FastAPI expone `/health` permitiendo que herramientas gratuitas de monitoreo (como UptimeRobot) alerten anomalías de memoria o caídas de troncal SIP sin consumir recursos del conmutador.

---

## 5. Consecuencias y Compromisos (Trade-offs)

### Impactos Positivos
* **Experiencia de Usuario Ininterrumpida**: Ante cortes de red o caídas de APIs externas, el cliente continúa la conversación con frases de respaldo con la voz del dueño.
* **Visibilidad en Tiempo Real**: Telemetría completa de memoria, sesiones activas y estado de registro SIP en un solo JSON estructurado.
* **Detección Temprana de Errores**: Excepciones no controladas enviadas a Sentry si está configurado el DSN.
* **Rendimiento Verificado**: El simulador de estrés demostró procesamiento de 50 llamadas simultáneas a más de 10,000 llamadas/segundo en FSM en memoria sin fugas de memoria.

### Impactos Negativos o Deuda Técnica Asumida
* Mientras el circuito permanezca en `OPEN`, los clientes recibirán respuestas genéricas o precargadas en lugar de síntesis personalizada en tiempo real, lo cual es preferible a una llamada muda.

---

## 6. Cumplimiento y Verificación

1. **Pruebas Unitarias de Circuit Breaker**:
   - `python -m unittest tests/test_circuit_breaker.py` valida estados `CLOSED`, `OPEN`, `HALF_OPEN`, timeouts y recuperación.
2. **Prueba de Estrés Concurrente**:
   - `python tests/stress_test_telephony.py --stages 10,25,50` valida 100% de éxito en 50 sesiones simultáneas.
3. **Endpoint de Salud**:
   - `GET /health` responde HTTP 200 OK con payload JSON completo.
4. **Auditoría de ADRs**:
   - `python tools/adr.py audit` confirma consistencia e indexación de los 10 ADRs.
5. **CI/CD**:
   - Workflows en `.github/workflows/ci.yml` y `.github/workflows/cd.yml` garantizan ejecución de pruebas antes de cada despliegue.

---

## 7. Enlaces y Referencias

* **MADR Template**: Version 3.0.0
* **ADR Relacionado**: [ADR-0006 (Voice Studio)](0006-estudio-de-voz-web-banco-audio-latencia-cero.md)
* **ADR Relacionado**: [ADR-0009 (Estrategia de Fallback y Latencia)](0009-estrategia-de-fallback-y-latencia-para-el-motor-de-voz.md)
* **Implementación**: [`circuit_breaker.py`](../../circuit_breaker.py), [`tests/stress_test_telephony.py`](../../tests/stress_test_telephony.py)
