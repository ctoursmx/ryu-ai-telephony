# ADR-0002: Pipeline Acústico G.711 A-law 8kHz con Remuestreo soxr HQ y Normalización

* **Estado**: `Aceptada`
* **Fecha**: 2026-03-03
* **Decisores**: Ingeniería Acústica y Telefonía Ryu
* **Contexto Técnico**: `audio_codec.py`, `sip_telephony_service.py`, `voice_studio_backend.py`

---

## 1. Contexto y Planteamiento del Problema

El estándar de telefonía fija y móvil en México (y troncales Zadarma VoIP) opera en códec **G.711 A-law (PCMA)** a una frecuencia de muestreo de **8,000 Hz** con resolución de 8 bits no lineales (compresión logarítmica).

Sin embargo:
1. Las fuentes de audio modernas (modelos TTS como Edge-TTS o navegadores web) generan audio a 24,000 Hz, 44,100 Hz o 48,000 Hz.
2. Si el remuestreo hacia 8,000 Hz se realiza con diezmado ingenuo o filtros de baja calidad, se produce **aliasing** (ruido metálico, siseo desagradable en frecuencias agudas).
3. Si el nivel de volumen no está perfectamente calibrado, la compresión A-law produce **clipping digital** (saturación audible que degrada la inteligibilidad de la voz).

---

## 2. Factores Clave de Decisión

* **Inteligibilidad acústica en bocinas de teléfonos móviles y fijos**.
* **Eliminación total del aliasing y artefactos metálicos**.
* **Eficiencia de procesamiento en tiempo real** (tiempo de conversión < 15 ms por frase).
* **Compatibilidad 100% nativa con los paquetes RTP G.711 payload type 8**.

---

## 3. Opciones Consideradas

### Opción A: Conversión con `pydub` y `scipy.signal.resample`
* **Ventajas**: Bibliotecas conocidas en Python.
* **Desventajas**: `pydub` requiere invocar procesos externos `ffmpeg`, lo que introduce 150-300 ms de latencia; `scipy` es muy pesado en memoria para un contenedor de producción.

### Opción B: Remuestreo con `soxr` HQ y codificación nativa en C/Python (Elegida)
* **Ventajas**:
  - `soxr` (SoX Resampler library) ofrece filtros sinc de ventana de Kaiser con rechazo de banda de atenuación > 95 dB.
  - Velocidad ultra-rápida implementada en extensiones C de alto rendimiento.
  - Normalización determinística de amplitud a `-1.4 dBFS` (pico 0.85 en escala lineal `[-1.0, 1.0]`).
* **Desventajas**: Requiere dependencias compiladas C/C++ en el entorno Linux.

---

## 4. Decisión Adoptada

Se adoptó un pipeline acústico estricto en tres fases:
1. **Remuestreo de Alta Fidelidad**: Conversión de 24kHz (Edge-TTS) o 16kHz/48kHz (micrófonos web) a 8,000 Hz mediante `soxr.resample(..., quality="HQ")`.
2. **Normalización Dinámica a -1.4 dBFS**:
   ```python
   peak = float(np.max(np.abs(pcm_float)))
   if peak > 1e-4:
       pcm_float = pcm_float * (0.85 / peak)
   ```
3. **Compresión G.711 A-law Directa**: Conversión de enteros signed 16-bit a bytes G.711 usando tablas de cuantización rápida en `audio_codec.py`.

---

## 5. Consecuencias y Compromisos

### Impactos Positivos
* Sonido nítido, cálido y sin distorsión metálica en cualquier teléfono celular o fijo que llame al conmutador.
* Conversión instantánea (< 5 ms en CPU) sin procesos externos.
* Coherencia sonora idéntica entre las frases sintetizadas y los clips pregrabados del Voice Studio.

---

## 6. Cumplimiento y Verificación

* Pruebas automatizadas en `test_audio_transcode.py` y `test_voice_studio_e2e.py`.
* Verificación espectral de audio PCM en 8000 Hz.
