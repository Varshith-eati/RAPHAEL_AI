"""Bounded background work with one owner per engine and race-safe terminal states."""
from collections import deque
from dataclasses import dataclass, field
import logging
import threading
import time
import uuid

from ..contracts import Cancellation
from ..errors import AppError, Cancelled

LOG = logging.getLogger("raphael.jobs")
TERMINAL = {"ready", "error", "cancelled"}


@dataclass
class Job:
    kind: str
    request: object
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cancel: Cancellation = field(default_factory=Cancellation)
    state: str = "queued"
    text: str = ""
    error: str | None = None
    code: str | None = None
    details: dict = field(default_factory=dict)
    audio: bytes | None = None
    created: float = field(default_factory=time.monotonic)
    finished: float | None = None
    started: float | None = None
    first_delta: float | None = None


class JobManager:
    def __init__(self, services, config, performance=None):
        self.services = services
        self.config = config
        self.performance = performance
        self._jobs = {}
        self._queues = {kind: deque() for kind in services}
        self._health = {kind: {"state": "loading", "error": None} for kind in services}
        self._condition = threading.Condition(threading.RLock())
        self._stopping = threading.Event()
        self._threads = []
        self._launched = set()

    def start(self, lazy=False):
        for kind in self.services:
            if lazy:
                self._health[kind] = {'state': 'sleeping', 'error': None}
            else:
                self.ensure(kind)
        monitor = threading.Thread(target=self._monitor, name='raphael-cleanup', daemon=True)
        self._threads.append(monitor)
        monitor.start()

    def ensure(self, kind):
        with self._condition:
            if kind in self._launched or self._stopping.is_set(): return
            self._launched.add(kind)
            self._health[kind] = {'state': 'loading', 'error': None}
            thread = threading.Thread(target=self._worker, args=(kind,), name=f'raphael-{kind}', daemon=True)
            self._threads.append(thread)
            thread.start()

    def health(self):
        with self._condition:
            return {kind: dict(value) for kind, value in self._health.items()}

    def _finish(self, job, state, error=None, code=None):
        job.state, job.error, job.code = state, error, code
        job.finished, job.request = time.monotonic(), None
        if self.performance and state == 'ready':
            stage = {'chat': 'model_total', 'voice': 'tts_startup', 'transcription': 'transcription'}[job.kind]
            self.performance.record(stage, job.finished - job.created)

    def _prune(self):
        now = time.monotonic()
        for key, job in list(self._jobs.items()):
            if job.finished is not None and now - job.finished >= self.config.retention_seconds:
                del self._jobs[key]

    def submit(self, kind, request):
        with self._condition:
            if self._stopping.is_set():
                raise AppError("Raphael is shutting down.", 503, "stopping")
            health = self._health[kind]
            if health['state'] == 'sleeping':
                self.ensure(kind)
            if health["state"] != "ready":
                raise AppError(health["error"] or f"The local {kind} engine is still loading.",
                               503, "engine_unavailable")
            self._prune()
            queue = self._queues[kind]
            if len(queue) >= self.config.queue_size:
                raise AppError("Raphael is busy. Stop a pending request and try again.", 429, "queue_full")
            if len(self._jobs) >= self.config.max_records:
                old = next((key for key, job in self._jobs.items() if job.state in TERMINAL), None)
                if old is None:
                    raise AppError("Too many requests. Stop the current reply first.", 429, "jobs_full")
                del self._jobs[old]
            job = Job(kind, request)
            self._jobs[job.id] = job
            queue.append(job.id)
            self._condition.notify_all()
            return job.id

    def _find(self, key):
        job = self._jobs.get(key)
        if job is None:
            raise AppError("This request has expired.", 404, "job_missing")
        return job

    def snapshot(self, key):
        with self._condition:
            job = self._find(key)
            result = {"id": key, "kind": job.kind, "state": job.state, "text": job.text,
                      "error": job.error, "code": job.code, "details": dict(job.details)}
            if job.kind == "voice" and job.state == "ready":
                result["audio"] = f"/api/audio/{key}"
            return result

    def audio(self, key):
        with self._condition:
            job = self._find(key)
            if job.state != "ready" or not job.audio:
                raise AppError("Audio unavailable.", 404, "audio_missing")
            return job.audio

    def cancel(self, key):
        with self._condition:
            job = self._jobs.get(key)
            if job is None:
                return
            if job.state in TERMINAL:
                return
            self._finish(job, "cancelled")
            job.audio = None
            if key in self._queues[job.kind]:
                self._queues[job.kind].remove(key)
        job.cancel.cancel()

    def _worker(self, kind):
        service = self.services[kind]
        try:
            service.start()
            with self._condition:
                self._health[kind] = {"state": "ready", "error": None}
            LOG.info("engine_ready kind=%s", kind)
        except Exception as error:
            message = str(error) if isinstance(error, AppError) else (
                f"The local {kind} engine could not start. Check runtime/raphael.log and restart.")
            with self._condition:
                self._health[kind] = {"state": "error", "error": message}
            # Do not log arbitrary exception messages: a provider may embed prompt text.
            LOG.error("engine_failed kind=%s exception=%s", kind, type(error).__name__)
            return
        while not self._stopping.is_set():
            with self._condition:
                self._condition.wait_for(lambda: self._queues[kind] or self._stopping.is_set())
                if self._stopping.is_set():
                    return
                job = self._jobs[self._queues[kind].popleft()]
                if job.state != "queued":
                    continue
                job.state = "generating"
                job.started = time.monotonic()
                if self.performance:
                    self.performance.record('queue_wait', job.started - job.created)
                request = job.request

            def delta(text):
                with self._condition:
                    if job.state == "generating":
                        if len(job.text) + len(text) > 20000:
                            raise AppError("The reply exceeded its size limit. Ask a shorter question.",
                                           502, "reply_too_large")
                        job.text += text
                        if text and job.first_delta is None:
                            job.first_delta = time.monotonic()
                            if self.performance and kind == 'chat':
                                self.performance.record('model_first_token', job.first_delta - job.created)
            def progress(label):
                with self._condition:
                    if job.state == 'generating': job.details['progress'] = label
            delta.progress = progress
            try:
                job.cancel.check()
                result = service.execute(request, job.cancel, delta)
                with self._condition:
                    if job.state == "generating":
                        if kind == "chat" and not job.text.strip():
                            raise AppError("The model returned no answer. Try the other local model.",
                                           502, "empty_reply")
                        if kind == "voice" and (not result.audio or len(result.audio) > 16000000):
                            raise AppError("Speech was empty or too long. Try a shorter passage.",
                                           502, "invalid_audio")
                        job.details, job.audio = dict(result.details), result.audio
                        self._finish(job, "ready")
                LOG.info("job_finished kind=%s id=%s state=%s", kind, job.id, job.state)
            except Cancelled:
                with self._condition:
                    if job.state not in TERMINAL:
                        self._finish(job, "cancelled")
            except Exception as error:
                with self._condition:
                    if job.state not in TERMINAL:
                        message = str(error) if isinstance(error, AppError) else "This request failed. Please retry."
                        code = error.code if isinstance(error, AppError) else "provider_failed"
                        self._finish(job, "error", message, code)
                LOG.warning("job_failed kind=%s id=%s exception=%s", kind, job.id, type(error).__name__)
            finally:
                # Do not retain the last recording while this worker waits for another job.
                request = None

    def _monitor(self):
        while not self._stopping.wait(0.25):
            cancelled = []
            with self._condition:
                for job in list(self._jobs.values()):
                    if job.state not in TERMINAL and time.monotonic() - job.created > self.config.deadline_seconds:
                        self._finish(job, "error", "This request took too long. Please try a shorter request.", "timeout")
                        if job.id in self._queues[job.kind]:
                            self._queues[job.kind].remove(job.id)
                        cancelled.append(job.cancel)
                self._prune()
            for cancel in cancelled:
                cancel.cancel()

    def close(self):
        self._stopping.set()
        with self._condition:
            keys = list(self._jobs)
            self._condition.notify_all()
        for key in keys:
            self.cancel(key)
        for service in self.services.values():
            try:
                service.close()
            except Exception as error:
                LOG.warning("close_failed exception=%s", type(error).__name__)
        for thread in self._threads:
            thread.join(timeout=5)
        with self._condition:
            self._jobs.clear()
