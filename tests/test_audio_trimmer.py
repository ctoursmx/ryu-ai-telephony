import io
import wave
import unittest
import numpy as np
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import voice_studio_backend

class TestAudioTrimmer(unittest.TestCase):
    def setUp(self):
        self.sample_rate = 16000
        self.duration = 2.0
        t = np.linspace(0, self.duration, int(self.sample_rate * self.duration), endpoint=False)
        waveform = (np.sin(2 * np.pi * 440 * t) * 16384).astype(np.int16)

        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(waveform.tobytes())
        self.raw_wav_bytes = wav_io.getvalue()

    def test_transcode_browser_audio_without_trim(self):
        alaw, wav, dur = voice_studio_backend.transcode_browser_audio(self.raw_wav_bytes)
        self.assertAlmostEqual(dur, 2.0, places=1)
        self.assertGreater(len(alaw), 15000)
        self.assertGreater(len(wav), 30000)

    def test_transcode_browser_audio_with_trim(self):
        alaw, wav, dur = voice_studio_backend.transcode_browser_audio(
            self.raw_wav_bytes,
            start_sec=0.2,
            end_sec=1.7
        )
        self.assertAlmostEqual(dur, 1.5, places=1)
        self.assertEqual(len(alaw), 12000)

    def test_trim_item_recording_lifecycle(self):
        test_item_id = 'test_trim_clip'
        try:
            save_res = voice_studio_backend.save_item_recording(test_item_id, self.raw_wav_bytes)
            self.assertEqual(save_res['status'], 'ok')
            self.assertAlmostEqual(save_res['duration_sec'], 2.0, places=1)

            trim_res = voice_studio_backend.trim_item_recording(test_item_id, start_sec=0.1, end_sec=1.6)
            self.assertEqual(trim_res['status'], 'ok')
            self.assertAlmostEqual(trim_res['duration_sec'], 1.5, places=1)

            wav_path = voice_studio_backend.AUDIO_DIR / f'{test_item_id}.wav'
            self.assertTrue(wav_path.exists())
            with wave.open(str(wav_path), 'rb') as wf:
                dur = wf.getnframes() / wf.getframerate()
                self.assertAlmostEqual(dur, 1.5, places=1)

            alaw_path = voice_studio_backend.AUDIO_DIR / f'{test_item_id}.alaw'
            self.assertTrue(alaw_path.exists())
            self.assertEqual(len(alaw_path.read_bytes()), 12000)

        finally:
            voice_studio_backend.delete_item_recording(test_item_id)

    def test_invalid_trim_ranges(self):
        with self.assertRaises(ValueError):
            voice_studio_backend.transcode_browser_audio(
                self.raw_wav_bytes,
                start_sec=1.8,
                end_sec=1.2
            )

if __name__ == '__main__':
    unittest.main()
