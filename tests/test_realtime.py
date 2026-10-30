"""Streaming, routing, bounded audio, privacy and cancellation regression tests."""
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from raphael.contracts import Cancellation, ChatRequest, Message, Profile, Result
from raphael.errors import AppError
from raphael.realtime.streaming import partial_reply, SpeechBuffer
from raphael.realtime.settings import InteractionSettings, SettingsStore, validate, route_model
from raphael.realtime.metrics import Performance
from raphael.realtime.routing import plain_conversation
from raphael.services.chat import ChatService
from raphael.storage import ProfileStore
import test_backend as fixtures

class StreamingTests(unittest.TestCase):
    def test_unicode_and_escape_prefixes_never_retract_or_leak_json(self):
        answer = 'Hello "friend". नमस्ते 🌙\nHow are you?'
        encoded = json.dumps({'action':'reply','arguments':{},'reply':answer})
        previous = ''
        for index in range(len(encoded) + 1):
            current = partial_reply(encoded[:index])
            self.assertTrue(current.startswith(previous), (index, current, previous))
            self.assertTrue(answer.startswith(current))
            previous = current
        self.assertEqual(previous, answer)

    def test_tools_and_reordered_action_do_not_stream(self):
        for source in ('{"action":"write_text","arguments":{"content":"secret"},"reply":"done"}',
                       '{"reply":"premature","action":"reply","arguments":{}}',
                       '{"action":"reply","action":"open_app","reply":"bad"}'):
            self.assertEqual(partial_reply(source), '')

    def test_sentence_buffer_no_duplicates_and_first_phrase_is_short(self):
        text = 'Dr. Smith recommends taking regular breaks while studying a difficult topic. Try a short walk afterward.'
        buffer = SpeechBuffer(); pieces = []
        for i in range(1, len(text) + 1): pieces.extend(buffer.feed(text[:i]))
        pieces.extend(buffer.feed(text, True))
        self.assertEqual(' '.join(pieces), text)
        self.assertLessEqual(len(pieces[0]), 72)
        self.assertNotEqual(pieces[0], 'Dr.')
        self.assertEqual(buffer.feed(text, True), [])

    def test_complete_word_and_total_limit(self):
        buffer = SpeechBuffer(first_limit=12, later_limit=20, maximum=100)
        self.assertEqual(buffer.feed('extraordinarily'), [])
        self.assertEqual(buffer.feed('extraordinarily long '), ['extraordinarily'])
        pieces = buffer.feed('extraordinarily long ' + 'word ' * 40, True)
        self.assertLessEqual(buffer.emitted, 100)
        self.assertTrue(pieces)

    def test_service_publishes_before_provider_finishes(self):
        release, published = threading.Event(), threading.Event()
        class Provider:
            def tool_turn(self, *args): raise AssertionError('Buffered path used')
            def tool_turn_stream(self, request, messages, cancel, schemas, context, publish):
                publish('Early text. '); published.set()
                if not release.wait(2): raise AssertionError('No consumer observed streaming')
                publish('Finished.')
                return {'content':'Early text. Finished.'}, {}
        class Laptop:
            enabled = True
            approvals = type('Approvals', (), {'cancel':lambda self, ids: None})()
            def context(self): return ''
        output = []
        thread = threading.Thread(target=lambda: ChatService(Provider(), Laptop()).execute(
            ChatRequest('test', (Message('user','hello'),), Profile()), Cancellation(), output.append))
        thread.start(); self.assertTrue(published.wait(1)); self.assertTrue(thread.is_alive())
        self.assertEqual(output, ['Early text. ']); release.set(); thread.join(2)
        self.assertEqual(''.join(output), 'Early text. Finished.')

