# ADR-0003: Motor de Transcripción Local faster-whisper int8 con Acoustic Priming

* **Estado**: `Aceptada`
* **Fecha**: 2026-03-05
* **Decisores**: Equipo de Inteligencia Artificial y STT Ryu
* **Contexto Técnico**: `sip_telephony_service.py` / `voice_engine_ryu.py`

---

## 1. Contexto y Planteamiento del Problema

Para atender 1,700 llamadas por semana (aproximadamente 10,000 a 15,000 turnos conversacionales por mes), el sistema requiere transcribir con precisión la voz de clientes de Tequila y zonas aledañas (con ruidos de fondo, acentos locales y jerga gastronómica mexicana como "boneless", "yakimeshi", "kushiage", "teppanyaki", "medineño", "cofradía").

El uso de APIs de transcripción en la nube (como OpenAI Whisper API o Google Speech-to-Text):
1. Añade entre 800 ms y 1,500 ms de latencia por la subida de audio vía HTTPS.
2. Implica un costo de $0.006 USD por minuto, sumando más de **$120 - $200 USD mensuales** solo en STT.
3. Depende de la estabilidad de la conexión transfronteriza hacia los servidores de EE.UU.

---

## 2. Factores Clave de Decisión

* **Latencia de transcripción inferior a 1.2 segundos** en hardware de servidor VPS sin GPU.
* **Cero costo por llamada** ($0.00 USD).
* **Precisión fonética para platillos japoneses y colonias de Tequila**.
* **Precalentamiento en memoria RAM** para evitar demoras en la primera llamada entrante.

---

## 3. Opciones Consideradas

### Opción A: OpenAI Whisper API Cloud (`whisper-1`)
* **Ventajas**: Alta precisión general.
* **Desventajas**: Latencia de red de 1 a 2 segundos por turno, costo recurrente por minuto.

### Opción B: Whisper Original en PyTorch (`openai/whisper`)
* **Ventajas**: Código fuente abierto.
* **Desventajas**: Muy lento en CPU (3 a 5 segundos por frase), alto consumo de memoria RAM (> 1.5 GB).

### Opción C: `faster-whisper` (CTranslate2) con Cuantización `int8` (Elegida)
* **Ventajas**:
  - Motor de inferencia en C++ altamente optimizado para instrucciones AVX2 / AVX-512 de procesadores x86.
  - La cuantización `int8` reduce el uso de memoria a ~150 MB (modelo `base`).
  - Velocidad de procesamiento 4x superior a PyTorch en CPU pura.
  - Soporte de **Acoustic Priming** mediante `initial_prompt` para guiar al decodificador hacia el vocabulario de Ryu.
* **Desventajas**: Requiere modelo pre-descargado en disco local.

---

## 4. Decisión Adoptada

Se implementó **`faster-whisper` modelo `base` con cómputo `int8`** corriendo localmente en el servidor, con las siguientes optimizaciones:
1. **Precalentamiento en arranque**: Se ejecuta una transcripción sintética de 0.5s al iniciar el servicio para asegurar que el modelo y los hilos CTranslate2 residan en memoria listos para atender llamadas.
2. **Remuestreo de Entrada 8k a 16k**: Whisper requiere audio a 16,000 Hz; se realiza una interpolación lineal de alta velocidad de 8 kHz a 16 kHz en memoria.
3. **Acoustic Priming Dinámico**: Se alimenta a Whisper un prompt de inicialización con los términos más comunes del restaurante:
   ```text
   Restaurante Ryu en Tequila, Jalisco. Especialidades: Sushi, Teriyaki, Yakimeshi,
   Kushiage, Boneless, Alitas, Hamburguesas, Paninis. Zonas: Cofradía, Centro, El Medineño, Tierra de Agave.
   ```

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Transcripción en **~0.6 a 1.1 segundos** en CPU estándar de 2-4 núcleos.
* Costo recurrente de transcripción: **$0.00 USD** sin importar si se reciben 1,000 o 10,000 llamadas al mes.
* Resiliencia total ante caídas de proveedores externos de STT.

---

## 6. Cumplimiento y Verificación

* Logs de inicialización: `faster-whisper listo y precalentado en 0.82s`.
* Pruebas de transcripción validadas en `test_enhanced_flow.py`.
