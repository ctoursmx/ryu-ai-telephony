import io
import wave
import unittest
import numpy as np
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import voice_studio_backend

class TestAudioLeveler(unittest.TestCase):
    def setUp(self):
        self.sample_rate = 16000
        self.duration = 2.0
        self.t = np.linspace(0, self.duration, int(self.sample_rate * self.duration), endpoint=False)

    def test_leveling_quiet_and_loud_inputs_to_same_dbfs(self):
        # Audio bajo (-26 dBFS) vs audio alto (-8 dBFS)
        quiet_signal = (0.05 * np.sin(2 * np.pi * 440 * self.t)).astype(np.float32)
        loud_signal = (0.40 * np.sin(2 * np.pi * 440 * self.t)).astype(np.float32)

        norm_quiet = voice_studio_backend.normalize_speech_rms(quiet_signal, target_dbfs=-17.0, sample_rate=16000)
        norm_loud = voice_studio_backend.normalize_speech_rms(loud_signal, target_dbfs=-17.0, sample_rate=16000)

        rms_quiet_db = 20.0 * np.log10(np.sqrt(np.mean(norm_quiet**2) + 1e-9))
        rms_loud_db = 20.0 * np.log10(np.sqrt(np.mean(norm_loud**2) + 1e-9))

        self.assertAlmostEqual(rms_quiet_db, -17.0, delta=0.5)
        self.assertAlmostEqual(rms_loud_db, -17.0, delta=0.5)
        # La diferencia perceptual entre ambos debe ser prácticamente cero (<0.2 dB)
        self.assertLess(abs(rms_quiet_db - rms_loud_db), 0.2)

    def test_silence_gating(self):
        # 1 segundo de voz activa y 1 segundo de silencio total
        signal = np.zeros(int(self.sample_rate * 2.0), dtype=np.float32)
        signal[:int(self.sample_rate * 1.0)] = 0.10 * np.sin(2 * np.pi * 440 * self.t[:int(self.sample_rate * 1.0)])

        norm = voice_studio_backend.normalize_speech_rms(signal, target_dbfs=-17.0, sample_rate=16000)
        active_part = norm[:int(self.sample_rate * 1.0)]
        active_rms_db = 20.0 * np.log10(np.sqrt(np.mean(active_part**2) + 1e-9))

        # La parte activa de voz debe quedar calibrada al target sin verse afectada por el segundo de silencio
        self.assertAlmostEqual(active_rms_db, -17.0, delta=0.5)

    def test_soft_limiter_prevents_hard_clipping(self):
        # Señal con picos excesivos (>1.0)
        signal = (0.20 * np.sin(2 * np.pi * 440 * self.t)).astype(np.float32)
        signal[100:150] = 0.98 # transitorio de golpe de aire

        norm = voice_studio_backend.normalize_speech_rms(signal, target_dbfs=-17.0, sample_rate=16000)
        peak = np.max(np.abs(norm))
        # Ningún valor debe exceder el umbral seguro de 0.95 ni saturar
        self.assertLessEqual(peak, 0.95)

    def test_batch_normalize_lifecycle(self):
        test_id = 'test_batch_norm_clip'
        try:
            # Crear WAV sintético bajo
            waveform = (np.sin(2 * np.pi * 440 * self.t) * 4000).astype(np.int16)
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(waveform.tobytes())

            voice_studio_backend.save_item_recording(test_id, wav_io.getvalue())

            # Ejecutar nivelación masiva
            res = voice_studio_backend.batch_normalize_all_recordings(target_dbfs=-17.0)
            self.assertEqual(res['status'], 'ok')
            self.assertGreaterEqual(res['normalized_count'], 1)

            # Verificar que el WAV existe y tiene audio calibrado
            w_path = voice_studio_backend.AUDIO_DIR / f'{test_id}.wav'
            self.assertTrue(w_path.exists())
            with wave.open(str(w_path), 'rb') as wf:
                raw = wf.readframes(wf.getnframes())
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                rms_db = 20.0 * np.log10(np.sqrt(np.mean(samples**2) + 1e-9))
                self.assertAlmostEqual(rms_db, -17.0, delta=0.6)
        finally:
            voice_studio_backend.delete_item_recording(test_id)

if __name__ == '__main__':
    unittest.main()
