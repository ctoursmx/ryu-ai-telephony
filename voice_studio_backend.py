#!/usr/bin/env python3
"""
voice_studio_backend.py
Motor de procesamiento de audio y gestión del Estudio de Grabación de Voz Ryu.
- Transcodifica grabaciones del navegador (WebM, Opus, Ogg, WAV, MP4) a G.711 A-law 8000 Hz puro.
- Normaliza a -1.4 dBFS para telefonía profesional sin distorsión ni clipping.
- Mantiene versión WAV (16kHz) para reproducción inmediata en el navegador.
- Sincroniza en tiempo real con voice_studio_manifest.json y la RAM del servicio SIP.
"""

import io
import json
import time
import wave
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

import av
import numpy as np
import soxr

from audio_codec import pcm2alaw

ROOT_DIR = Path(__file__).parent
MANIFEST_FILE = ROOT_DIR / "voice_studio_manifest.json"
AUDIO_DIR = ROOT_DIR / "audio_clips"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def normalize_speech_rms(
    samples: np.ndarray,
    target_dbfs: float = -17.0,
    max_gain_db: float = 18.0,
    sample_rate: int = 16000
) -> np.ndarray:
    """
    Nivela el volumen del habla a un nivel RMS perceptual constante (-17.0 dBFS),
    descartando silencios ambientales por debajo de -45 dBFS (Voice Activity Gating)
    y aplicando un limitador suave analógico (tanh) para evitar saturación o 'clipping'
    en consonantes explosivas o golpes de aire.
    """
    if len(samples) == 0:
        return samples

    # Longitud de ventana para calcular energía (~50 ms)
    frame_len = max(64, int(sample_rate * 0.05))
    num_frames = len(samples) // frame_len
    if num_frames == 0:
        frames = [samples]
    else:
        frames = [samples[i * frame_len:(i + 1) * frame_len] for i in range(num_frames)]

    frame_rms = [np.sqrt(np.mean(f.astype(np.float32) ** 2) + 1e-9) for f in frames]
    frame_db = [20.0 * np.log10(r) for r in frame_rms]

    # Puerta de voz: discriminar silencios/pausas por debajo de -45 dBFS
    speech_frames = [f for f, db in zip(frames, frame_db) if db > -45.0]
    if speech_frames:
        speech_concat = np.concatenate(speech_frames).astype(np.float32)
        active_rms = np.sqrt(np.mean(speech_concat ** 2) + 1e-9)
    else:
        active_rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2) + 1e-9)

    target_rms = 10.0 ** (target_dbfs / 20.0)
    desired_gain = target_rms / max(active_rms, 1e-5)
    max_gain = 10.0 ** (max_gain_db / 20.0)
    gain = min(desired_gain, max_gain)

    scaled = samples.astype(np.float32) * gain

    # Limitador suave analógico (tanh) para picos que superen 0.85 (-1.4 dBFS)
    threshold = 0.85
    overshoot = np.abs(scaled) > threshold
    if np.any(overshoot):
        s = scaled[overshoot]
        sgn = np.sign(s)
        abs_s = np.abs(s)
        limited = sgn * (threshold + (1.0 - threshold) * np.tanh((abs_s - threshold) / (1.0 - threshold))) * 0.95
        scaled[overshoot] = limited

    return np.clip(scaled, -0.99, 0.99)


