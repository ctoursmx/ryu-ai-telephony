# 🍣 Restaurante Ryu - Sistema Telefónico con IA y Gestión de Pedidos

Sistema automatizado de recepcionista telefónica e inteligencia artificial conversacional para el restaurante **Ryu** y **Capri Cucina Italiana** en Tequila, Jalisco. Diseñado para atender llamadas telefónicas reales en tiempo real a través de VoIP (SIP), responder dudas sobre el menú, tomar pedidos a domicilio o para recoger en sucursal, auditar la matemática de los costos y despachar comandas estructuradas al canal de Telegram y sistemas de cocina.

---

## 🚀 Arquitectura del Sistema

```mermaid
flowchart TD
    Cliente([📱 Cliente Llamando]) -->|Llamada Telefónica PSTN| Zadarma[☁️ Zadarma VoIP DID: +52 33 8526 1250]
    Zadarma -->|SIP / RTP G.711 A-law| Service[⚡ sip_telephony_service.py / Docker]
    
    subgraph Core Engine [Motor en Memoria RAM & CPU]
        Service -->|Audio PCM 8kHz| STT[🎙️ faster-whisper CTranslate2 int8]
        STT -->|Texto Transcrito| LLM[🧠 OpenAI GPT-4o-mini]
        LLM -->|Texto de Respuesta| TTS[🔊 Edge-TTS es-MX-DaliaNeural + soxr HQ]
        TTS -->|RTP Monotónico 50pps| Service
        LLM -->|Comanda Confirmada| Auditor[🧮 Auditor Matemático Python]
    end

    Auditor -->|Ticket Formateado| Telegram[📲 Bot de Telegram Cocina / Reparto]
```

* **Telefonía SIP/RTP:** Enlace troncal SIP directo con Zadarma mediante `pyVoIP`, con parches de latencia cero, temporizador multimedia de 1ms, recepción simétrica de paquetes de audio (RFC 4961) y detector de corte de flujo RTP para colgado instantáneo.
* **Speech-to-Text (STT):** `faster-whisper` (`base`, cuantización `int8`) ejecutándose 100% en RAM y CPU local. Latencia promedio: **~1.4 segundos** a costo **$0.00 USD/minuto**.
* **Inteligencia Artificial (LLM):** OpenAI `gpt-4o-mini` guiado por el catálogo estructurado `menu_ryu.json` y el prompt especializado `prompt_voice_telephone_ryu.md`.
* **Text-to-Speech (TTS):** Microsoft Edge-TTS (`es-MX-DaliaNeural`), filtrado y remuestreado con `soxr` y escalado acústico para telefonía analógica a 8 kHz G.711 A-law.
* **Auditoría Matemática:** Algoritmo determinístico en Python que previene alucinaciones aritméticas sumando platillos, extras y costos de envío antes de emitir la comanda.

---

## 📂 Estructura del Proyecto

```text
.
├── docs/                                # Documentación de arquitectura y especificaciones formales
│   ├── adr/                             # Architecture Decision Records (Estándar MADR)
│   │   ├── README.md                    # Índice maestro de decisiones arquitectónicas
│   │   ├── template.md                  # Plantilla estándar MADR
│   │   └── 0001..0008-*.md              # Registros de decisión técnica (VoIP, STT, LLM, etc.)
│   └── specs/                           # Especificaciones formales Open Spec
│       ├── openapi.yaml                 # Especificación OpenAPI 3.1.0 (formato YAML)
│       ├── openapi.json                 # Especificación OpenAPI 3.1.0 (formato JSON)
│       ├── telephony-spec.yaml          # Open Spec: VoIP SIP/RTP, G.711 A-law y VAD
│       ├── order-contract-spec.yaml     # Open Spec: Contrato determinístico de comandas
│       └── README.md                    # Guía de especificaciones y sincronización
├── tools/                               # Herramientas de automatización y CLI
│   ├── adr.py                           # CLI gestor de ADRs (list, new, audit)
│   └── export_openapi.py                # Exportador sincronizado de esquemas OpenAPI
├── schemas_ryu.py                       # Modelos Pydantic formales para OpenAPI 3.1
├── test_specs.py                        # Suite de pruebas automatizadas para ADR y Open Spec
├── server_telephony_ryu.py              # API FastAPI del conmutador, Voice Studio y panel
├── sip_telephony_service.py             # Servicio de telefonía SIP VoIP en tiempo real
├── voice_engine_ryu.py                  # Motor conversacional, LLM, VAD y despacho
├── voice_studio_backend.py              # Backend del estudio de grabación de voz
├── menu_ryu.json                        # Catálogo y reglas de negocio estructuradas para IA
├── prompt_voice_telephone_ryu.md        # Personalidad e instrucciones de la recepcionista
├── Dockerfile                           # Definición de contenedor optimizado (Python 3.11 Debian)
├── docker-compose.yml                   # Orquestación de producción con network_mode: host
├── requirements.txt                     # Dependencias de Python verificadas
└── README.md                            # Documentación integral del proyecto
```

