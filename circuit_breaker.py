# -*- coding: utf-8 -*-
"""
==============================================================================
RESTAURANTE RYU - PATRÓN DE RESILIENCIA CIRCUIT BREAKER
Control de latencia estricta (<800ms) y aislamiento de fallos para el Motor de Voz
==============================================================================
"""

import time
import enum
import asyncio
import logging
import threading
from typing import Callable, Any, Optional, Dict

logger = logging.getLogger("RyuCircuitBreaker")


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Lanzada cuando se intenta ejecutar una operación y el circuito está ABIERTO."""
    pass


class CircuitBreakerTimeoutException(Exception):
    """Lanzada cuando una operación excede el umbral estricto de latencia."""
    pass


class CircuitBreaker:
    """
    Implementación thread-safe y compatible con asyncio del patrón Circuit Breaker.
    
    Reglas de transición:
    1. CLOSED:
       - Ejecución normal.
       - Si ocurren `failure_threshold` fallos consecutivos (o llamadas que superen `timeout_threshold`),
         el circuito transiciona a OPEN.
    2. OPEN:
       - Todas las llamadas fallan inmediatamente o ejecutan el fallback configurado.
       - Tras `recovery_timeout` segundos, transiciona a HALF_OPEN para una prueba controlada.
    3. HALF_OPEN:
       - Se permite una llamada de prueba.
       - Si triunfa, el circuito se restablece a CLOSED.
       - Si falla o excede el tiempo límite, vuelve inmediatamente a OPEN y reinicia el reloj.
    """

    def __init__(
        self,
        name: str = "voice_tts",
        failure_threshold: int = 3,
        recovery_timeout: float = 15.0,
        timeout_threshold: float = 0.8,
        half_open_successes_needed: int = 1
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.timeout_threshold = timeout_threshold
        self.half_open_successes_needed = half_open_successes_needed

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._successful_half_open_calls = 0
        self._last_state_change = time.time()
        self._last_failure_time = 0.0
        self._total_calls = 0
        self._total_failures = 0
        self._total_timeouts = 0
        self._total_fallbacks = 0
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._evaluate_state()
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def _evaluate_state(self):
        """Evalúa si un circuito OPEN debe pasar a HALF_OPEN por expiración de tiempo."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._successful_half_open_calls = 0
                self._last_state_change = time.time()
                logger.info(f"⚡ [CircuitBreaker:{self.name}] Transición a HALF_OPEN tras {elapsed:.1f}s de recuperación.")

    def record_success(self, duration: Optional[float] = None):
        """Registra una ejecución exitosa."""
        with self._lock:
            self._total_calls += 1
            if self._state == CircuitState.HALF_OPEN:
                self._successful_half_open_calls += 1
                if self._successful_half_open_calls >= self.half_open_successes_needed:
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._successful_half_open_calls = 0
                    self._last_state_change = time.time()
                    logger.info(f"✅ [CircuitBreaker:{self.name}] Circuito RESTABLECIDO a CLOSED exitosamente.")
            else:
                self._consecutive_failures = 0

    def record_failure(self, exception: Optional[Exception] = None, duration: Optional[float] = None, is_timeout: bool = False):
        """Registra un fallo o timeout en la ejecución."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            if is_timeout:
                self._total_timeouts += 1

            self._consecutive_failures += 1
            self._last_failure_time = time.time()

            dur_str = f" ({duration*1000:.1f}ms)" if duration is not None else ""
            reason = "Timeout excedido (>800ms)" if is_timeout else f"Excepción: {exception}"
            logger.warning(
                f"⚠️ [CircuitBreaker:{self.name}] Fallo registrado #{self._consecutive_failures}{dur_str}. Causa: {reason}"
            )

            if self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if self._state == CircuitState.HALF_OPEN or self._consecutive_failures >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_state_change = time.time()
                    logger.error(
                        f"🚨 [CircuitBreaker:{self.name}] Circuito ABIERTO (OPEN). Conmutando a fallback de voz inmediato."
                    )

    def reset(self):
        """Restablece manualmente el circuito al estado inicial CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._successful_half_open_calls = 0
            self._last_state_change = time.time()
            logger.info(f"🔄 [CircuitBreaker:{self.name}] Reinicio manual a CLOSED.")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas operacionales del Circuit Breaker."""
        with self._lock:
            self._evaluate_state()
            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self.failure_threshold,
                "timeout_threshold_sec": self.timeout_threshold,
                "recovery_timeout_sec": self.recovery_timeout,
                "total_calls": self._total_calls,
                "total_failures": self._total_failures,
                "total_timeouts": self._total_timeouts,
                "total_fallbacks": self._total_fallbacks,
                "last_state_change": self._last_state_change,
            }

    def call(self, func: Callable, *args, fallback: Optional[Callable] = None, **kwargs) -> Any:
        """
        Ejecuta una función síncrona protegida por el Circuit Breaker.
        Si el circuito está OPEN o la función falla/supera el umbral de latencia, se ejecuta el fallback.
        """
        with self._lock:
            self._evaluate_state()
            if self._state == CircuitState.OPEN:
                self._total_fallbacks += 1
                if fallback:
                    return fallback(*args, **kwargs)
                raise CircuitBreakerOpenException(f"Circuito {self.name} está ABIERTO.")

        t0 = time.time()
        try:
            res = func(*args, **kwargs)
            duration = time.time() - t0
            if duration > self.timeout_threshold:
                self.record_failure(duration=duration, is_timeout=True)
                if fallback:
                    self._total_fallbacks += 1
                    return fallback(*args, **kwargs)
                return res
            self.record_success(duration=duration)
            return res
        except Exception as exc:
            duration = time.time() - t0
            self.record_failure(exception=exc, duration=duration)
            if fallback:
                with self._lock:
                    self._total_fallbacks += 1
                return fallback(*args, **kwargs)
            raise

    async def call_async(self, coro_func: Callable, *args, fallback: Optional[Callable] = None, **kwargs) -> Any:
        """
        Ejecuta una función asíncrona (coroutine) protegida por el Circuit Breaker.
        Si el circuito está OPEN o excede `timeout_threshold`, aplica fallback inmediatamente sin bloquear el hilo.
        """
        with self._lock:
            self._evaluate_state()
            if self._state == CircuitState.OPEN:
                self._total_fallbacks += 1
                if fallback:
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)
                raise CircuitBreakerOpenException(f"Circuito {self.name} está ABIERTO.")

        t0 = time.time()
        try:
            # Ejecutar con timeout estricto para no colgar la llamada SIP en vivo
            coro = coro_func(*args, **kwargs)
            res = await asyncio.wait_for(coro, timeout=self.timeout_threshold)
            duration = time.time() - t0
            self.record_success(duration=duration)
            return res
        except asyncio.TimeoutError:
            duration = time.time() - t0
            self.record_failure(duration=duration, is_timeout=True)
            if fallback:
                with self._lock:
                    self._total_fallbacks += 1
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback(*args, **kwargs)
                return fallback(*args, **kwargs)
            raise CircuitBreakerTimeoutException(f"Operación en {self.name} excedió timeout de {self.timeout_threshold}s")
        except Exception as exc:
            duration = time.time() - t0
            self.record_failure(exception=exc, duration=duration)
            if fallback:
                with self._lock:
                    self._total_fallbacks += 1
                if asyncio.iscoroutinefunction(fallback):
                    return await fallback(*args, **kwargs)
                return fallback(*args, **kwargs)
            raise


# Instancia global para protección del pipeline de voz y TTS
voice_circuit_breaker = CircuitBreaker(
    name="voice_engine_tts",
    failure_threshold=3,
    recovery_timeout=15.0,
    timeout_threshold=0.8,
    half_open_successes_needed=1
)
