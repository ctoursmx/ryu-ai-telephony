"""
======================================================================
RESTAURANTE RYU - MÓDULO DE SEGURIDAD Y BLINDAJE (ANTI-SPAM Y WATCHDOG)
Protección contra TDoS telefónico, llamadas infinitas, abusos y desbordamiento
======================================================================
"""

import os
import glob
import time
import logging
from collections import defaultdict, deque
from typing import Dict, Tuple, Optional, List

logger = logging.getLogger("RyuSecurityGuard")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class CallWatchdog:
    """
    Guardián de Duración y Turnos de Llamada:
    Supervisa el tiempo transcurrido y la cantidad de turnos para evitar
    que una llamada consuma saldo o tokens indefinidamente.
    """
    def __init__(self, call_id: str, max_duration_sec: int = 360, warning_threshold_sec: int = 300, max_turns: int = 20):
        self.call_id = call_id
        self.max_duration_sec = max_duration_sec       # 6 minutos por defecto
        self.warning_threshold_sec = warning_threshold_sec # Aviso al minuto 5
        self.max_turns = max_turns                     # Máximo 20 intercambios
        self.start_time = time.time()
        self.turns_count = 0
        self.warning_spoken = False

    def record_turn(self) -> int:
        self.turns_count += 1
        return self.turns_count

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def check_status(self) -> Tuple[str, str]:
        """
        Evalúa el estado de la llamada.
        Retorna: (STATUS_CODE, MENSAJE_RELEVANTE)
        STATUS_CODE: 'OK' | 'WARNING_TIME' | 'EXPIRED_TIME' | 'EXPIRED_TURNS'
        """
        elapsed = self.elapsed_seconds

        if elapsed >= self.max_duration_sec:
            return (
                "EXPIRED_TIME",
                "Hemos alcanzado el límite de 6 minutos para esta llamada. Para brindar servicio a otros clientes, procederemos a cerrar la llamada. ¡Hasta luego!"
            )

        if self.turns_count >= self.max_turns:
            return (
                "EXPIRED_TURNS",
                "Hemos completado el número máximo de turnos permitidos para esta orden. Si te faltó algo, con gusto te atendemos en una nueva llamada. ¡Hasta luego!"
            )

        if elapsed >= self.warning_threshold_sec and not self.warning_spoken:
            self.warning_spoken = True
            return (
                "WARNING_TIME",
                "Estimado cliente, nos queda un minuto para finalizar tu llamada y atender las demás líneas. ¿Confirmo tu pedido con lo que llevamos registrado?"
            )

        return ("OK", "")

class CallRateLimiter:
    """
    Limitador de Frecuencia y Anti-Spam Telefónico:
    Previene ataques de denegación de servicio telefónico (TDoS) y llamadas
    de broma repetitivas desde el mismo número en ventanas de 5 minutos.
    """
    def __init__(self, max_calls: int = 4, window_seconds: int = 300, cooldown_seconds: int = 600):
        self.max_calls = max_calls                     # Máx 4 llamadas
        self.window_seconds = window_seconds           # en 5 minutos
        self.cooldown_seconds = cooldown_seconds       # 10 min de bloqueo si es abusivo
        self._call_history: Dict[str, deque] = defaultdict(deque)
        self._blocked_numbers: Dict[str, float] = {}   # phone -> unblock_timestamp
        self._short_calls_counter: Dict[str, int] = defaultdict(int)

    def can_accept_call(self, phone: str) -> Tuple[bool, str]:
        """Verifica si el número telefónico tiene permitido entrar o está en cooldown."""
        if not phone or phone == "Número Oculto" or phone == "Desconocido":
            # Llamadas sin identificador se permiten pero con monitoreo individual
            return (True, "OK")

        now = time.time()

        # 1. Verificar si está en lista de cooldown por abuso
        if phone in self._blocked_numbers:
            unblock_at = self._blocked_numbers[phone]
            if now < unblock_at:
                remaining_min = int((unblock_at - now) / 60) + 1
                logger.warning(f"🚫 [Anti-Spam]: Llamada rechazada de {phone}. En cooldown por {remaining_min} min.")
                return (
                    False,
                    f"El número {phone} ha excedido el límite de llamadas permitidas. Por favor intenta de nuevo en {remaining_min} minutos."
                )
            else:
                del self._blocked_numbers[phone]
                self._call_history[phone].clear()

        # 2. Limpiar llamadas fuera de la ventana deslizante
        timestamps = self._call_history[phone]
        while timestamps and (now - timestamps[0]) > self.window_seconds:
            timestamps.popleft()

        # 3. Validar umbral de frecuencia
        if len(timestamps) >= self.max_calls:
            self._blocked_numbers[phone] = now + self.cooldown_seconds
            logger.warning(f"🚫 [Anti-Spam]: {phone} superó {self.max_calls} llamadas en {self.window_seconds}s. Bloqueado temporalmente.")
            return (
                False,
                f"Has alcanzado el límite de {self.max_calls} llamadas en 5 minutos. Tu línea tendrá un breve descanso de 10 minutos."
            )

        return (True, "OK")

    def record_call_start(self, phone: str):
        if phone and phone not in ["Número Oculto", "Desconocido"]:
            self._call_history[phone].append(time.time())

    def record_call_end(self, phone: str, duration_seconds: float):
        """Monitorea llamadas fantasma (< 5s) que buscan saturar la línea."""
        if not phone or phone in ["Número Oculto", "Desconocido"]:
            return

        if duration_seconds < 6.0:
            self._short_calls_counter[phone] += 1
            if self._short_calls_counter[phone] >= 3:
                # 3 llamadas fantasma consecutivas activan cooldown
                self._blocked_numbers[phone] = time.time() + self.cooldown_seconds
                logger.warning(f"🚫 [Anti-Spam]: {phone} realizó 3 llamadas ultracortas consecutivas (<6s). Bloqueado por 10 min.")
        else:
            self._short_calls_counter[phone] = 0

