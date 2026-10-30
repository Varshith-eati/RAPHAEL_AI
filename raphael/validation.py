"""Validate untrusted JSON before it reaches a model or persistent storage."""
import math
import io
import wave

from .contracts import ChatRequest, Message, Profile, SpeechRequest, TranscriptionRequest
from .errors import AppError


MAX_RECORDING_SECONDS = 30
MAX_RECORDING_BYTES = 16000 * 2 * MAX_RECORDING_SECONDS + 4096


def transcription_request(audio: bytes, language: str) -> TranscriptionRequest:
    if language not in ("en", "hi", "auto"):
        raise AppError("Choose English, Hindi, or automatic language detection.")
    if not 44 <= len(audio) <= MAX_RECORDING_BYTES:
        raise AppError("Record between a quarter second and 30 seconds of speech.", 413, "audio_size")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, "NONE"):
                raise AppError("The recording must be mono, 16-bit, 16 kHz WAV audio.", 400, "audio_format")
            frames = source.getnframes()
            if not 4000 <= frames <= 16000 * MAX_RECORDING_SECONDS:
                raise AppError("Record between a quarter second and 30 seconds of speech.", 400, "audio_duration")
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise AppError("The recording was incomplete. Please record it again.")
    except (wave.Error, EOFError, ValueError):
        raise AppError("That recording is not a valid WAV file.", 400, "audio_format") from None
    return TranscriptionRequest(pcm, language)


def profile_request(payload) -> Profile:
    if not isinstance(payload, dict):
        raise AppError("Saved preferences must be an object.")
    name, notes = payload.get("name", ""), payload.get("notes", [])
    if (not isinstance(name, str) or len(name) > 60
            or not isinstance(notes, list) or len(notes) > 12
            or any(not isinstance(n, str) or not n.strip() or len(n) > 500 for n in notes)):
        raise AppError("Use a name up to 60 characters and up to 12 notes of 500 characters.")
    return Profile(name.strip(), tuple(n.strip() for n in notes))


def chat_request(payload, models, saved_profile: Profile) -> ChatRequest:
    model, messages = payload.get("model"), payload.get("messages")
    if not isinstance(model, str) or model not in models:
        raise AppError("Select an installed local model.")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 25:
        raise AppError("Use between 1 and 25 messages per request.")
    clean = []
    total = 0
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            raise AppError("Invalid conversation role.")
        content = message.get("content")
        if not isinstance(content, str) or not 1 <= len(content.strip()) <= 6000 or len(content) > 6000:
            raise AppError("A message is empty or too long.")
        total += len(content)
        clean.append(Message(message["role"], content.strip()))
    if total > 18000 or clean[-1].role != "user":
        raise AppError("Start a new conversation or shorten your message.")
    profile = profile_request(payload["profile"]) if "profile" in payload else saved_profile
    return ChatRequest(model, tuple(clean), profile)


def speech_request(payload, voices) -> SpeechRequest:
    text, voice, speed = payload.get("text"), payload.get("voice", "heart"), payload.get("speed", 1.0)
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2400 or len(text) > 2400:
        raise AppError("Speech supports 1–2400 characters at a time.")
    if not isinstance(voice, str) or voice not in voices:
        raise AppError("Select one of the included voices.")
    if type(speed) not in (int, float) or not math.isfinite(speed) or not 0.8 <= speed <= 1.2:
        raise AppError("Voice speed must be between 0.8 and 1.2.")
    return SpeechRequest(text.strip(), voice, float(speed))
