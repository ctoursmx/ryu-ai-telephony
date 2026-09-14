# 🏛️ Registros de Decisión de Arquitectura (ADR) - Restaurante Ryu

Este directorio contiene los **Architecture Decision Records (ADR)** que documentan las decisiones técnicas, de infraestructura y de diseño de software más críticas del sistema de telefonía con inteligencia artificial para el **Restaurante Ryu**.

Seguimos una versión adaptada del formato **MADR (Markdown Architectural Decision Records)**.

---

## 📋 Índice Maestro de Decisiones

| ID | Título de la Decisión | Estado | Fecha | Componente |
| :--- | :--- | :---: | :---: | :--- |
| [**ADR-0001**](0001-telefonia-sip-rtp-zadarma-pyvoip.md) | Enlace Telefónico SIP/RTP Directo con Zadarma y pyVoIP Parcheado | `Aceptada` | 2026-03-01 | Telefonía VoIP / SIP |
| [**ADR-0002**](0002-pipeline-audio-g711-alaw-soxr-normalizacion.md) | Pipeline Acústico G.711 A-law 8kHz con Remuestreo soxr HQ y Normalización | `Aceptada` | 2026-03-03 | DSP Acústico / Codecs |
| [**ADR-0003**](0003-transcripcion-local-faster-whisper-int8.md) | Motor de Transcripción Local faster-whisper int8 con Acoustic Priming | `Aceptada` | 2026-03-05 | STT / CPU Inferencing |
| [**ADR-0004**](0004-orquestacion-conversacional-llm-gpt4o-mini.md) | Orquestación Conversacional con GPT-4o-mini y Normalización Fonética | `Aceptada` | 2026-03-07 | LLM / Diálogo |
| [**ADR-0005**](0005-auditoria-matematica-deterministica-pedidos.md) | Auditoría Matemática Determinística en Python para Cálculo de Cuentas | `Aceptada` | 2026-03-09 | Órdenes / Finanzas |
| [**ADR-0006**](0006-estudio-de-voz-web-banco-audio-latencia-cero.md) | Estudio de Grabación Web (Voice Studio) y Banco de Audio Pregrabado en RAM | `Aceptada` | 2026-09-13 | Voz / Optimización |
| [**ADR-0007**](0007-seguridad-autenticacion-panel-control.md) | Autenticación Híbrida Blindada (HMAC Tokens + Rate Limiting) para /admin | `Aceptada` | 2026-09-11 | Seguridad / Web API |
| [**ADR-0008**](0008-despliegue-docker-host-networking.md) | Despliegue en Docker con Host Networking para VoIP en Servidor VPS | `Aceptada` | 2026-03-02 | DevOps / Infraestructura |

---

## 🛠️ Estados Posibles de un ADR

* **`Propuesta`**: En discusión o borrador inicial.
* **`En Revisión`**: Evaluándose activamente por el equipo de ingeniería.
* **`Aceptada`**: Aprobada y actualmente en producción en la base de código.
* **`Rechazada`**: No fue aprobada tras evaluar sus desventajas técnicas.
* **`Reemplazada`**: Quedó obsoleta por una nueva decisión (indica enlace al nuevo ADR).
* **`Deprecada`**: Ya no está en uso en el sistema.

---

## 🚀 Gestión de ADRs vía CLI

Puedes gestionar los ADRs de este repositorio utilizando la herramienta de línea de comandos:

```bash
# Crear un nuevo ADR
python tools/adr.py new "Titulo de la Nueva Decisión"

# Listar todos los ADRs con su estado actual
python tools/adr.py list

# Auditar integridad de enlaces y formato
python tools/adr.py audit
```
