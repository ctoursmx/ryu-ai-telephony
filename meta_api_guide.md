# Guía Paso a Paso: Configuración de Meta WhatsApp Cloud API Oficial para Ryu

Usar la **API oficial de WhatsApp Cloud de Meta** es la mejor decisión para un negocio, ya que:
- **0% de riesgo de baneo:** La conexión es 100% autorizada por Meta.
- **1,000 conversaciones de servicio gratuitas cada mes:** Cuando el cliente inicia la conversación, no tiene costo durante la ventana de 24 horas.
- **Alta velocidad y estabilidad:** No depende de un celular conectado a internet o emuladores.

---

## 1. Crear la Aplicación en Meta for Developers

1. Entra a [developers.facebook.com](https://developers.facebook.com/) e inicia sesión con tu cuenta de Facebook.
2. Ve a **Mis Apps** -> **Crear App**.
3. Selecciona el tipo de app: **Otro** -> **Negocio (Business)**.
4. Asigna un nombre a la app (ej. `Ryu Tequila Bot`) y selecciona tu cuenta de Administrador Comercial (Business Manager).
5. En el panel de la app, busca el producto **WhatsApp** y da clic en **Configurar (Set up)**.

---

## 2. Obtener las Claves de Conexión

En el menú lateral de WhatsApp -> **Inicio rápido / Primeros pasos**:

1. **Identificador de número de teléfono (Phone Number ID):**
   * Es un número largo (ej. `102938475610293`). Cópialo.
2. **Identificador de la cuenta de WhatsApp Business (WABA ID):**
   * Cópialo para tus registros.
3. **Número de prueba o Número real del restaurante:**
   * Puedes iniciar pruebas con el número de prueba de Meta o agregar el número de teléfono del restaurante Ryu en la sección **Configuración del teléfono**.

---

## 3. Generar un Token Permanente (System User Token)

El token temporal de la pantalla principal expira en 24 horas. Para producción necesitas un Token permanente:

1. Ve a tu [Business Manager de Meta](https://business.facebook.com/settings/).
2. En el menú izquierdo, ve a **Usuarios** -> **Usuarios del sistema (System Users)**.
3. Haz clic en **Agregar**, nombra al usuario (ej. `n8n-ryubot`) y asígnale el rol de **Administrador**.
4. Haz clic en **Asignar activos (Assign Assets)**:
   * Selecciona **Apps** -> Elige tu app `Ryu Tequila Bot` -> Activa control total.
   * Selecciona **Cuentas de WhatsApp** -> Elige tu WABA de Ryu -> Activa control total.
5. Haz clic en **Generar nuevo token (Generate New Token)**:
   * Selecciona la app.
   * Caducidad del token: **Nunca (Never)**.
   * Permisos requeridos:
     - `whatsapp_business_messaging`
     - `whatsapp_business_management`
6. Copia y guarda este Token en un lugar seguro.

---

## 4. Configurar el Webhook en n8n

1. En n8n, importa el archivo [n8n_meta_whatsapp_workflow.json](file:///c:/Users/HP/Desktop/Ryu/n8n_meta_whatsapp_workflow.json).
2. Activa el flujo para que los Webhooks queden escuchando en modo producción.
3. En el panel de Meta Developer -> **WhatsApp** -> **Configuración**:
   * En **URL de devolución de llamada (Callback URL)**: Pega la URL de producción de n8n:
     ```
     https://tu-instancia-n8n.com/webhook/meta-whatsapp-webhook
     ```
   * En **Token de verificación (Verify Token)**: Escribe una palabra clave secreta (ej. `RyuTequilaSecureToken2026`).
   * Haz clic en **Verificar y guardar**.
4. En **Campos de webhook (Webhook Fields)**, haz clic en **Administrar** y suscríbete a:
   * `messages` (Obligatorio para recibir los mensajes entrantes).

---

## 5. Variables de Entorno en n8n

En tus credenciales o variables de n8n, define:
* `META_WHATSAPP_TOKEN`: El token permanente generado en el paso 3.
* `OPENAI_API_KEY`: Tu API Key para el modelo de lenguaje de toma de pedidos.
* `TELEGRAM_BOT_TOKEN`: Token de tu bot de Telegram.
* `TELEGRAM_CHAT_ID`: ID del grupo de comandas de Ryu.
