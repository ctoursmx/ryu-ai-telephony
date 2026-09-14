# ADR-0007: Autenticación Híbrida Blindada (HMAC Tokens + Rate Limiting) para /admin

* **Estado**: `Aceptada`
* **Fecha**: 2026-09-11
* **Decisores**: Seguridad y Backend Ryu
* **Contexto Técnico**: `server_telephony_ryu.py`, `templates/admin_dashboard.html`

---

## 1. Contexto y Planteamiento del Problema

El panel administrativo web (`/admin`) permite modificar en caliente variables operacionales críticas:
* Abrir o cerrar la recepción de pedidos en cocina.
* Modificar precios de platillos y horarios de servicio.
* Marcar ingredientes como agotados (afectando la venta de rollos o pizzas).
* Subir grabaciones de voz y borrar audios existentes.

Dado que el servidor corre expuesto a internet en una dirección IP pública (VPS `89.167.43.130:8000`), es imprescindible prevenir accesos no autorizados, ataques de fuerza bruta o robo de sesiones.

---

## 2. Factores Clave de Decisión

* **Protección contra ataques de fuerza bruta por diccionario en el login**.
* **Autenticación stateless sin base de datos de sesiones pesada**.
* **Compatibilidad dual**: Funcionar con cookies seguras para navegadores y con cabeceras `Authorization: Bearer <token>` para clientes móviles y APIs.
* **Sesiones prolongadas para comodidad del operador del restaurante (30 días)** sin comprometer la seguridad criptográfica.

---

## 3. Opciones Consideradas

### Opción A: Autenticación con Base de Datos Relacional (OAuth2 / Django / Auth0)
* **Ventajas**: Gestión estándar de usuarios y roles.
* **Desventajas**: Sobrecarga de dependencias externas para un panel operado por el dueño y administradores autorizados.

### Opción B: Tokens Firmados Criptográficamente con HMAC-SHA256 y Rate Limiting en Memoria (Elegida)
* **Ventajas**:
  - Implementación ligera y de alto rendimiento en FastAPI (`verify_admin_auth`).
  - Tokens con firma criptográfica: `username:expiration:hmac_signature`.
  - Rate limiting estricto: Bloqueo temporal por 10 minutos al acumular 5 intentos fallidos consecutivos por IP.
  - Verificación en tiempo constante con `secrets.compare_digest()` para prevenir ataques de temporización (timing attacks).
* **Desventajas**: Requiere proteger la clave secreta `ADMIN_SECRET_KEY` en el archivo `.env`.

---

## 4. Decisión Adoptada

Se adoptó la **Opción B**:
1. **Endpoint `/api/auth/login`**: Valida credenciales contra `ADMIN_USERNAME` y `ADMIN_PASSWORD` mediante comparación de tiempo constante.
2. **Generación de Token HMAC**: Genera un token firmado válido por 30 días, entregado tanto en JSON como en cookie `admin_token`.
3. **Soporte Dual en `verify_admin_auth()`**:
   - Cabecera `Authorization: Bearer <token>`
   - Cabecera `X-Admin-Token: <token>`
   - Cookie `admin_token`
4. **Protección Anti-Fuerza Bruta**: El diccionario `login_failed_attempts` monitorea los timestamps de intentos por IP cliente y bloquea con código HTTP 429 tras 5 fallos.

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Blindaje seguro del panel administrativo en IP pública sin bases de datos adicionales.
* Experiencia fluida para el dueño en su celular (no necesita iniciar sesión cada 10 minutos).

---

## 6. Cumplimiento y Verificación

* Pruebas de autenticación exitosa (200) y rechazo no autorizado (401/429) validadas en `test_vps_voice_studio.py`.
