# -*- coding: utf-8 -*-
"""
tests/test_circuit_breaker.py
Pruebas unitarias completas para el patrón Circuit Breaker del motor de voz.
"""

import time
import asyncio
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenException,
    CircuitBreakerTimeoutException
)


class TestCircuitBreaker(unittest.TestCase):

    def setUp(self):
        self.cb = CircuitBreaker(
            name="test_cb",
            failure_threshold=3,
            recovery_timeout=0.2,  # 200ms para pruebas rápidas
            timeout_threshold=0.1,  # 100ms para pruebas de timeout
            half_open_successes_needed=1
        )

    def test_initial_state_is_closed(self):
        self.assertEqual(self.cb.state, CircuitState.CLOSED)
        self.assertFalse(self.cb.is_open)

    def test_successful_calls_keep_circuit_closed(self):
        def add(a, b):
            return a + b

        res = self.cb.call(add, 2, 3)
        self.assertEqual(res, 5)
        self.assertEqual(self.cb.state, CircuitState.CLOSED)
        self.assertEqual(self.cb.get_stats()["consecutive_failures"], 0)

    def test_three_consecutive_failures_trips_to_open(self):
        def failing_func():
            raise RuntimeError("Fallo simulado")

        def fallback_func():
            return "FALLBACK_AUDIO"

        # 1er fallo
        res1 = self.cb.call(failing_func, fallback=fallback_func)
        self.assertEqual(res1, "FALLBACK_AUDIO")
        self.assertEqual(self.cb.state, CircuitState.CLOSED)
        self.assertEqual(self.cb.get_stats()["consecutive_failures"], 1)

        # 2do fallo
        res2 = self.cb.call(failing_func, fallback=fallback_func)
        self.assertEqual(res2, "FALLBACK_AUDIO")
        self.assertEqual(self.cb.state, CircuitState.CLOSED)
        self.assertEqual(self.cb.get_stats()["consecutive_failures"], 2)

        # 3er fallo -> debe pasar a OPEN
        res3 = self.cb.call(failing_func, fallback=fallback_func)
        self.assertEqual(res3, "FALLBACK_AUDIO")
        self.assertEqual(self.cb.state, CircuitState.OPEN)
        self.assertTrue(self.cb.is_open)

        # 4ta llamada: no ejecuta failing_func, devuelve fallback inmediatamente
        executed = []
        def normal_func():
            executed.append(True)
            return "OK"

        res4 = self.cb.call(normal_func, fallback=fallback_func)
        self.assertEqual(res4, "FALLBACK_AUDIO")
        self.assertEqual(len(executed), 0, "No debió ejecutarse la función con el circuito OPEN")

    def test_timeout_threshold_triggers_failure_and_fallback(self):
        def slow_func():
            time.sleep(0.15)  # Más que 100ms
            return "SLOW_RESULT"

        def fallback_func():
            return "FAST_FALLBACK"

        res = self.cb.call(slow_func, fallback=fallback_func)
        self.assertEqual(res, "FAST_FALLBACK")
        self.assertEqual(self.cb.get_stats()["total_timeouts"], 1)

    def test_recovery_to_half_open_and_closed(self):
        def failing_func():
            raise RuntimeError("Fallo")

        for _ in range(3):
            self.cb.call(failing_func, fallback=lambda: "FALLBACK")

        self.assertEqual(self.cb.state, CircuitState.OPEN)

        # Esperar a que pase el recovery_timeout (200ms)
        time.sleep(0.25)
        self.assertEqual(self.cb.state, CircuitState.HALF_OPEN)

        # Llamada exitosa en HALF_OPEN debe restablecer a CLOSED
        res = self.cb.call(lambda: "SUCCESS_NOW")
        self.assertEqual(res, "SUCCESS_NOW")
        self.assertEqual(self.cb.state, CircuitState.CLOSED)

    def test_async_call_with_timeout_and_fallback(self):
        async def async_slow():
            await asyncio.sleep(0.2)
            return "SLOW_ASYNC"

        async def async_fallback():
            return "FALLBACK_ASYNC"

        res = asyncio.run(self.cb.call_async(async_slow, fallback=async_fallback))
        self.assertEqual(res, "FALLBACK_ASYNC")
        self.assertGreaterEqual(self.cb.get_stats()["total_timeouts"], 1)


if __name__ == "__main__":
    unittest.main()
