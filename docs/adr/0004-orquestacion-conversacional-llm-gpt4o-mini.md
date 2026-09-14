# ADR-0004: Orquestación Conversacional con GPT-4o-mini y Normalización Fonética

* **Estado**: `Aceptada`
* **Fecha**: 2026-03-07
* **Decisores**: Arquitectura de Lenguaje Natural Ryu
* **Contexto Técnico**: `voice_engine_ryu.py`, `prompt_voice_telephone_ryu.md`, `menu_ryu.json`

---

## 1. Contexto y Planteamiento del Problema

El restaurante Ryu maneja un catálogo de más de 176 platillos repartidos en 3 conceptos gastronómicos distintos (Comida Japonesa Ryu, Snacks y Capri Cucina Italiana), además de promociones variables (3x2, descuentos por día), reglas de entrega foránea en Tequila y control de existencias de ingredientes en tiempo real.

El modelo de lenguaje debe:
1. Responder con naturalidad mexicana ("buenas tardes", "con gusto", "a tus órdenes") sin sonar acartonado o robótico.
2. No exceder 2 a 3 oraciones por turno para evitar aburrir al cliente en el teléfono.
3. Generar respuestas en menos de **800 milisegundos**.
4. Mantener un costo viable para 1,700 llamadas por semana.

---

## 2. Factores Clave de Decisión

* **Latencia de generación LLM Time-to-First-Token < 600 ms**.
* **Costo por llamada económico** (< $0.005 USD por llamada completa).
* **Comprensión contextual de intenciones** (pregunta menú, pide platillo, indica dirección, pregunta promociones, confirma orden).
* **Normalización fonética mexicana** antes de enviar el texto al motor de síntesis de voz o Voice Studio.

---

## 3. Opciones Consideradas

### Opción A: Modelos Locales en Servidor (Ollama / Llama-3-8B)
* **Ventajas**: Privacidad y cero costo por token.
* **Desventajas**: Requiere GPU dedicada costosa o CPU muy potente que colapsaría el VPS al atender múltiples llamadas simultáneas.

### Opción B: OpenAI GPT-4o (Completo)
* **Ventajas**: Máximo razonamiento.
* **Desventajas**: Costo 10 veces mayor, latencia de 1.5 a 2.5 segundos por respuesta, excesivo para diálogo telefónico de restaurante.

### Opción C: OpenAI GPT-4o-mini con Prompt Dinámico Inyectado (Elegida)
* **Ventajas**:
  - Latencia promedio de **~450 a 650 ms**.
  - Costo ultra-bajo ($0.15 por millón de tokens de entrada / $0.60 por millón de salida). Una llamada de 10 turnos cuesta menos de **$0.0025 USD**.
  - Excelente seguimiento de instrucciones estructuradas en Markdown y formato de comandas.

---

## 4. Decisión Adoptada

Se seleccionó **GPT-4o-mini** con las siguientes directrices arquitectónicas:
1. **Prompt Dinámico de Cocina**: Inyección en tiempo real de los ingredientes agotados (`unavailable_ingredients`) y promociones del día (`promotions`) antes de evaluar el turno del usuario.
2. **KAG Engine (Knowledge Augmented Generation)**: Indexación fonética de más de 400 variantes de platillos y alias para desambiguar pedidos en memoria antes de la llamada al LLM.
3. **Filtro Fonético Mexicano**: La función `clean_text_for_speech()` traduce términos fonéticamente problemáticos:
   - "Ryu" -> "Riu"
   - "3x2" -> "tres por dos"
   - "$120" -> "ciento veinte pesos"
   - "Pº del Centenario" -> "Paseo del Centenario"

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Respuestas telefónicas empáticas, fluidas y concisas.
* Consumo mensual de API de OpenAI estimado en menos de **$15 USD** para todo el volumen del restaurante.

---

## 6. Cumplimiento y Verificación

* Evaluado continuamente con `test_enhanced_flow.py` y `test_promo_followup.py`.