def transcode_browser_audio(
    raw_audio_bytes: bytes,
    start_sec: Optional[float] = None,
    end_sec: Optional[float] = None
) -> Tuple[bytes, bytes, float]:
    """
    Decodifica el audio enviado por el navegador web (WebM, Opus, MP4, WAV, OGG)
    usando PyAV / FFmpeg interno, permite recorte opcional de inicio/fin, y genera:
    1. alaw_bytes: Audio G.711 A-law 8000 Hz mono (estándar Zadarma VoIP).
    2. wav_bytes: Audio WAV 16000 Hz mono PCM (reproductor web de alta fidelidad).
    3. duration_sec: Duración exacta en segundos.
    """
    if not raw_audio_bytes or len(raw_audio_bytes) < 100:
        raise ValueError("El archivo de audio recibido está vacío o es demasiado pequeño.")

    container = av.open(io.BytesIO(raw_audio_bytes))
    audio_stream = next((s for s in container.streams if s.type == "audio"), None)
    if not audio_stream:
        raise ValueError("No se detectó una pista de audio válida en el archivo.")

    resampler_8k = av.AudioResampler(format="s16", layout="mono", rate=8000)
    resampler_16k = av.AudioResampler(format="s16", layout="mono", rate=16000)

    pcm8_parts = []
    pcm16_parts = []

    for packet in container.demux(audio_stream):
        for frame in packet.decode():
            for rf in resampler_8k.resample(frame):
                pcm8_parts.append(rf.to_ndarray().tobytes())
            for rf in resampler_16k.resample(frame):
                pcm16_parts.append(rf.to_ndarray().tobytes())

    # Flush resamplers
    for rf in resampler_8k.resample(None):
        pcm8_parts.append(rf.to_ndarray().tobytes())
    for rf in resampler_16k.resample(None):
        pcm16_parts.append(rf.to_ndarray().tobytes())

    pcm8_raw = b"".join(pcm8_parts)
    pcm16_raw = b"".join(pcm16_parts)

    if not pcm8_raw:
        raise ValueError("No se pudieron extraer muestras de audio de la grabación.")

    # Aplicar recorte de inicio/fin si fue especificado (ej. quitar clic del ratón al final)
    total_sec = (len(pcm8_raw) // 2) / 8000.0
    if start_sec is not None or end_sec is not None:
        s_sec = max(0.0, float(start_sec)) if start_sec is not None else 0.0
        e_sec = min(total_sec, float(end_sec)) if end_sec is not None else total_sec
        if e_sec <= s_sec:
            raise ValueError(f"El tiempo final ({e_sec:.2f}s) debe ser mayor que el inicial ({s_sec:.2f}s).")

        if s_sec > 0.0 or e_sec < total_sec:
            s_idx8 = int(s_sec * 8000) * 2
            e_idx8 = int(e_sec * 8000) * 2
            pcm8_raw = pcm8_raw[s_idx8:e_idx8]

            s_idx16 = int(s_sec * 16000) * 2
            e_idx16 = int(e_sec * 16000) * 2
            pcm16_raw = pcm16_raw[s_idx16:e_idx16]

    if not pcm8_raw:
        raise ValueError("El rango de recorte seleccionado no contiene muestras de audio.")

    # 1. Nivelación perceptual RMS del audio a 16kHz para el navegador y alta fidelidad (-17 dBFS)
    s16_arr = np.frombuffer(pcm16_raw, dtype=np.int16).astype(np.float32) / 32768.0
    s16_norm = normalize_speech_rms(s16_arr, target_dbfs=-17.0, sample_rate=16000)
    s16_int16 = np.clip(s16_norm * 32767.0, -32768, 32767).astype(np.int16)

    # Generar WAV 16kHz nivelado para el navegador
    wav_out_io = io.BytesIO()
    with wave.open(wav_out_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(s16_int16.tobytes())
    wav_bytes = wav_out_io.getvalue()

    # 2. Resamplear a 8000 Hz HQ y generar versión telefónica G.711 A-law (-17 dBFS)
    s8_float = soxr.resample(s16_norm, 16000, 8000, quality="HQ")
    s8_norm = normalize_speech_rms(s8_float, target_dbfs=-17.0, sample_rate=8000)
    s8_int16 = np.clip(s8_norm * 32767.0, -32768, 32767).astype(np.int16)
    alaw_bytes = pcm2alaw(s8_int16.tobytes())

    duration_sec = round(len(alaw_bytes) / 8000.0, 2)
    return alaw_bytes, wav_bytes, duration_sec


def get_manifest_data() -> dict:
    """Retorna el manifiesto actualizado con estadísticas en vivo."""
    if not MANIFEST_FILE.exists():
        import generate_voice_manifest
        return generate_voice_manifest.build_manifest()

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Actualizar estado de archivos físicos
    items = manifest.get("items", [])
    recorded_count = 0
    for it in items:
        i_id = it["id"]
        alaw_path = AUDIO_DIR / f"{i_id}.alaw"
        has_audio = alaw_path.exists() and alaw_path.stat().st_size > 0
        if has_audio:
            it["status"] = "recorded"
            it["audio_alaw"] = f"/audio_clips/{i_id}.alaw"
            it["audio_wav"] = f"/api/voice-studio/audio/{i_id}"
            if it.get("duration_sec", 0.0) == 0.0:
                it["duration_sec"] = round(alaw_path.stat().st_size / 8000.0, 2)
            recorded_count += 1
        else:
            it["status"] = "pending"
            it["audio_alaw"] = None
            it["audio_wav"] = None

    manifest["recorded_items"] = recorded_count
    manifest["pending_items"] = len(items) - recorded_count
    manifest["completion_percent"] = round((recorded_count / len(items)) * 100, 1) if items else 0.0

    return manifest


def save_item_recording(
    item_id: str,
    raw_audio: bytes,
    start_sec: Optional[float] = None,
    end_sec: Optional[float] = None
) -> dict:
    """Procesa, guarda, opcionalmente recorta y sincroniza la grabación de un ítem."""
    item_id = str(item_id).strip()
    if not item_id:
        raise ValueError("ID de ítem no válido.")

    alaw_bytes, wav_bytes, duration_sec = transcode_browser_audio(
        raw_audio,
        start_sec=start_sec,
        end_sec=end_sec
    )

    alaw_path = AUDIO_DIR / f"{item_id}.alaw"
    wav_path = AUDIO_DIR / f"{item_id}.wav"

    alaw_path.write_bytes(alaw_bytes)
    wav_path.write_bytes(wav_bytes)

    # Actualizar manifiesto
    manifest = get_manifest_data()
    updated_item = None
    for it in manifest.get("items", []):
        if it["id"] == item_id:
            it["status"] = "recorded"
            it["duration_sec"] = duration_sec
            it["audio_alaw"] = f"/audio_clips/{item_id}.alaw"
            it["audio_wav"] = f"/api/voice-studio/audio/{item_id}"
            it["updated_at"] = datetime.now().isoformat()
            updated_item = it
            break

    if updated_item:
        manifest["recorded_items"] = sum(1 for x in manifest["items"] if x["status"] == "recorded")
        manifest["pending_items"] = len(manifest["items"]) - manifest["recorded_items"]
        manifest["completion_percent"] = round((manifest["recorded_items"] / len(manifest["items"])) * 100, 1)
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Actualizar la memoria RAM telefónica en vivo
    try:
        import sip_telephony_service
        if hasattr(sip_telephony_service, "load_voice_studio_clips"):
            sip_telephony_service.load_voice_studio_clips()
    except Exception as e:
        print(f"Aviso actualizando RAM de telefonía: {e}")

    return {
        "status": "ok",
        "item_id": item_id,
        "duration_sec": duration_sec,
        "item": updated_item
    }


def trim_item_recording(item_id: str, start_sec: float, end_sec: float) -> dict:
    """
    Recorta un archivo de audio ya grabado (WAV 16kHz y G.711 A-law 8kHz),
    eliminando el sonido del clic del ratón al final o silencios al inicio.
    """
    item_id = str(item_id).strip()
    wav_path = AUDIO_DIR / f"{item_id}.wav"
    alaw_path = AUDIO_DIR / f"{item_id}.alaw"

    if not wav_path.exists():
        raise FileNotFoundError(f"No existe el archivo de audio para el ítem '{item_id}'.")

    with wave.open(str(wav_path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        total_duration = nframes / framerate

        s_sec = max(0.0, float(start_sec))
        e_sec = min(total_duration, float(end_sec))
        if e_sec <= s_sec:
            raise ValueError(f"El tiempo final ({e_sec:.2f}s) debe ser mayor que el inicial ({s_sec:.2f}s).")

        start_frame = int(s_sec * framerate)
        end_frame = int(e_sec * framerate)

        wf.setpos(start_frame)
        frames_to_read = end_frame - start_frame
        trimmed_pcm16 = wf.readframes(frames_to_read)

    if not trimmed_pcm16:
        raise ValueError("El rango de recorte no produjo muestras de audio válidas.")

    # Guardar nuevo archivo WAV 16kHz recortado y nivelado (-17 dBFS)
    s16_arr = np.frombuffer(trimmed_pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    s16_norm = normalize_speech_rms(s16_arr, target_dbfs=-17.0, sample_rate=framerate)
    s16_int16 = np.clip(s16_norm * 32767.0, -32768, 32767).astype(np.int16)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(s16_int16.tobytes())

    # Generar y normalizar versión telefónica G.711 A-law a 8000Hz (-17 dBFS)
    s8_float = soxr.resample(s16_norm, framerate, 8000, quality="HQ")
    s8_norm = normalize_speech_rms(s8_float, target_dbfs=-17.0, sample_rate=8000)
    s8_int16 = np.clip(s8_norm * 32767.0, -32768, 32767).astype(np.int16)
    alaw_bytes = pcm2alaw(s8_int16.tobytes())
    alaw_path.write_bytes(alaw_bytes)

    new_duration_sec = round(len(alaw_bytes) / 8000.0, 2)

    # Actualizar manifiesto
    manifest = get_manifest_data()
    updated_item = None
    for it in manifest.get("items", []):
        if it["id"] == item_id:
            it["duration_sec"] = new_duration_sec
            it["updated_at"] = datetime.now().isoformat()
            updated_item = it
            break

    if updated_item:
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Sincronizar en memoria RAM con el servicio SIP de telefonía
    try:
        import sip_telephony_service
        if hasattr(sip_telephony_service, "load_voice_studio_clips"):
            sip_telephony_service.load_voice_studio_clips()
    except Exception as e:
        print(f"Aviso actualizando RAM de telefonía tras recortar: {e}")

    return {
        "status": "ok",
        "item_id": item_id,
        "duration_sec": new_duration_sec,
        "item": updated_item
    }


def delete_item_recording(item_id: str) -> dict:
    """Elimina la grabación física de un ítem y lo restablece a pendiente."""
    item_id = str(item_id).strip()
    alaw_path = AUDIO_DIR / f"{item_id}.alaw"
    wav_path = AUDIO_DIR / f"{item_id}.wav"

    if alaw_path.exists():
        alaw_path.unlink()
    if wav_path.exists():
        wav_path.unlink()

    manifest = get_manifest_data()
    for it in manifest.get("items", []):
        if it["id"] == item_id:
            it["status"] = "pending"
            it["duration_sec"] = 0.0
            it["audio_alaw"] = None
            it["audio_wav"] = None
            it["updated_at"] = datetime.now().isoformat()
            break

    manifest["recorded_items"] = sum(1 for x in manifest["items"] if x["status"] == "recorded")
    manifest["pending_items"] = len(manifest["items"]) - manifest["recorded_items"]
    manifest["completion_percent"] = round((manifest["recorded_items"] / len(manifest["items"])) * 100, 1)

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    try:
        import sip_telephony_service
        if hasattr(sip_telephony_service, "load_voice_studio_clips"):
            sip_telephony_service.load_voice_studio_clips()
    except Exception as e:
        print(f"Aviso actualizando RAM de telefonía tras eliminar: {e}")

    return {"status": "ok", "deleted_item_id": item_id}


def concatenate_clips_wav(item_ids: list[str]) -> bytes:
    """Concatena múltiples clips grabados con 150ms de silencio para simulación web."""
    silence_pcm = b"\x00" * int(16000 * 2 * 0.15) # 150ms a 16kHz s16le mono
    all_frames = []

    for idx, i_id in enumerate(item_ids):
        w_path = AUDIO_DIR / f"{i_id}.wav"
        if w_path.exists():
            with wave.open(str(w_path), "rb") as wf:
                all_frames.append(wf.readframes(wf.getnframes()))
                if idx < len(item_ids) - 1:
                    all_frames.append(silence_pcm)

    if not all_frames:
        raise ValueError("Ninguno de los clips seleccionados tiene audio grabado.")

    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as out_wf:
        out_wf.setnchannels(1)
        out_wf.setsampwidth(2)
        out_wf.setframerate(16000)
        out_wf.writeframes(b"".join(all_frames))

    return out_io.getvalue()


def batch_normalize_all_recordings(target_dbfs: float = -17.0) -> dict:
    """
    Nivela retrospectivamente todas las grabaciones existentes en audio_clips/
    al estándar internacional de telefonía VoIP (-17.0 dBFS RMS), actualizando
    tanto los archivos WAV de alta fidelidad como los G.711 A-law telefónicos,
    y sincronizando la memoria RAM del conmutador en tiempo real.
    """
    manifest = get_manifest_data()
    items_by_id = {it["id"]: it for it in manifest.get("items", [])}
    normalized_count = 0
    errors = []

    for wav_path in sorted(AUDIO_DIR.glob("*.wav")):
        item_id = wav_path.stem
        alaw_path = AUDIO_DIR / f"{item_id}.alaw"

        try:
            with wave.open(str(wav_path), "rb") as wf:
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                raw_pcm = wf.readframes(nframes)

            if not raw_pcm:
                continue

            s_arr = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
            s_norm = normalize_speech_rms(s_arr, target_dbfs=target_dbfs, sample_rate=framerate)
            s_int16 = np.clip(s_norm * 32767.0, -32768, 32767).astype(np.int16)

            # Re-escribir WAV 16kHz nivelado
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(nchannels)
                wf.setsampwidth(sampwidth)
                wf.setframerate(framerate)
                wf.writeframes(s_int16.tobytes())

            # Resamplear y re-escribir G.711 A-law 8000Hz nivelado
            s8_float = soxr.resample(s_norm, framerate, 8000, quality="HQ")
            s8_norm = normalize_speech_rms(s8_float, target_dbfs=target_dbfs, sample_rate=8000)
            s8_int16 = np.clip(s8_norm * 32767.0, -32768, 32767).astype(np.int16)
            alaw_bytes = pcm2alaw(s8_int16.tobytes())
            alaw_path.write_bytes(alaw_bytes)

            new_duration_sec = round(len(alaw_bytes) / 8000.0, 2)
            if item_id in items_by_id:
                it = items_by_id[item_id]
                it["duration_sec"] = new_duration_sec
                it["status"] = "recorded"
                it["audio_alaw"] = f"/audio_clips/{item_id}.alaw"
                it["audio_wav"] = f"/api/voice-studio/audio/{item_id}"
                it["updated_at"] = datetime.now().isoformat()
            normalized_count += 1
        except Exception as e:
            errors.append(f"{item_id}: {str(e)}")

    if normalized_count > 0:
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        try:
            import sip_telephony_service
            if hasattr(sip_telephony_service, "load_voice_studio_clips"):
                sip_telephony_service.load_voice_studio_clips()
        except Exception as e:
            print(f"Aviso actualizando RAM SIP tras nivelación masiva: {e}")

    return {
        "status": "ok",
        "normalized_count": normalized_count,
        "target_dbfs": target_dbfs,
        "errors": errors
    }

