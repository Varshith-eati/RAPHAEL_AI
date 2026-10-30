"""Validated configuration. Relative paths resolve against the TOML file."""
from dataclasses import dataclass, fields, replace
from pathlib import Path
import math
import tomllib


@dataclass(frozen=True)
class ServerConfig:
    port: int = 8768
    max_body_bytes: int = 70000
    request_timeout_seconds: int = 15


@dataclass(frozen=True)
class ChatConfig:
    port: int = 11436
    executable: str = ""
    models_dir: str = "~/.ollama/models"
    models: tuple[str, ...] = ("qwen3.5:4b", "llama3.2:latest")
    context_tokens: int = 4096
    max_reply_tokens: int = 360
    threads: int = 6
    temperature: float = 0.65
    timeout_seconds: int = 150
    startup_timeout_seconds: int = 60


@dataclass(frozen=True)
class VoiceConfig:
    model: str = "../raphael-chat/models/kokoro-v1.0.onnx"
    voices: str = "../raphael-chat/models/voices-v1.0.bin"
    threads: int = 4
    cache_bytes: int = 16000000


@dataclass(frozen=True)
class JobsConfig:
    queue_size: int = 2
    max_records: int = 24
    retention_seconds: int = 900
    deadline_seconds: int = 240


@dataclass(frozen=True)
class TranscriptionConfig:
    model: str = "models/whisper-base"
    threads: int = 4
    language: str = "en"


@dataclass(frozen=True)
class LaptopConfig:
    enabled: bool = False
    workspace: str = "~/Documents/Raphael Workspace"


@dataclass(frozen=True)
class Config:
    root: Path
    data_dir: Path
    server: ServerConfig
    chat: ChatConfig
    voice: VoiceConfig
    jobs: JobsConfig
    transcription: TranscriptionConfig = TranscriptionConfig()
    laptop: LaptopConfig = LaptopConfig()

    def resolve(self, value: str):
        path = Path(value).expanduser()
        return (path if path.is_absolute() else self.root / path).resolve()


def _section(cls, values):
    if not isinstance(values, dict):
        raise ValueError(f"{cls.__name__} must be a TOML section.")
    unknown = set(values) - {field.name for field in fields(cls)}
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} settings: {', '.join(sorted(unknown))}")
    return cls(**values)


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}.")


def load_config(path: Path, port: int | None = None, data_dir: Path | None = None):
    path = path.resolve()
    with path.open("rb") as source:
        raw = tomllib.load(source)
    unknown = set(raw) - {"server", "chat", "voice", "jobs", "transcription", "laptop", "data_dir"}
    if unknown:
        raise ValueError(f"Unknown configuration sections: {', '.join(sorted(unknown))}")
    server = _section(ServerConfig, raw.get("server", {}))
    chat = _section(ChatConfig, raw.get("chat", {}))
    voice = _section(VoiceConfig, raw.get("voice", {}))
    jobs = _section(JobsConfig, raw.get("jobs", {}))
    transcription = _section(TranscriptionConfig, raw.get("transcription", {}))
    laptop = _section(LaptopConfig, raw.get("laptop", {}))
    if type(laptop.enabled) is not bool or not isinstance(laptop.workspace, str) or not laptop.workspace.strip():
        raise ValueError("laptop.enabled must be true/false and laptop.workspace must be a folder path.")
    if port is not None:
        server = replace(server, port=port)
    for value, name, low, high in [
        (server.port, "server.port", 1024, 65535),
        (chat.port, "chat.port", 1024, 65535),
        (server.max_body_bytes, "server.max_body_bytes", 1024, 1000000),
        (server.request_timeout_seconds, "server.request_timeout_seconds", 1, 120),
        (chat.context_tokens, "chat.context_tokens", 1024, 32768),
        (chat.max_reply_tokens, "chat.max_reply_tokens", 16, 4096),
        (chat.threads, "chat.threads", 1, 64),
        (chat.timeout_seconds, "chat.timeout_seconds", 5, 600),
        (chat.startup_timeout_seconds, "chat.startup_timeout_seconds", 5, 300),
        (voice.threads, "voice.threads", 1, 64),
        (transcription.threads, "transcription.threads", 1, 16),
        (voice.cache_bytes, "voice.cache_bytes", 0, 128000000),
        (jobs.queue_size, "jobs.queue_size", 1, 16),
        (jobs.max_records, "jobs.max_records", 4, 256),
        (jobs.retention_seconds, "jobs.retention_seconds", 1, 86400),
        (jobs.deadline_seconds, "jobs.deadline_seconds", 1, 600),
    ]:
        _integer(value, name, low, high)
    if server.port == chat.port:
        raise ValueError("The interface and model service must use different ports.")
    if (type(chat.temperature) not in (int, float)
            or not math.isfinite(chat.temperature) or not 0 <= chat.temperature <= 2):
        raise ValueError("chat.temperature must be between 0 and 2.")
    if (not isinstance(chat.models, (tuple, list)) or not chat.models
            or any(not isinstance(m, str) or not m or len(m) > 200
                   or '://' in m or 'cloud' in m.lower() for m in chat.models)):
        raise ValueError("chat.models must list local Ollama model names.")
    for value in (voice.model, voice.voices, chat.models_dir, chat.executable, transcription.model):
        if not isinstance(value, str):
            raise ValueError("Model and executable paths must be text.")
    if transcription.language not in ("en", "hi", "auto"):
        raise ValueError("transcription.language must be en, hi, or auto.")
    folder = data_dir if data_dir is not None else raw.get("data_dir", "runtime")
    if not isinstance(folder, (str, Path)):
        raise ValueError("data_dir must be a path.")
    folder = Path(folder).expanduser()
    if not folder.is_absolute():
        folder = path.parent / folder
    return Config(path.parent, folder.resolve(), server,
                  replace(chat, models=tuple(chat.models)), voice, jobs, transcription, laptop)
