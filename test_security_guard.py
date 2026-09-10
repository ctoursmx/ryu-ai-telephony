"""
======================================================================
RESTAURANTE RYU - SUITE DE PRUEBAS DE SEGURIDAD Y BLINDAJE (ANTI-SPAM)
Valida CallWatchdog, CallRateLimiter, MessageRateLimiter, InputSanitizer
======================================================================
"""

import os
import sys
import time
import unittest

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from security_guard import (
    CallWatchdog,
    CallRateLimiter,
    MessageRateLimiter,
    InputSanitizer,
    cleanup_temp_audio_files
)

class TestSecurityGuard(unittest.TestCase):

    def test_01_call_watchdog_time_limits(self):
        """Valida que CallWatchdog emita advertencia al minuto 5 y corte forzoso al minuto 6."""
        # Instanciar con tiempos breves para prueba unitaria
        dog = CallWatchdog(call_id="call_test_1", max_duration_sec=6, warning_threshold_sec=3, max_turns=5)
        
        # En t=0, debe estar OK
        status, msg = dog.check_status()
        self.assertEqual(status, "OK")

        # Simular t=3.5s (umbral de advertencia)
        dog.start_time = time.time() - 3.5
        status, msg = dog.check_status()
        self.assertEqual(status, "WARNING_TIME")
        self.assertIn("un minuto", msg)

        # La segunda vez que se consulte, la advertencia no debe repetirse
        status_repeat, _ = dog.check_status()
        self.assertEqual(status_repeat, "OK")

        # Simular t=6.5s (límite máximo alcanzado)
        dog.start_time = time.time() - 6.5
        status_expired, msg_exp = dog.check_status()
        self.assertEqual(status_expired, "EXPIRED_TIME")
        self.assertIn("alcanzado el límite", msg_exp)
        print("✅ Test 01 - CallWatchdog Time Limits: PASSED (Advertencia y timeout validados)")

    def test_02_call_watchdog_turn_limits(self):
        """Valida que CallWatchdog corte la llamada si se excede el número máximo de turnos."""
        dog = CallWatchdog(call_id="call_test_2", max_duration_sec=360, warning_threshold_sec=300, max_turns=3)
        
        dog.record_turn() # Turno 1
        dog.record_turn() # Turno 2
        status, _ = dog.check_status()
        self.assertEqual(status, "OK")

        dog.record_turn() # Turno 3 (límite)
        status, msg = dog.check_status()
        self.assertEqual(status, "EXPIRED_TURNS")
        self.assertIn("número máximo de turnos", msg)
        print("✅ Test 02 - CallWatchdog Turn Limits: PASSED (Máximo 20 turnos activo)")

    def test_03_call_rate_limiter_flooding(self):
        """Valida que se bloquee un número tras exceder el límite de llamadas en 5 minutos."""
        limiter = CallRateLimiter(max_calls=3, window_seconds=60, cooldown_seconds=120)
        phone = "+523385269999"

        # Primeras 3 llamadas permitidas
        for i in range(3):
            can_call, _ = limiter.can_accept_call(phone)
            self.assertTrue(can_call, f"La llamada {i+1} debió ser permitida")
            limiter.record_call_start(phone)

        # 4ta llamada: debe ser bloqueada por rate limit
        can_call_4, reason = limiter.can_accept_call(phone)
        self.assertFalse(can_call_4)
        self.assertIn("límite", reason.lower())
        print("✅ Test 03 - CallRateLimiter Flooding: PASSED (Bloqueo tras ráfaga telefónica)")

    def test_04_call_rate_limiter_short_prank_calls(self):
        """Valida que 3 llamadas consecutivas de broma / fantasma (<6s) activen cooldown."""
        limiter = CallRateLimiter(max_calls=10, window_seconds=300, cooldown_seconds=300)
        phone = "+523385268888"

        # Simular 3 llamadas que cuelgan a los 2 segundos
        for _ in range(3):
            limiter.record_call_start(phone)
            limiter.record_call_end(phone, duration_seconds=2.0)

        # Siguiente llamada debe ser rechazada por spam de llamadas fantasma
        can_call, reason = limiter.can_accept_call(phone)
        self.assertFalse(can_call)
        print("✅ Test 04 - CallRateLimiter Short Prank Calls: PASSED (Detección de llamadas fantasma)")

    def test_05_message_rate_limiter(self):
        """Valida que el limitador de mensajes HTTP bloquee con 429 al exceder tasa."""
        limiter = MessageRateLimiter(max_requests=5, window_seconds=10)
        client = "192.168.1.50_session123"

        for i in range(5):
            allowed, _ = limiter.check_rate_limit(client)
            self.assertTrue(allowed)

        # 6ta petición inmediata debe ser rechazada
        allowed_6, retry_after = limiter.check_rate_limit(client)
        self.assertFalse(allowed_6)
        self.assertGreaterEqual(retry_after, 1)
        print("✅ Test 05 - MessageRateLimiter: PASSED (Rate limit HTTP 429 funcional)")

    def test_06_input_sanitizer_and_spam(self):
        """Valida que se trunquen textos gigantes y se detecte repetición compulsiva."""
        # 1. Truncamiento
        huge_text = "Quiero sushi " * 100 # ~1300 caracteres
        sanitized = InputSanitizer.sanitize_text(huge_text, max_chars=350)
        self.assertLessEqual(len(sanitized), 355)
        self.assertTrue(sanitized.endswith("..."))

        # 2. Detección de repetición compulsiva
        history = [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "Hola, ¿qué deseas?"},
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "¿Qué se te antoja?"},
            {"role": "user", "content": "hola"}
        ]
        is_spam = InputSanitizer.is_spam_repetition("hola", history, threshold=3)
        self.assertTrue(is_spam)

        not_spam = InputSanitizer.is_spam_repetition("dame un sushi", history, threshold=3)
        self.assertFalse(not_spam)
        print("✅ Test 06 - InputSanitizer & Spam Detection: PASSED")

    def test_07_temp_audio_cleaner(self):
        """Valida que la función de mantenimiento elimine audios temporales antiguos."""
        # Crear archivo falso temporal
        temp_file = "fast_reply_test_dummy.mp3"
        with open(temp_file, "w") as f:
            f.write("dummy audio")

        # Forzar tiempo de modificación antiguo (hace 15 minutos)
        past_time = time.time() - 900
        os.utime(temp_file, (past_time, past_time))

        deleted = cleanup_temp_audio_files(directory=".", max_age_seconds=600)
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(os.path.exists(temp_file))
        print("✅ Test 07 - Temp Audio Cleaner: PASSED (Archivos huérfanos eliminados)")

if __name__ == "__main__":
    unittest.main()
