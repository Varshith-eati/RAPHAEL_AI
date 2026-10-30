"""Replaceable local speech adapter. Clean WAV output without reverb."""
import io
import re
import textwrap
import threading
import time

from ..contracts import Result
from ..errors import AppError
from .runtime import AUDIO_IMPORT_LOCK

VOICES = {"heart": {"id": "af_heart", "name": "Soft · Heart"},
          "bella": {"id": "af_bella", "name": "Bright · Bella"},
          "sarah": {"id": "af_sarah", "name": "Gentle · Sarah"}}


ABBREVIATIONS = ("Dr", "Mr", "Mrs", "Ms", "Prof", "St", "vs", "e.g", "i.e")
SENTENCE_END = (r"(?<=[.!?])" + "".join(rf"(?<!\b{re.escape(a)}\.)" for a in ABBREVIATIONS) + r"\s+|\n+")


def speech_chunks(text: str):
    text = re.sub(r"```[\s\S]*?```", " Code is shown in the conversation. ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*#`]+", "", text)
    text = re.sub(r"(?<!\w)_+|_+(?!\w)", "", text).replace("_", " ").strip()
    if not text:
        raise AppError("There is no text to speak.")
    return [chunk for sentence in re.split(SENTENCE_END, text, flags=re.IGNORECASE)
            for chunk in textwrap.wrap(sentence, width=220, break_long_words=True)]


class KokoroProvider:
    voices = VOICES

    def __init__(self, config):
        self.config = config
        self.model = None
        self._closed = threading.Event()

    def start(self):
        model = self.config.resolve(self.config.voice.model)
        voices = self.config.resolve(self.config.voice.voices)
        missing = [path.name for path in (model, voices) if not path.is_file()]
        if missing:
            raise AppError(f"Voice files are missing ({', '.join(missing)}). Check the [voice] paths in "
                           "config.toml. Text chat still works.", 503, "voice_files_missing")
        try:
            with AUDIO_IMPORT_LOCK:
                import onnxruntime as ort
                from kokoro_onnx import Kokoro
        except ImportError:
            raise AppError("Voice libraries are missing. Use the configured Python runtime.",
                           503, "voice_runtime_missing") from None
        options = ort.SessionOptions()
        options.intra_op_num_threads = self.config.voice.threads
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        loaded = Kokoro.from_session(session, str(voices))
        if not self._closed.is_set():
            self.model = loaded

    def synthesize(self, request, cancel):
        import numpy as np
        import soundfile as sf
        model = self.model
        if model is None:
            raise AppError("The local voice is unavailable. Text chat still works.", 503, "voice_unavailable")
        started, pieces, rate = time.monotonic(), [], 24000
        for chunk in speech_chunks(request.text):
            cancel.check()
            samples, rate = model.create(chunk, voice=self.voices[request.voice]["id"],
                                         speed=request.speed, lang="en-us")
            cancel.check()
            if pieces:
                pieces.append(np.zeros(int(rate * 0.08), dtype=np.float32))
            pieces.append(samples)
        if not pieces:
            raise AppError("There is no text to speak.")
        samples = np.concatenate(pieces)
        if not samples.size or not np.isfinite(samples).all():
            raise AppError("The voice returned invalid audio. Please retry.", 502, "invalid_audio")
        peak = float(np.max(np.abs(samples)))
        if peak > 0.97:
            samples = samples * (0.97 / peak)
        buffer = io.BytesIO()
        sf.write(buffer, samples, rate, format="WAV", subtype="PCM_16")
        return Result({"voice": request.voice, "duration_seconds": round(len(samples) / rate, 2),
                       "generation_seconds": round(time.monotonic() - started, 2),
                       "engine": "Kokoro · local"}, buffer.getvalue())

    def close(self):
        self._closed.set()
        self.model = None
