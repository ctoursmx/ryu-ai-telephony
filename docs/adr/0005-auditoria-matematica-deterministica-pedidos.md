# ADR-0005: Auditoría Matemática Determinística en Python para Cálculo de Cuentas

* **Estado**: `Aceptada`
* **Fecha**: 2026-03-09
* **Decisores**: Arquitectura de Negocio y Finanzas Ryu
* **Contexto Técnico**: `voice_engine_ryu.py`, `order_service.py`, `menu_ryu.json`

---

## 1. Contexto y Planteamiento del Problema

Los Modelos de Lenguaje Grande (LLMs) son probabilísticos y propensos a **alucinaciones aritméticas** (e.g. sumar mal 2 rollos de $165 y un refresco de $35, o inventar tarifas de envío no oficiales).

En una operación restaurantera con 1,700 llamadas a la semana:
* Cobrar de menos causa pérdidas financieras acumulativas a la cocina.
* Cobrar de más genera reclamos y pérdida de confianza de los clientes en Tequila.

---

## 2. Factores Clave de Decisión

* **Precisión matemática absoluta (100% determinística)** en los totales de cada pedido.
* **Separación estricta de responsabilidades**: El LLM se encarga de la interacción lingüística; el código Python se encarga de los números, sumas y tarifas.
* **Tarificación exacta de zonas de entrega**: Aplicar costo $0 de día y $15 de noche en zona urbana Tequila; tarifas foráneas fijas ($30, $50, $80, $100) para El Medineño, San Martín de Cañas, Magdalena, Tierra de Agave, etc.

---

## 3. Opciones Consideradas

### Opción A: Dejar que el LLM sume y cotice el total
* **Ventajas**: Fácil de implementar en el prompt ("Calcula la suma de los platillos").
* **Desventajas**: Tasa de error inaceptable (5% a 15% de sumas erróneas o descuentos mal aplicados).

### Opción B: Function Calling / Herramientas de OpenAI en cada turno
* **Ventajas**: Invoca funciones de Python.
* **Desventajas**: Incrementa la latencia telefónica en 400-800 ms por cada turno debido a los múltiples viajes de ida y vuelta a la API.

### Opción C: Auditor Matemático Determinístico Post-Extracción (Elegida)
* **Ventajas**:
  - El LLM extrae los platillos identificados en formato estructurado (o etiquetas).
  - Un módulo determinístico en Python busca los precios oficiales en `menu_ryu.json`, valida ingredientes extras y suma las tarifas según la zona detectada por regex/alias.
  - La cuenta final se valida y se inyecta al cliente de forma garantizada.
* **Desventajas**: Requiere mantener sincronizada la lista de platillos y precios en `menu_ryu.json` y `restaurant_state.json`.

---

## 4. Decisión Adoptada

Se adoptó la **Opción C**:
1. Todo cálculo financiero se realiza mediante funciones determinísticas en Python:
   ```text
   Subtotal = Suma(Precio Oficial del Platillo * Cantidad) + Extras
   Costo de Envío = Tarifa de Zona (o Regla Tequila Día/Noche)
   Total = Subtotal + Costo de Envío
   ```
2. Si el cliente o el LLM mencionan un precio discordante, el motor de auditoría sobrescribe el valor con el cálculo canónico de la base de datos oficial.
3. El ticket impreso y la comanda enviada a Telegram siempre reflejan la suma matemáticamente auditada.

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Cero diferencias de centavos en la caja del restaurante.
* Tarificación automática de zonas foráneas sin depender de que el comensal recuerde la tarifa.

---

## 6. Cumplimiento y Verificación

* Pruebas unitarias en `test_delivery_questions.py` y `test_delivery_phonetics.py`.
