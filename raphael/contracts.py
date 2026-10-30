"""Small data contracts shared by services and replaceable providers."""
from dataclasses import dataclass
import logging
import threading
from typing import Callable

from .errors import Cancelled


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class Profile:
    name: str = ""
    notes: tuple[str, ...] = ()

    def as_dict(self):
        return {"name": self.name, "notes": list(self.notes)}


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: tuple[Message, ...]
    profile: Profile


@dataclass(frozen=True)
class SpeechRequest:
    text: str
    voice: str = "heart"
    speed: float = 1.0


@dataclass(frozen=True)
class TranscriptionRequest:
    pcm: bytes
    language: str = "en"


@dataclass(frozen=True)
class Result:
    details: dict
    audio: bytes | None = None


class Cancellation:
    """Thread-safe cancellation with a hook for interrupting socket reads."""
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []

    def is_set(self):
        return self._event.is_set()

    def check(self):
        if self.is_set():
            raise Cancelled()

    def wait(self, seconds):
        return self._event.wait(seconds)

    def register(self, callback):
        with self._lock:
            run_now = self.is_set()
            if not run_now:
                self._callbacks.append(callback)
        if run_now:
            callback()

    def unregister(self, callback):
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def cancel(self):
        with self._lock:
            self._event.set()
            callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            try:
                callback()
            except Exception as error:
                logging.getLogger("raphael.cancel").warning("interrupt_failed exception=%s", type(error).__name__)