---

## 🏛️ Registros de Decisión Arquitectónica (ADR) & Open Spec

El proyecto implementa el estándar **MADR (Markdown Architectural Decision Records)** y **Open Spec** para garantizar reproducibilidad técnica, trazabilidad de decisiones de ingeniería y contratos de API estrictos.

### 📋 Registros de Decisión (ADR)
Ubicados en [`docs/adr/`](file:///c:/Users/HP/Desktop/Ryu/docs/adr/README.md):

| ID | Decisión | Estado | Contexto Clave |
| :--- | :--- | :--- | :--- |
| **[ADR-0001](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0001-telefonia-sip-rtp-zadarma-pyvoip.md)** | Telefonía SIP/RTP Directa con Zadarma y pyVoIP Parcheado | `Aceptada` | Puerto UDP 5060, temporizador 1ms, Symmetric RTP (RFC 4961). |
| **[ADR-0002](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0002-pipeline-audio-g711-alaw-soxr-normalizacion.md)** | Pipeline de Audio G.711 A-law 8kHz con Remuestreador soxr HQ | `Aceptada` | 50 pps (160 bytes cada 20 ms), normalización a -1.4 dBFS. |
| **[ADR-0003](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0003-transcripcion-local-faster-whisper-int8.md)** | Transcripción Local con faster-whisper int8 en CPU/RAM Pool | `Aceptada` | $0 USD/minuto, latencia < 1.4s, acoustic priming de platillos. |
| **[ADR-0004](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0004-orquestacion-conversacional-llm-gpt4o-mini.md)** | Orquestación Conversacional con OpenAI GPT-4o-mini | `Aceptada` | Inyección dinámica de disponibilidad y blindaje contra prompt attacks. |
| **[ADR-0005](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0005-auditoria-matematica-deterministica-pedidos.md)** | Auditoría Matemática Determinística de Cuentas y Comandas | `Aceptada` | Prohibición al LLM de hacer aritmética; cálculo determinista en Python. |
| **[ADR-0006](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0006-estudio-de-voz-web-banco-audio-latencia-cero.md)** | Estudio de Grabación Web (Voice Studio) con Acento Local | `Aceptada` | Banco de 233 audios en RAM; 0ms latencia de síntesis y $0 USD costo. |
| **[ADR-0007](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0007-seguridad-autenticacion-panel-control.md)** | Autenticación Criptográfica HMAC-SHA256 y Anti-Fuerza Bruta | `Aceptada` | Tokens con salting, rate limiting por IP y expiración periódica. |
| **[ADR-0008](file:///c:/Users/HP/Desktop/Ryu/docs/adr/0008-despliegue-docker-host-networking.md)** | Despliegue en Docker con Host Networking Mode | `Aceptada` | Eliminación de NAT SIP traversal y acceso directo a interfaces de red. |

#### Herramienta CLI de Gestión (`tools/adr.py`):
```bash
# Listar todas las decisiones arquitectónicas
python tools/adr.py list

# Crear un nuevo registro a partir de la plantilla estándar
python tools/adr.py new "Migración a PostgreSQL AGE para grafos"

# Auditar consistencia técnica e integridad del índice
python tools/adr.py audit
```

---

### 📐 Especificaciones de Contratos Técnicos (Open Spec)
Ubicadas en [`docs/specs/`](file:///c:/Users/HP/Desktop/Ryu/docs/specs/README.md):

* **OpenAPI 3.1.0:** [`docs/specs/openapi.yaml`](file:///c:/Users/HP/Desktop/Ryu/docs/specs/openapi.yaml) y [`docs/specs/openapi.json`](file:///c:/Users/HP/Desktop/Ryu/docs/specs/openapi.json).
* **Especificación VoIP / Audio:** [`docs/specs/telephony-spec.yaml`](file:///c:/Users/HP/Desktop/Ryu/docs/specs/telephony-spec.yaml).
* **Contrato de Comandas:** [`docs/specs/order-contract-spec.yaml`](file:///c:/Users/HP/Desktop/Ryu/docs/specs/order-contract-spec.yaml).

#### Interfaces Vivas en el Servidor:
* **Swagger UI:** [`http://89.167.43.130:8000/docs`](http://89.167.43.130:8000/docs)
* **ReDoc:** [`http://89.167.43.130:8000/redoc`](http://89.167.43.130:8000/redoc)
* **OpenAPI YAML en vivo:** [`http://89.167.43.130:8000/api/openapi.yaml`](http://89.167.43.130:8000/api/openapi.yaml)

#### Comprobación Automatizada de Especificaciones:
```bash
# Regenerar OpenAPI sincronizado desde el código fuente
python tools/export_openapi.py

# Ejecutar suite de pruebas unitarias
python -m unittest test_specs.py
```

---

## ⚙️ Configuración y Variables de Entorno

1. Copia la plantilla `.env.example` a un nuevo archivo `.env`:
   ```bash
   cp .env.example .env
   ```

2. Configura tus credenciales en el archivo `.env`:
   ```dotenv
   # OpenAI
   OPENAI_API_KEY=sk-proj-tu_clave_de_openai_aqui

   # Zadarma SIP
   ZADARMA_SIP_SERVER=sip.zadarma.com
   ZADARMA_SIP_USER=20432
   ZADARMA_SIP_PASSWORD=tu_contraseña_sip
   ZADARMA_PHONE_NUMBER=+523385261250

   # Telegram
   TELEGRAM_BOT_TOKEN=tu_telegram_bot_token
   TELEGRAM_CHAT_ID=-100xxxxxxxxxx
   ```

---

## 🐳 Despliegue con Docker y Docker Compose

### En Servidores Linux / VPS (Recomendado para Producción)
En Linux, el contenedor corre con `network_mode: host` para recibir el tráfico UDP de SIP (puerto 5060) y RTP directamente sin lidiar con mapeos complejos de puertos dinámicos.

1. **Construir y levantar el contenedor en segundo plano:**
   ```bash
   docker compose up -d --build
   ```

2. **Monitorear los logs en tiempo real:**
   ```bash
   docker compose logs -f
   ```

3. **Detener el servicio:**
   ```bash
   docker compose down
   ```

---

## 💻 Ejecución Local (Windows / Linux sin Docker)

1. **Crear y activar un entorno virtual:**
   ```bash
   python -m venv venv
   # En Windows:
   .\venv\Scripts\activate
   # En Linux / Mac:
   source venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Iniciar el servicio telefónico:**
   ```bash
   python -u sip_telephony_service.py
   ```

---

## 🧠 Base de Datos de Grafos (PostgreSQL + Apache AGE) y KAG

El sistema incorpora una capa de grafos de conocimiento con **Apache AGE** (A Graph Extension for PostgreSQL) y **KAG (Knowledge-Augmented Generation)**:

1. **Grafo de Conocimiento (openCypher):**
   - Modela la ontología completa del restaurante: `(:Dish)`, `(:Category)`, `(:Zone)`, `(:Customer)`, `(:Alias)`.
   - Consulta y enlaza relaciones: `(:Dish)-[:BELONGS_TO]->(:Category)` y `(:Dish)-[:HAS_ALIAS]->(:Alias)`.
2. **KAG Anti-Alucinación (Ground Truth):**
   - Anclaje factual determinista antes de la generación: inyecta precios exactos, reglas de horarios y tarifas de envío en tiempo real.
   - Guardián post-generación: audita la respuesta del LLM antes de hablar o despachar, corrigiendo automáticamente cualquier desviación de precios o inventiva aritmética.
3. **Bucle de Autoaprendizaje Continuo (Self-Learning):**
   - Aprende dinámicamente alias fonéticos y regionalismos cuando el cliente corrige al bot ("no, quise decir X").
   - Recuerda preferencias y direcciones de clientes recurrentes para agilizar el pedido.
4. **Protocol Buffers (Protobuf v3):**
   - Esquemas estrictos en `proto/` (`ryu_order.proto`, `ryu_telephony.proto`, `ryu_kag.proto`).
   - Serialización binaria ultra compacta (~300-450 bytes) almacenada en columnas `BYTEA` de PostgreSQL y transferida entre servicios con latencia cero.

Para compilar esquemas proto:
```bash
python -m grpc_tools.protoc -Iproto --python_out=proto proto/ryu_order.proto proto/ryu_telephony.proto proto/ryu_kag.proto
```

Para correr las pruebas automatizadas del pipeline KAG y Protobuf:
```bash
python test_kag_pipeline.py
```

---


Para subir este proyecto a tu cuenta de GitHub:

1. **Crea un repositorio vacío en GitHub** (por ejemplo, con el nombre `ryu-ai-telephony`).
2. **Vincula tu repositorio local y sube los cambios:**
   ```bash
   git remote add origin https://github.com/<TU_USUARIO>/ryu-ai-telephony.git
   git branch -M main
   git push -u origin main
   ```

> [!NOTE]
> Las credenciales reales en tu archivo `.env` y las grabaciones dinámicas de audio están estrictamente ignoradas en `.gitignore`, por lo que puedes compartir tu código con total tranquilidad.

---

## 📜 Licencia y Contacto
Desarrollado para **Restaurante Ryu** — Paseo del Centenario 27, Colonia Cofradía, Tequila, Jalisco.
Teléfono SIP: **+52 33 8526 1250**.