class SettingsTests(unittest.TestCase):
    def test_privacy_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'settings.json'; store = SettingsStore(path)
            self.assertFalse(store.get()['wake_enabled']); self.assertFalse(store.get()['startup_enabled'])
            store.update({'barge_in':True, 'followup_seconds':10})
            self.assertEqual(SettingsStore(path).get()['followup_seconds'], 10)
            for values in ({'followup_seconds':True},{'orb_glow':float('nan')},{'silence_seconds':0}, {'unknown':1}):
                with self.assertRaises(AppError): store.update(values)
            self.assertEqual(SettingsStore(path).get()['followup_seconds'], 10)

    def test_explicit_model_wins_and_missing_advanced_is_not_downgraded(self):
        values = asdict(InteractionSettings()); values['model_routing'] = True
        installed = ['llama3.2:latest','qwen3.5:4b']
        self.assertEqual(route_model('auto', [{'content':'Hello'}], installed, values), installed[0])
        self.assertEqual(route_model('auto', [{'content':'Debug this algorithm'}], installed, values), installed[1])
        self.assertEqual(route_model(installed[0], [{'content':'Debug this algorithm'}], installed, values), installed[0])
        with self.assertRaises(AppError): route_model('auto',[{'content':'complex reasoning'}],installed[:1],values)
        with self.assertRaises(AppError): route_model('auto',[{'content':[]}],installed,values)

    def test_local_requests_keep_tools_and_normal_questions_use_fast_path(self):
        for value in ('Open Gmail','What is my CPU?', 'Explain the files in my workspace', 'Give my notes to me', 'read C:\\work\\a.txt'):
            self.assertFalse(plain_conversation([Message('user',value)]))
        for value in ('Hello', 'What is two plus two?', 'Explain quantum computing', 'Give two tips for studying'):
            self.assertTrue(plain_conversation([Message('user',value)]))
        self.assertFalse(plain_conversation([Message('user','Read my file'),Message('user','Explain it')]))

    def test_cached_preferences_observe_external_updates_and_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'prefs.db'; first, second = ProfileStore(path), ProfileStore(path)
            try:
                self.assertEqual(first.get(), Profile())
                second.save(Profile('Name', ('Use short replies',)))
                self.assertEqual(first.get().name, 'Name')
                first.save(Profile()); self.assertEqual(second.get(), Profile())
            finally: first.close(); second.close()

    def test_metrics_are_bounded_and_content_free(self):
        with tempfile.TemporaryDirectory() as folder:
            perf = Performance(Path(folder), True)
            for i in range(510): perf.record('memory', i/1000)
            perf.record('PRIVATE PROMPT', 1); perf.record('memory', float('nan')); perf.close()
            self.assertEqual(perf.report()['stages']['memory']['count'], 500)
            data = (Path(folder)/'performance.jsonl').read_text()
            self.assertNotIn('PRIVATE', data)
            self.assertEqual(set(json.loads(data.splitlines()[0])), {'stage','seconds','kind','monotonic'})

class InteractionHTTPTests(unittest.TestCase):
    # Reuse the existing isolated fake-engine fixture without duplicating its test methods.
    setUp = fixtures.HTTPTests.setUp
    tearDown = fixtures.HTTPTests.tearDown
    request = fixtures.HTTPTests.request
    def test_desktop_bootstrap_is_required(self):
        self.server.require_bootstrap = True
        self.assertEqual(self.request('/api/status', headers={'X-Raphael-Token':''})[0], 403)
        self.assertEqual(self.request('/api/status')[0], 200)

    def test_settings_and_metrics(self):
        self.assertEqual(self.request('/api/interaction', {'barge_in':True})[0], 200)
        self.assertTrue(self.request('/api/interaction')[1]['barge_in'])
        self.assertEqual(self.request('/api/interaction', {'wake_enabled':True})[0], 400)
        self.assertEqual(self.request('/api/performance', {'stage':'memory','seconds':.02,'kind':'browser'})[0], 200)
        self.assertEqual(self.request('/api/performance', {'stage':'memory','seconds':True,'kind':'browser'})[0], 400)

class EndpointTests(unittest.TestCase):
    def test_audio_endpoint_noise_pause_and_30_second_bound(self):
        import numpy as np
        from raphael.desktop.audio import Endpoint
        from raphael.validation import transcription_request
        detector = Endpoint(silence=.6)
        quiet, speech = np.zeros(480,dtype='float32'), np.full(480,.1,dtype='float32')
        for _ in range(300): self.assertIsNone(detector.feed(quiet)[1])
        self.assertLessEqual(len(detector.pre),10)
        for _ in range(25): detector.feed(speech)
        result = None
        for _ in range(30):
            level, audio, delay = detector.feed(quiet)
            if audio: result = audio
        self.assertIsNotNone(result); transcription_request(result,'en')
        for _ in range(1100):
            _, audio, _ = detector.feed(speech)
            if audio:
                transcription_request(audio,'en'); break
        else: self.fail('Continuous speech was not bounded')

    def test_named_interruption_ignores_echo(self):
        from raphael.desktop.controller import interruption, wake_command
        self.assertEqual(interruption('Raphael, stop. Tell me something else.', 'To solve this problem'), 'Tell me something else.')
        self.assertIsNone(interruption('Raphael stop', 'Say Raphael stop to interrupt'))
        self.assertIsNone(wake_command('I was discussing Raphael'))
        self.assertEqual(wake_command('Hey Raphael, explain light.'), 'explain light.')

if __name__ == '__main__': unittest.main()
