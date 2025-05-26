import threading
import time
from typing import Optional

from .singleton import singleton


@singleton
class BluetoothKeepAliveProvider:
    """
    Bluetooth Speaker Keep-Alive Provider.

    Manages periodic silent audio playback to prevent Bluetooth speakers from
    entering sleep mode and adds audio padding to prevent word clipping.
    """

    def __init__(
        self,
        keepalive_interval: float = 60.0,
        padding_duration: float = 0.3,
        enabled: bool = True,
    ):
        # Initialize or update configuration
        if not hasattr(self, "_lock"):
            self._lock = threading.Lock()
            self._running = False
            self._keepalive_thread: Optional[threading.Thread] = None
            self._last_audio_time = 0.0
            self._tts_providers = []

        # Always update configuration parameters on each call
        with self._lock:
            self._enabled = enabled
            self._keepalive_interval = keepalive_interval
            self._padding_duration = padding_duration

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        with self._lock:
            self._enabled = value

    def register_tts_provider(self, tts_provider) -> None:
        with self._lock:
            if tts_provider not in self._tts_providers:
                self._tts_providers.append(tts_provider)

    def clear_tts_providers(self) -> None:
        """Clear all registered TTS providers. Useful for test isolation."""
        with self._lock:
            self._tts_providers.clear()

    def add_audio_padding(self, text: str) -> str:
        with self._lock:
            enabled = self._enabled
            padding_duration = self._padding_duration

        if not enabled or not text.strip():
            return text
        padding_chars = int(padding_duration * 10)
        silent_padding = "." * min(padding_chars, 3)
        return f"{silent_padding} {text.strip()}"

    def notify_audio_activity(self) -> None:
        with self._lock:
            self._last_audio_time = time.time()

    def _generate_keepalive_audio(self) -> None:
        with self._lock:
            enabled = self._enabled
            providers = self._tts_providers.copy()

        if not enabled or not providers:
            return

        for provider in providers:
            provider.add_pending_message(".")

    def _keepalive_loop(self) -> None:
        while self._running:
            current_time = time.time()
            with self._lock:
                time_since_last_audio = current_time - self._last_audio_time
                should_keepalive = (
                    self._enabled and time_since_last_audio >= self._keepalive_interval
                )

            if should_keepalive:
                self._generate_keepalive_audio()
                with self._lock:
                    self._last_audio_time = current_time

            time.sleep(1.0)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._last_audio_time = time.time()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, daemon=True
        )
        self._keepalive_thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=5.0)
