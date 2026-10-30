"""Behavior tests with fake inference. No model downloads or voice SDK required."""
from dataclasses import replace
from pathlib import Path
import http.client
import io
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave
import weakref

from raphael.application import Application
from raphael.config import Config, ServerConfig, ChatConfig, VoiceConfig, JobsConfig, load_config
from raphael.contracts import Cancellation, ChatRequest, Message, Profile, Result, SpeechRequest
from raphael.errors import AppError, Cancelled
from raphael.http_api import LocalServer
from raphael.providers.kokoro import speech_chunks
from raphael.providers.ollama import OllamaProvider
from raphael.services.jobs import JobManager
from raphael.services.voice import VoiceService
from raphael.storage import ProfileStore
from raphael.validation import chat_request, profile_request, speech_request, transcription_request

ROOT = Path(__file__).resolve().parents[1]


def until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for test condition")


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\0\0" * 240)
    return buffer.getvalue()


class FakeChat:
    models = ["test-local"]

    def start(self):
        pass

    def generate(self, request, cancel, on_delta):
        cancel.check()
        on_delta("Hello ")
        on_delta(request.profile.name or "there")
        return Result({"model": request.model})

    def close(self):
        pass


class FakeVoice:
    voices = {"heart": {"name": "Test voice"}}

    def __init__(self, broken=False):
        self.broken = broken
        self.calls = 0

    def start(self):
        if self.broken:
            raise RuntimeError("PRIVATE_PROVIDER_DATA")

    def synthesize(self, request, cancel):
        self.calls += 1
        cancel.check()
        return Result({"voice": request.voice}, wav_bytes())

    def close(self):
        pass


class FakeTranscriber:
    def start(self):
        pass

    def transcribe(self, request, cancel, on_delta):
        cancel.check()
        on_delta("What is two plus three?")
        return Result({"language": request.language})

    def close(self):
        pass


