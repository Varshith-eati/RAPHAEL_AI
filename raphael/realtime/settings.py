"""Validated, atomic per-installation settings shared by the web and desktop UI."""
from dataclasses import dataclass, asdict, fields
import json
import math
import os
from pathlib import Path
import tempfile
import threading

from ..errors import AppError

@dataclass(frozen=True)
class InteractionSettings:
    background_enabled: bool = True
    launch_minimized: bool = False
    startup_enabled: bool = False
    startup_notification: bool = False
    crash_recovery: bool = True
    startup_delay: int = 15
    wake_enabled: bool = False
    wake_sensitivity: float = 0.65
    vad_sensitivity: float = 0.55
    silence_seconds: float = 0.9
    followup_seconds: int = 8
    barge_in: bool = False
    microphone: str = ''
    speech_streaming: bool = True
    voice: str = 'heart'
    speed: float = 1.0
    volume: float = 0.65
    input_language: str = 'en'
    orb_enabled: bool = True
    orb_size: int = 240
    orb_x: int = -1
    orb_y: int = -1
    orb_glow: float = 0.7
    animation_quality: str = 'balanced'
    audio_reactive: bool = True
    hide_timeout: int = 30
    orb_for_text: bool = False
    reduced_motion: bool = False
    draggable_orb: bool = False
    response_streaming: bool = True
    fast_conversation: bool = True
    model_routing: bool = False
    preferred_model: str = ''
    fast_model: str = 'llama3.2:latest'
    advanced_model: str = 'qwen3.5:4b'
    memory_limit: int = 12
    low_resource: bool = False
    diagnostics: bool = False
    hotkey: str = 'Ctrl+Alt+R'

LIMITS = {'startup_delay': (0, 120), 'wake_sensitivity': (0, 1), 'vad_sensitivity': (0, 1),
    'silence_seconds': (.4, 2.5), 'followup_seconds': (3, 30), 'orb_size': (120, 480),
    'orb_x': (-32768, 32768), 'orb_y': (-32768, 32768), 'orb_glow': (0, 1),
    'hide_timeout': (10, 120), 'memory_limit': (0, 12), 'speed': (.8, 1.2), 'volume': (0, 1)}
OPTIONS = {'animation_quality': ('low', 'balanced', 'high'), 'voice': ('heart', 'bella', 'sarah'),
           'input_language': ('en', 'hi', 'auto'),
           'hotkey': ('Ctrl+Alt+R', 'Ctrl+Shift+R', 'Ctrl+Alt+Space')}

def validate(values):
    defaults = asdict(InteractionSettings())
    if not isinstance(values, dict) or set(values) - set(defaults):
        raise AppError('Unknown background or interaction setting.')
    merged = {**defaults, **values}
    for key, default in defaults.items():
        value = merged[key]
        if type(default) is bool:
            valid = type(value) is bool
        elif type(default) is int:
            valid = type(value) is int and LIMITS[key][0] <= value <= LIMITS[key][1]
        elif type(default) is float:
            valid = type(value) in (float, int) and math.isfinite(value) and LIMITS[key][0] <= value <= LIMITS[key][1]
        else:
            valid = isinstance(value, str) and len(value) <= 200 and '\0' not in value
            if key in OPTIONS: valid = valid and value in OPTIONS[key]
            if key.endswith('_model'): valid = valid and '://' not in value and 'cloud' not in value.lower()
        if not valid: raise AppError('Invalid value for ' + key.replace('_', ' ') + '.')
    return merged

class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._values = asdict(InteractionSettings())
        if path.exists():
            if path.stat().st_size > 32000: raise ValueError('Interaction settings file is too large.')
            self._values = validate(json.loads(path.read_text(encoding='utf-8')))

    def get(self):
        with self._lock: return dict(self._values)

    def update(self, changes):
        with self._lock:
            if not isinstance(changes, dict): raise AppError('Settings must be an object.')
            proposed = validate({**self._values, **changes})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                                 prefix='.settings-', delete=False) as target:
                    temporary = Path(target.name)
                    json.dump(proposed, target, indent=2)
                    target.flush(); os.fsync(target.fileno())
                os.replace(temporary, self.path)
                temporary = None
            finally:
                if temporary is not None: temporary.unlink(missing_ok=True)
            self._values = proposed
            return dict(proposed)

def route_model(requested, messages, installed, settings):
    """Opt-in, local keyword routing. Explicit user choices always win."""
    if requested and requested != 'auto': return requested
    preferred = settings['preferred_model']
    if preferred and preferred != 'auto': return preferred
    if not settings['model_routing']: return next(iter(installed), '')
    if not isinstance(messages, list) or any(not isinstance(m, dict) or not isinstance(m.get('content'), str) for m in messages):
        raise AppError('Messages must contain text.')
    text = messages[-1].get('content', '').lower() if messages else ''
    complex_terms = ('code', 'debug', 'program', 'algorithm', 'research', 'compare', 'tradeoff',
                     'trade-off', 'analy', 'reason', 'prove', 'plan', 'architecture', 'complex')
    complex_task = len(text) > 300 or any(term in text for term in complex_terms)
    chosen = settings['advanced_model' if complex_task else 'fast_model']
    if chosen not in installed:
        raise AppError('The selected routing model is not installed. Choose an installed model in settings.')
    return chosen
