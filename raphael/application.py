"""Composition root: select adapters here; the API never imports model SDKs."""
from . import __version__
from .providers.kokoro import KokoroProvider
from .providers.ollama import OllamaProvider
from .providers.whisper import WhisperProvider
from .services.chat import ChatService
from .services.jobs import JobManager
from .services.voice import VoiceService
from .services.transcription import TranscriptionService
from .storage import ProfileStore
from .laptop.service import LaptopTools
from .realtime.settings import SettingsStore, route_model
from .realtime.metrics import Performance
from dataclasses import replace
import time
from .validation import chat_request, profile_request, speech_request, transcription_request


class Application:
    def __init__(self, config, *, chat_provider=None, voice_provider=None, profile_store=None, transcription_provider=None, laptop_tools=None):
        self.config = config
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsStore(config.data_dir / 'interaction-settings.json')
        self.performance = Performance(config.data_dir, self.settings.get()['diagnostics'])
        self.desktop = None
        self.chat = chat_provider if chat_provider is not None else OllamaProvider(config)
        self.voice = voice_provider if voice_provider is not None else KokoroProvider(config)
        self.transcription = transcription_provider if transcription_provider is not None else WhisperProvider(config)
        self.profiles = profile_store if profile_store is not None else ProfileStore(config.data_dir / "preferences.sqlite3")
        self.laptop = laptop_tools or LaptopTools(config)
        self.jobs = JobManager({"chat": ChatService(self.chat, self.laptop, self.settings, self.performance),
                                "voice": VoiceService(self.voice, config.voice.cache_bytes),
                                "transcription": TranscriptionService(self.transcription)}, config.jobs, self.performance)

    def start(self, lazy=False):
        self.jobs.start(lazy=lazy)

    def status(self):
        health = self.jobs.health()
        models = list(self.chat.models) if health["chat"]["state"] == "ready" else []
        return {"app": "raphael-modular", "version": __version__, "api_version": 1,
                "chat": health["chat"]["state"], "voice": health["voice"]["state"],
                "chat_error": health["chat"]["error"], "voice_error": health["voice"]["error"],
                "transcription": health["transcription"]["state"],
                "transcription_error": health["transcription"]["error"],
                "laptop": self.laptop.status(), "interaction": self.settings.get(),
                "desktop": self.desktop is not None,
                "models": models, "default_model": next(iter(models), None),
                "voices": [{"id": key, "name": value["name"]} for key, value in self.voice.voices.items()],
                "location": "On this computer", "memory": "local_database"}

    def submit_chat(self, payload):
        started = time.perf_counter()
        profile = self.profiles.get()
        self.performance.record('memory', time.perf_counter() - started)
        options = self.settings.get()
        profile = replace(profile, notes=profile.notes[:options['memory_limit']])
        if isinstance(payload, dict) and payload.get('model') == 'auto':
            payload = {**payload, 'model': route_model('auto', payload.get('messages', []), self.config.chat.models, options)}
        request = chat_request(payload, self.config.chat.models, profile)
        request = replace(request, profile=replace(request.profile, notes=request.profile.notes[:options['memory_limit']]))
        return self.jobs.submit("chat", request)

    def submit_speech(self, payload):
        request = speech_request(payload, self.voice.voices)
        return self.jobs.submit("voice", request)

    def submit_transcription(self, audio, language=None):
        request = transcription_request(audio, language or self.config.transcription.language)
        return self.jobs.submit("transcription", request)

    def save_profile(self, payload):
        return self.profiles.save(profile_request(payload)).as_dict()

    def update_settings(self, payload):
        from .errors import AppError
        from .realtime.settings import validate
        proposed = validate({**self.settings.get(), **payload})
        if self.desktop:
            return self.desktop.change_settings(payload)
        if proposed['startup_enabled'] or proposed['wake_enabled']:
            raise AppError('Open Launch-Desktop.cmd to enable background wake listening or Windows startup.')
        result = self.settings.update(payload)
        self.performance.enabled = result['diagnostics']
        return result

    def close(self):
        self.jobs.close()
        self.laptop.close()
        self.performance.close()
        if hasattr(self.profiles, 'close'): self.profiles.close()