def microphone_wav(frames=16000, rate=16000, channels=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\0\0" * frames * channels)
    return buffer.getvalue()


class ValidationTests(unittest.TestCase):
    def test_microphone_accepts_only_bounded_complete_pcm_recordings(self):
        self.assertEqual(len(transcription_request(microphone_wav(), "en").pcm), 32000)
        for audio in (b"not a WAV", microphone_wav(frames=100), microphone_wav(frames=480001),
                      microphone_wav(rate=24000), microphone_wav(channels=2), microphone_wav()[:-20]):
            with self.subTest(size=len(audio)), self.assertRaises(AppError):
                transcription_request(audio, "en")
        with self.assertRaises(AppError):
            transcription_request(microphone_wav(), "unsupported")

    def test_untrusted_roles_and_content_are_rejected(self):
        for role in ([], {}, "system", None, 2):
            with self.subTest(role=role), self.assertRaises(AppError):
                chat_request({"model": "local", "messages": [{"role": role, "content": "hi"}]}, ["local"], Profile())

    def test_context_budget_and_last_role(self):
        for messages in ([{"role": "user", "content": "x" * 6000}] * 4,
                         [{"role": "assistant", "content": "hello"}],
                         [{"role": "user", "content": "x" * 6001}], []):
            with self.assertRaises(AppError):
                chat_request({"model": "local", "messages": messages}, ["local"], Profile())

    def test_saved_profile_default_and_ephemeral_override(self):
        payload = {"model": "local", "messages": [{"role": "user", "content": "Hello"}]}
        saved = Profile("A", ("Short answers",))
        self.assertEqual(chat_request(payload, ["local"], saved).profile, saved)
        payload["profile"] = {"name": "B", "notes": []}
        self.assertEqual(chat_request(payload, ["local"], saved).profile.name, "B")

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(AppError):
            chat_request({"model": "other:cloud", "messages": [{"role": "user", "content": "hi"}]}, ["local"], Profile())

    def test_voice_numeric_edges(self):
        for speed in (True, None, float("nan"), float("inf"), 0.7, 1.3, "1"):
            with self.subTest(speed=speed), self.assertRaises(AppError):
                speech_request({"text": "hello", "speed": speed}, {"heart"})
        self.assertEqual(speech_request({"text": "hello", "speed": 0.8}, {"heart"}).speed, 0.8)

    def test_profile_limits_and_whitespace(self):
        self.assertEqual(profile_request({"name": " A ", "notes": [" concise "]}), Profile("A", ("concise",)))
        for payload in ({"notes": ["x"] * 13}, {"notes": [""]}, {"name": "x" * 61}, {"notes": [3]}, []):
            with self.assertRaises(AppError):
                profile_request(payload)

    def test_speech_cleanup_keeps_identifiers_and_abbreviations(self):
        self.assertEqual(speech_chunks("Use snake_case_names here."), ["Use snake case names here."])
        self.assertEqual(speech_chunks("Dr. Smith went home. Fine."), ["Dr. Smith went home.", "Fine."])
        self.assertEqual(speech_chunks("This is _important_ and **bold**."), ["This is important and bold."])
        self.assertEqual(speech_chunks("Ask dr. Smith. Next."), ["Ask dr. Smith.", "Next."])
        self.assertEqual(speech_chunks("Use e.g. an example. Fine."), ["Use e.g. an example.", "Fine."])
        self.assertEqual(speech_chunks("An eXg. Next."), ["An eXg.", "Next."])

    def test_speech_markup_and_long_words_are_bounded(self):
        chunks = speech_chunks("```print('private code')``` [link](https://example.com) " + "A" * 900)
        self.assertTrue(all(len(chunk) <= 220 for chunk in chunks))
        self.assertNotIn("private code", " ".join(chunks))
        self.assertNotIn("https://", " ".join(chunks))


class ConfigurationAndStorageTests(unittest.TestCase):
    def test_startup_deadline_counts_probe_and_wait_time(self):
        config = load_config(ROOT / "config.toml")
        provider = OllamaProvider(config)
        provider._process = Mock()
        provider._process.poll.return_value = None
        clock, timeouts = [0.0], []
        def probe(path, timeout):
            timeouts.append(timeout)
            clock[0] += timeout
            raise OSError("Simulated slow probe")
        def wait(seconds):
            clock[0] += seconds
            return False
        with patch("raphael.providers.ollama.time.monotonic", side_effect=lambda: clock[0]), \
                patch.object(provider, "_get", side_effect=probe), \
                patch.object(provider._stopping, "wait", side_effect=wait):
            with self.assertRaises(AppError) as error:
                provider._wait_until_ready(2.0)
        self.assertEqual(error.exception.code, "model_start_timeout")
        self.assertEqual(clock[0], 2.0)
        self.assertEqual(timeouts, [1.0, 0.5])

    def test_startup_returns_when_ready_without_an_extra_wait(self):
        provider = OllamaProvider(load_config(ROOT / "config.toml"))
        provider._process = Mock()
        provider._process.poll.return_value = None
        with patch("raphael.providers.ollama.time.monotonic", return_value=0), \
                patch.object(provider, "_get", return_value={"version": "test"}), \
                patch.object(provider._stopping, "wait") as wait:
            provider._wait_until_ready(60)
            wait.assert_not_called()

    def test_startup_detects_a_stopped_model_process(self):
        provider = OllamaProvider(load_config(ROOT / "config.toml"))
        provider._process = Mock()
        provider._process.poll.return_value = 1
        with self.assertRaises(AppError) as error:
            provider._wait_until_ready(time.monotonic() + 60)
        self.assertEqual(error.exception.code, "model_start_failed")

    def test_failed_migration_rolls_back_schema(self):
        import sqlite3
        connect = sqlite3.connect
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql.startswith("CREATE TABLE notes"):
                    raise sqlite3.OperationalError("Simulated disk error")
                return super().execute(sql, *args)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prefs.db"
            with patch("raphael.storage.sqlite3.connect", side_effect=lambda *a, **kw: connect(*a, **kw, factory=FailingConnection)):
                with self.assertRaises(sqlite3.OperationalError):
                    ProfileStore(path)
            db = connect(path)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])
            db.close()
            self.assertEqual(ProfileStore(path).get(), Profile())

    def test_close_during_initial_probe_never_starts_an_orphan_process(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Config(ROOT, Path(folder), ServerConfig(), ChatConfig(), VoiceConfig(), JobsConfig())
            provider = OllamaProvider(config)
            entered, release = threading.Event(), threading.Event()
            def probe(*args, **kwargs):
                entered.set()
                release.wait(2)
                raise OSError("Service absent")
            with patch.object(provider, "_get", side_effect=probe), patch("raphael.providers.ollama.subprocess.Popen") as process:
                thread = threading.Thread(target=provider.start)
                thread.start()
                self.assertTrue(entered.wait(2))
                provider.close()
                release.set()
                thread.join(2)
                self.assertFalse(thread.is_alive())
                process.assert_not_called()

    def test_configuration_paths_and_typos(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            path.write_text('data_dir="data"\n[server]\nport=9000\n')
            config = load_config(path)
            self.assertEqual(config.data_dir, Path(folder) / "data")
            self.assertEqual(config.server.port, 9000)
            for text in ('[server]\nprot=9000', '[server]\nport=true', '[chat]\nmodels=["test:cloud"]',
                         '[jobs]\nqueue_size=0', '[chat]\ntemperature=nan', '[server]\nport=11436',
                         '[chat]\nstartup_timeout_seconds=0'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_preferences_persist_and_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.sqlite3"
            profile = Profile("Robert'); DROP TABLE notes;--", ("Unicode: नमस्ते", "Use short replies"))
            ProfileStore(path).save(profile)
            self.assertEqual(ProfileStore(path).get(), profile)
            ProfileStore(path).save(Profile())
            self.assertEqual(ProfileStore(path).get(), Profile())

    def test_readers_never_see_half_a_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProfileStore(Path(folder) / "prefs.db")
            a, b = Profile("A", ("A",)), Profile("B", ("B",))
            store.save(a)
            def writer():
                for i in range(30):
                    store.save(a if i % 2 else b)
            thread = threading.Thread(target=writer)
            thread.start()
            for _ in range(30):
                self.assertIn(store.get(), (a, b))
            thread.join()
            store.close()

    def test_newer_database_is_not_overwritten(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prefs.db"
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA user_version=99")
            connection.close()
            with self.assertRaises(RuntimeError):
                ProfileStore(path)


class BlockingService:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def start(self):
        pass

    def execute(self, request, cancel, delta):
        self.entered.set()
        if request == "fail":
            raise RuntimeError("PRIVATE_PROMPT_TEXT")
        if request == "block":
            self.release.wait(3)
        delta("late result" if cancel.is_set() else "answer")
        self.finished.set()
        return Result({"result": "ok"})

    def close(self):
        self.release.set()


class JobTests(unittest.TestCase):
    def setUp(self):
        self.service = BlockingService()
        self.manager = JobManager({"chat": self.service}, JobsConfig(queue_size=1))
        self.manager.start()
        until(lambda: self.manager.health()["chat"]["state"] == "ready")

    def tearDown(self):
        self.manager.close()

    def test_finished_input_is_released_while_worker_is_idle(self):
        request = SpeechRequest("This input should not remain in the idle worker.")
        reference = weakref.ref(request)
        key = self.manager.submit("chat", request)
        del request
        until(lambda: self.manager.snapshot(key)["state"] == "ready")
        until(lambda: reference() is None)

    def test_queue_backpressure_and_cancelled_slot_reuse(self):
        first = self.manager.submit("chat", "block")
        self.assertTrue(self.service.entered.wait(2))
        second = self.manager.submit("chat", "queued")
        with self.assertRaises(AppError) as error:
            self.manager.submit("chat", "overflow")
        self.assertEqual(error.exception.status, 429)
        self.manager.cancel(second)
        replacement = self.manager.submit("chat", "replacement")
        self.manager.cancel(first)
        self.service.release.set()
        until(lambda: self.manager.snapshot(replacement)["state"] == "ready")
        self.assertEqual(self.manager.snapshot(second)["state"], "cancelled")

    def test_late_result_cannot_resurrect_cancelled_job(self):
        key = self.manager.submit("chat", "block")
        self.assertTrue(self.service.entered.wait(2))
        self.manager.cancel(key)
        self.service.release.set()
        self.assertTrue(self.service.finished.wait(2))
        self.assertEqual(self.manager.snapshot(key)["state"], "cancelled")
        self.assertEqual(self.manager.snapshot(key)["text"], "")
        self.manager.cancel(key)

    def test_deadline_interrupts_and_remains_error(self):
        self.manager.config = replace(self.manager.config, deadline_seconds=0.05)
        key = self.manager.submit("chat", "block")
        until(lambda: self.manager.snapshot(key)["state"] == "error")
        self.service.release.set()
        self.assertTrue(self.service.finished.wait(2))
        self.assertEqual(self.manager.snapshot(key)["code"], "timeout")
        self.assertEqual(self.manager.snapshot(key)["text"], "")

    def test_provider_failure_is_sanitized_and_next_request_works(self):
        key = self.manager.submit("chat", "fail")
        until(lambda: self.manager.snapshot(key)["state"] == "error")
        self.assertNotIn("PRIVATE", json.dumps(self.manager.snapshot(key)))
        another = self.manager.submit("chat", "ok")
        until(lambda: self.manager.snapshot(another)["state"] == "ready")

    def test_finished_jobs_expire_without_new_requests(self):
        self.manager.config = replace(self.manager.config, retention_seconds=0.05)
        key = self.manager.submit("chat", "ok")
        until(lambda: self.manager.snapshot(key)["state"] == "ready")
        def expired():
            try:
                self.manager.snapshot(key)
                return False
            except AppError:
                return True
        until(expired)

    def test_shutdown_cancels_active_and_queued_and_rejects_new(self):
        self.manager.submit("chat", "block")
        self.service.entered.wait(2)
        self.manager.submit("chat", "queued")
        self.manager.close()
        self.assertTrue(all(not thread.is_alive() for thread in self.manager._threads))
        with self.assertRaises(AppError):
            self.manager.submit("chat", "new")

    def test_cancellation_hook_registered_after_cancel_runs(self):
        cancel = Cancellation()
        calls = []
        cancel.cancel()
        cancel.register(lambda: calls.append(1))
        self.assertEqual(calls, [1])
        with self.assertRaises(Cancelled):
            cancel.check()

    def test_one_bad_interrupt_hook_does_not_block_the_others(self):
        cancel, calls = Cancellation(), []
        def broken():
            raise RuntimeError("Bad provider hook")
        cancel.register(broken)
        cancel.register(lambda: calls.append(True))
        cancel.cancel()
        self.assertEqual(calls, [True])

    def test_voice_cache_reuses_and_evicts_by_bytes(self):
        provider = FakeVoice()
        service = VoiceService(provider, len(wav_bytes()))
        a, b = SpeechRequest("A"), SpeechRequest("B")
        service.execute(a, Cancellation(), lambda _: None)
        self.assertTrue(service.execute(a, Cancellation(), lambda _: None).details["cached"])
        service.execute(b, Cancellation(), lambda _: None)
        service.execute(a, Cancellation(), lambda _: None)
        self.assertEqual(provider.calls, 3)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = Config(ROOT, Path(self.temp.name), ServerConfig(),
                        ChatConfig(models=("test-local",)), VoiceConfig(), JobsConfig())
        self.app = Application(config, chat_provider=FakeChat(), voice_provider=FakeVoice(), transcription_provider=FakeTranscriber())
        self.server = LocalServer(self.app, port=0)
        self.app.start()
        until(lambda: all(h["state"] == "ready" for h in self.app.jobs.health().values()))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02})
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.app.close()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        request_headers = {"X-Raphael-Token": self.server.token}
        if headers:
            request_headers.update(headers)
        data = raw if raw is not None else json.dumps(body) if body is not None else None
        if data is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection.request("POST" if data is not None else "GET", path, data, request_headers)
        response = connection.getresponse()
        content = response.read()
        status, mime = response.status, response.getheader("Content-Type")
        connection.close()
        return status, json.loads(content) if mime.startswith("application/json") else content

    def test_status_and_health_and_streamed_chat(self):
        status, data = self.request("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["app"], "raphael-modular")
        self.assertEqual(self.request("/api/health")[0], 200)
        status, data = self.request("/api/chat", {"model": "test-local", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(status, 202)
        key = data["id"]
        until(lambda: self.request("/api/jobs/" + key)[1]["state"] == "ready")
        self.assertEqual(self.request("/api/jobs/" + key)[1]["text"], "Hello there")

    def test_profile_is_used_and_bad_update_does_not_erase(self):
        self.assertEqual(self.request("/api/profile", {"name": "Nia", "notes": ["Concise"]})[0], 200)
        self.assertEqual(self.request("/api/profile", {"name": ["bad"]})[0], 400)
        self.assertEqual(self.request("/api/profile")[1]["name"], "Nia")
        _, data = self.request("/api/chat", {"model": "test-local", "messages": [{"role": "user", "content": "hi"}]})
        until(lambda: self.request("/api/jobs/" + data["id"])[1]["state"] == "ready")
        self.assertEqual(self.request("/api/jobs/" + data["id"])[1]["text"], "Hello Nia")

    def test_audio_round_trip(self):
        _, data = self.request("/api/speak", {"text": "hello"})
        until(lambda: self.request("/api/jobs/" + data["id"])[1]["state"] == "ready")
        status, audio = self.request("/api/audio/" + data["id"])
        self.assertEqual(status, 200)
        self.assertEqual(audio[:4], b"RIFF")

    def test_microphone_transcription_round_trip_and_boundary(self):
        headers = {"Content-Type": "audio/wav", "X-Raphael-Language": "hi"}
        status, data = self.request("/api/transcribe", raw=microphone_wav(), headers=headers)
        self.assertEqual(status, 202)
        until(lambda: self.request("/api/jobs/" + data["id"])[1]["state"] == "ready")
        result = self.request("/api/jobs/" + data["id"])[1]
        self.assertEqual(result["text"], "What is two plus three?")
        self.assertEqual(result["details"]["language"], "hi")
        self.assertEqual(self.request("/api/transcribe", raw=microphone_wav(), headers={**headers, "X-Raphael-Token": "bad"})[0], 403)
        self.assertEqual(self.request("/api/transcribe", raw=microphone_wav(), headers={**headers, "Origin": "https://other.example"})[0], 403)
        self.assertEqual(self.request("/api/transcribe", raw=microphone_wav())[0], 415)
        self.assertEqual(self.request("/api/transcribe", raw=b"invalid", headers=headers)[0], 413)
        self.assertEqual(self.request("/microphone.js")[0], 200)
        self.assertEqual(self.request("/recorder-worklet.js")[0], 200)

    def test_browser_boundary_and_token_checks(self):
        for headers in ({"Origin": "https://example.com"}, {"Host": "evil.example"},
                        {"Sec-Fetch-Site": "cross-site"}, {"X-Raphael-Token": "bad"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/profile", {}, headers)[0], 403)
        self.assertEqual(self.request("/api/profile", headers={"X-Raphael-Token": ""})[0], 403)
        self.assertEqual(self.request("/api/status", headers={"Origin": "null"})[0], 403)

    def test_malformed_inputs_are_4xx_not_500(self):
        for route, body in (("/api/chat", {"model": "test-local", "messages": [{"role": [], "content": "hi"}]}),
                            ("/api/speak", {"text": "hi", "voice": {}}), ("/api/profile", [])):
            self.assertEqual(self.request(route, body)[0], 400)
        for raw in ('{"text":', '{"speed":NaN}', '[' * 2000):
            self.assertEqual(self.request("/api/speak", raw=raw)[0], 400)
        self.assertEqual(self.request("/api/speak", raw="{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("/api/speak", raw="x" * 70001)[0], 413)

    def test_static_allowlist_does_not_expose_code_or_database(self):
        for path in ("/server.py", "/config.toml", "/runtime/preferences.sqlite3", "/../server.py", "/%2e%2e/server.py"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/original")[0], 200)

    def test_voice_failure_does_not_block_chat(self):
        config = replace(self.app.config, data_dir=Path(self.temp.name) / "degraded")
        app = Application(config, chat_provider=FakeChat(), voice_provider=FakeVoice(broken=True), transcription_provider=FakeTranscriber())
        app.start()
        try:
            until(lambda: app.status()["voice"] == "error")
            until(lambda: app.status()["chat"] == "ready")
            self.assertNotIn("PRIVATE", json.dumps(app.status()))
            key = app.submit_chat({"model": "test-local", "messages": [{"role": "user", "content": "hi"}]})
            until(lambda: app.jobs.snapshot(key)["state"] == "ready")
            with self.assertRaises(AppError) as error:
                app.submit_speech({"text": "hi"})
            self.assertEqual(error.exception.status, 503)
        finally:
            app.close()

    def test_transcription_failure_leaves_chat_and_voice_available(self):
        provider = FakeTranscriber()
        provider.start = Mock(side_effect=RuntimeError("PRIVATE_PROVIDER_DATA"))
        config = replace(self.app.config, data_dir=Path(self.temp.name) / "no-microphone")
        app = Application(config, chat_provider=FakeChat(), voice_provider=FakeVoice(), transcription_provider=provider)
        app.start()
        try:
            until(lambda: app.status()["transcription"] == "error")
            until(lambda: app.status()["chat"] == app.status()["voice"] == "ready")
            self.assertNotIn("PRIVATE", json.dumps(app.status()))
            chat = app.submit_chat({"model": "test-local", "messages": [{"role": "user", "content": "hi"}]})
            voice = app.submit_speech({"text": "hi"})
            until(lambda: app.jobs.snapshot(chat)["state"] == app.jobs.snapshot(voice)["state"] == "ready")
            with self.assertRaises(AppError) as error:
                app.submit_transcription(microphone_wav())
            self.assertEqual(error.exception.status, 503)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
