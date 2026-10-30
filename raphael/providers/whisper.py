"""Offline speech recognition. Audio stays in RAM; no runtime downloads."""
import threading
import time

from ..contracts import Result
from ..errors import AppError
from .runtime import AUDIO_IMPORT_LOCK


class WhisperProvider:
    def __init__(self, config):
        self.config = config
        self.model = None
        self._closed = threading.Event()

    def start(self):
        folder = self.config.resolve(self.config.transcription.model)
        required = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
        if any(not (folder / name).is_file() for name in required):
            raise AppError("The local microphone model is missing. Check [transcription] in config.toml.",
                           503, "transcription_model_missing")
        try:
            with AUDIO_IMPORT_LOCK:
                from faster_whisper import WhisperModel
        except ImportError:
            raise AppError("Local speech-recognition libraries are missing. Install requirements.lock.txt.",
                           503, "transcription_runtime_missing") from None
        loaded = WhisperModel(str(folder), device="cpu", compute_type="int8",
                              cpu_threads=self.config.transcription.threads,
                              num_workers=1, local_files_only=True)
        if not self._closed.is_set():
            self.model = loaded

    def transcribe(self, request, cancel, on_delta):
        import numpy as np
        cancel.check()
        model = self.model
        if model is None:
            raise AppError("Local speech recognition is unavailable. You can still type.", 503,
                           "transcription_unavailable")
        audio = np.frombuffer(request.pcm, dtype="<i2").astype(np.float32) / 32768.0
        if np.max(np.abs(audio)) < 0.002:
            raise AppError("I didn't hear any speech. Check your microphone and try again.", 422, "no_speech")
        started = time.monotonic()
        segments, info = model.transcribe(
            audio, language=None if request.language == "auto" else request.language,
            beam_size=1, temperature=0, condition_on_previous_text=False,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 350},
            no_speech_threshold=0.6, max_new_tokens=256)
        parts = []
        for segment in segments:
            cancel.check()
            text = segment.text.strip()
            if text:
                on_delta((' ' if parts else '') + text)
                parts.append(text)
        cancel.check()
        transcript = " ".join(parts).strip()
        if not transcript:
            raise AppError("I didn't hear clear speech. Move closer to the microphone and try again.",
                           422, "no_speech")
        if len(transcript) > 6000:
            raise AppError("That recording produced too much text. Try a shorter recording.")
        return Result({"language": info.language, "duration_seconds": round(len(audio) / 16000, 2),
                       "generation_seconds": round(time.monotonic() - started, 2),
                       "engine": "Whisper base · local"})

    def close(self):
        self._closed.set()
        self.model = None
