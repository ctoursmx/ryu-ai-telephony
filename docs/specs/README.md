# 📐 Especificaciones de Arquitectura y Contratos Técnicos (Open Spec)

Bienvenido al repositorio formal de especificaciones y contratos de interfaz del conmutador con Inteligencia Artificial y panel operativo de **Restaurante Ryu** y **Capri Cucina Italiana** (Tequila, Jalisco).

---

## 📑 Índice de Especificaciones

| Archivo | Formato / Estándar | Propósito | Enlace Directo |
| :--- | :--- | :--- | :--- |
| **`openapi.yaml`** | OpenAPI 3.1.0 (YAML) | Especificación exhaustiva de todas las rutas REST, autenticación HMAC, parámetros y esquemas Pydantic. | [openapi.yaml](file:///c:/Users/HP/Desktop/Ryu/docs/specs/openapi.yaml) |
| **`openapi.json`** | OpenAPI 3.1.0 (JSON) | Especificación compilada para clientes automatizados, Postman, Swagger UI y validadores de esquema. | [openapi.json](file:///c:/Users/HP/Desktop/Ryu/docs/specs/openapi.json) |
| **`telephony-spec.yaml`** | Open Spec / VoIP | Protocolo SIP v2.0 Zadarma, configuración simétrica RTP, codec G.711 A-law 8kHz, umbrales de VAD y máquina de estados de llamada. | [telephony-spec.yaml](file:///c:/Users/HP/Desktop/Ryu/docs/specs/telephony-spec.yaml) |
| **`order-contract-spec.yaml`** | Open Spec / Data Contract | Esquema JSON Schema/YAML de la comanda de restaurante, invariantes de negocio, auditoría aritmética y contrato de Soft Restaurant POS. | [order-contract-spec.yaml](file:///c:/Users/HP/Desktop/Ryu/docs/specs/order-contract-spec.yaml) |

---

## 🌐 Exploración Interactiva en Vivo

Cuando el servidor está en ejecución (`python server_telephony_ryu.py` o servicio Docker en producción):

- **Swagger UI**: [`http://localhost:8000/docs`](http://localhost:8000/docs) (o en producción `http://89.167.43.130:8000/docs`)
- **ReDoc UI**: [`http://localhost:8000/redoc`](http://localhost:8000/redoc)
- **OpenAPI YAML en vivo**: [`http://localhost:8000/api/openapi.yaml`](http://localhost:8000/api/openapi.yaml)
- **OpenAPI JSON en vivo**: [`http://localhost:8000/openapi.json`](http://localhost:8000/openapi.json)

---

## 🔄 Cómo Regenerar y Sincronizar las Especificaciones

El archivo `tools/export_openapi.py` extrae automáticamente la especificación OpenAPI de la aplicación FastAPI en vivo, garantizando que el código fuente y la documentación se mantengan sincronizados:

```bash
# Desde la raíz del repositorio
python tools/export_openapi.py
```

### Comprobación Automatizada de Integridad:
```bash
# Ejecutar la suite de pruebas unitarias de contratos y especificaciones
python -m unittest test_specs.py
```

---

## 🔗 Relación con los ADR (Architecture Decision Records)
Cada decisión técnica que respalda estas especificaciones está formalmente fundamentada en el directorio [`docs/adr/`](file:///c:/Users/HP/Desktop/Ryu/docs/adr/README.md):
- **ADR-0001**: Telefonía SIP/RTP vía Zadarma y pyVoIP
- **ADR-0002**: Pipeline de Audio G.711 A-law 8kHz y soxr HQ
- **ADR-0003**: Transcripción local con faster-whisper int8
- **ADR-0004**: Orquestación conversacional con GPT-4o-mini
- **ADR-0005**: Auditoría matemática determinística de pedidos
- **ADR-0006**: Estudio de Voz Web (Voice Studio) con latencia 0ms
- **ADR-0007**: Seguridad y autenticación del panel de control
- **ADR-0008**: Despliegue Docker en modo Host Networking