class MessageRateLimiter:
    """
    Limitador de Tasa HTTP para el Simulador Web y endpoints FastAPI:
    Máximo 15 peticiones por minuto por cliente/sesión.
    """
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._request_history: Dict[str, deque] = defaultdict(deque)

    def check_rate_limit(self, client_id: str) -> Tuple[bool, int]:
        """
        Retorna: (is_allowed, retry_after_seconds)
        """
        now = time.time()
        history = self._request_history[client_id]

        while history and (now - history[0]) > self.window_seconds:
            history.popleft()

        if len(history) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - history[0])) + 1
            return (False, max(1, retry_after))

        history.append(now)
        return (True, 0)

class InputSanitizer:
    """Saneador de entrada contra ataques de texto masivo y repetición compulsiva."""

    @staticmethod
    def sanitize_text(text: str, max_chars: int = 350) -> str:
        """Trunca la entrada a un tamaño seguro para evitar desbordar el contexto del LLM."""
        if not text:
            return ""
        clean = text.strip()
        if len(clean) > max_chars:
            logger.warning(f"🛡️ [InputSanitizer]: Texto truncado de {len(clean)} a {max_chars} caracteres.")
            clean = clean[:max_chars] + "..."
        return clean

    @staticmethod
    def is_spam_repetition(text: str, history: List[Dict[str, str]], threshold: int = 3) -> bool:
        """Detecta si el cliente está enviando compulsivamente el mismo texto para hacer spam."""
        clean = text.strip().lower()
        if len(clean) < 3:
            return False
        
        matches = 0
        for msg in reversed(history):
            if msg.get("role") == "user" and msg.get("content", "").strip().lower() == clean:
                matches += 1
                if matches >= threshold:
                    return True
        return False

def cleanup_temp_audio_files(directory: str = ".", max_age_seconds: int = 600) -> int:
    """
    Elimina archivos de audio temporales (.mp3) huérfanos generados por TTS
    con una antigüedad superior a max_age_seconds (10 minutos por defecto).
    """
    deleted_count = 0
    now = time.time()
    patterns = [
        os.path.join(directory, "fast_reply_*.mp3"),
        os.path.join(directory, "response_*.mp3"),
        os.path.join(directory, "temp_*.wav")
    ]
    for pattern in patterns:
        for filepath in glob.glob(pattern):
            try:
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > max_age_seconds:
                        os.remove(filepath)
                        deleted_count += 1
            except Exception as e:
                logger.warning(f"Aviso limpiando archivo temporal {filepath}: {e}")

    if deleted_count > 0:
        logger.info(f"🧹 [Mantenimiento de Disco]: Se eliminaron {deleted_count} audios temporales antiguos.")
    return deleted_count

# Instancias globales listas para producción
call_rate_limiter = CallRateLimiter()
message_rate_limiter = MessageRateLimiter()
input_sanitizer = InputSanitizer()
