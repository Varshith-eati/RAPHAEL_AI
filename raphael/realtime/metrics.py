"""Bounded, content-free monotonic performance measurements."""
from collections import defaultdict, deque
import json
import logging
from logging.handlers import RotatingFileHandler
import math
from pathlib import Path
import statistics
import threading
import time

STAGES = frozenset({'input_to_first_text', 'input_to_first_audio', 'input_to_complete',
    'vad_endpoint', 'transcription', 'memory', 'prompt', 'model_first_token',
    'model_total', 'tts_startup', 'tool', 'queue_wait'})

class Performance:
    def __init__(self, folder: Path, enabled=False):
        self.enabled = enabled
        self._values = defaultdict(lambda: deque(maxlen=500))
        self._lock = threading.Lock()
        self._handler = None
        self.folder = folder

    def record(self, stage, seconds, kind='local'):
        if stage not in STAGES or kind not in ('local', 'browser', 'desktop'):
            return
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 3600:
            return
        with self._lock:
            self._values[stage].append(float(seconds))
            if self.enabled:
                if self._handler is None:
                    self.folder.mkdir(parents=True, exist_ok=True)
                    self._handler = RotatingFileHandler(self.folder / 'performance.jsonl', maxBytes=512000, backupCount=2, encoding='utf-8')
                # Only allowlisted labels, numeric timings and a monotonic timestamp.
                data = json.dumps({'stage': stage, 'seconds': round(seconds, 6), 'kind': kind,
                                   'monotonic': round(time.perf_counter(), 6)})
                self._handler.emit(logging.LogRecord('performance', logging.INFO, '', 0, data, (), None))

    def report(self):
        with self._lock:
            output = {}
            for stage, data in self._values.items():
                values = sorted(data)
                point = .95 * (len(values) - 1)
                index = int(point)
                p95 = values[index] + (values[min(index + 1, len(values) - 1)] - values[index]) * (point - index)
                output[stage] = {'count': len(values), 'mean': statistics.mean(values),
                    'median': statistics.median(values), 'p95': p95, 'max': values[-1]}
            return {'units': 'seconds', 'samples_per_stage_limit': 500, 'stages': output}

    def close(self):
        with self._lock:
            if self._handler:
                self._handler.close()
                self._handler = None
