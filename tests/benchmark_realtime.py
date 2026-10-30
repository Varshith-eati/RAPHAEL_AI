"""Equivalent local workloads; never logs prompts, replies, or raw audio."""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import statistics
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('phase', choices=['baseline', 'optimized'])
parser.add_argument('--repeats', type=int, default=3)
parser.add_argument('--baseline-source', type=Path, default=Path(__file__).resolve().parents[2] / 'raphael-modular-before-realtime-2026-10-29')
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
app_root = args.baseline_source if args.phase == 'baseline' else root
if not (app_root / 'raphael').is_dir(): raise SystemExit('Baseline source is missing; provide --baseline-source.')
sys.path.insert(0, str(app_root))
from raphael.config import load_config
from raphael.application import Application
from raphael.errors import AppError

import tempfile
qa = Path(tempfile.mkdtemp(prefix='raphael-latency-' + args.phase + '-'))
qa.mkdir(exist_ok=True)
(qa / 'Workspace').mkdir(exist_ok=True)
config = load_config(root / 'config.toml', port=8897, data_dir=qa / 'runtime')
config = replace(config, chat=replace(config.chat, port=11461, max_reply_tokens=360),
    transcription=replace(config.transcription, model=str(root / 'models/whisper-base')),
    laptop=replace(config.laptop, workspace=str(qa / 'Workspace')))
app = Application(config)
class NoNativeActions:
    def system_info(self): raise AppError('Native actions are unavailable in this benchmark.')
    def open_app(self, *_): raise AppError('Native actions are unavailable in this benchmark.')
    def open_text(self, *_): raise AppError('Native actions are unavailable in this benchmark.')
app.laptop.native = NoNativeActions()
workloads = [
    ('simple', 'What is two plus two? Answer in one short sentence without using tools.'),
    ('normal', 'Give two practical tips for staying focused while studying. Use two short sentences, without tools.'),
    ('reasoning', 'Explain when iteration is preferable to recursion and one tradeoff. Use two short sentences, without tools.'),
]
results = []
def done(key):
    value = app.jobs.snapshot(key)
    if value['state'] in ('error', 'cancelled'):
        raise RuntimeError(value['code'] or value['state'])
    return value

try:
    app.start()
    deadline = time.monotonic() + 100
    while not all(app.status()[kind] == 'ready' for kind in ('chat', 'voice', 'transcription')):
        if time.monotonic() > deadline: raise RuntimeError('Engine startup timeout')
        time.sleep(.25)
    print('Benchmark engines ready.', flush=True)
    for category, prompt in workloads:
        for repeat in range(args.repeats):
            started = time.perf_counter()
            key = app.submit_chat({'model': 'llama3.2:latest', 'messages': [{'role': 'user', 'content': prompt}]})
            first = None
            failed = None
            streaming = args.phase == 'optimized'
            if streaming:
                from raphael.realtime.streaming import SpeechBuffer
                buffer = SpeechBuffer()
            chunks, speech_jobs = [], []
            first_audio = speech_started = generation = None
            cache_hits = []
            chat_complete = False
            while True:
                try: status = done(key)
                except RuntimeError as error:
                    failed = str(error)
                    break
                if status['text'] and first is None: first = time.perf_counter() - started
                if streaming:
                    if not chat_complete:
                        chunks.extend(buffer.feed(status['text'], status['state'] == 'ready'))
                    if status['state'] == 'ready' and not chat_complete:
                        generation = time.perf_counter() - started
                        chat_complete = True
                    while chunks and len(speech_jobs) < 2:
                        if speech_started is None: speech_started = time.perf_counter()
                        speech_jobs.append(app.submit_speech({'text':chunks.pop(0), 'voice':'heart','speed':1.0}))
                    if speech_jobs:
                        speech_status = done(speech_jobs[0])
                        if speech_status['state'] == 'ready':
                            if first_audio is None: first_audio = time.perf_counter() - started
                            cache_hits.append(bool(speech_status['details'].get('cached', False)))
                            speech_jobs.pop(0)
                    if chat_complete and not chunks and not speech_jobs: break
                elif status['state'] == 'ready': break
                if time.perf_counter() - started > 180: raise RuntimeError('Chat timeout')
                time.sleep(.01)
            if failed:
                record = {'category': category, 'repeat': repeat + 1, 'error': failed,
                          'elapsed_seconds': round(time.perf_counter() - started, 4)}
                results.append(record)
                print(json.dumps(record), flush=True)
                (qa / 'samples.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
                continue
            if generation is None: generation = time.perf_counter() - started
            assert not status['details'].get('tools_used'), 'Unexpected tool request'
            if not streaming:
                speech_started = time.perf_counter()
                speech = app.submit_speech({'text': status['text'], 'voice': 'heart', 'speed': 1.0})
                while done(speech)['state'] != 'ready':
                    if time.perf_counter() - speech_started > 180: raise RuntimeError('Speech timeout')
                    time.sleep(.01)
                first_audio = time.perf_counter() - started
                cache_hits = [bool(done(speech)['details'].get('cached', False))]
            record = {'category': category, 'repeat': repeat + 1, 'cold_model': not results,
                      'first_text_seconds': round(first, 4), 'generation_seconds': round(generation, 4),
                      'first_audio_available_seconds': round(first_audio, 4),
                      'speech_generation_seconds': round(time.perf_counter() - speech_started, 4),
                      'first_voice_cache_hit': cache_hits[0] if cache_hits else None, 'voice_cache_hit': all(cache_hits), 'speech_chunks':len(cache_hits),
                      'reply_characters': len(status['text'])}
            results.append(record)
            print(json.dumps(record), flush=True)
            (qa / 'samples.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
finally:
    app.close()

def summarize(values):
    if not values: return {'count': 0}
    values = sorted(values)
    position = .95 * (len(values) - 1)
    left = int(position)
    p95 = values[left] + (values[min(left + 1, len(values) - 1)] - values[left]) * (position - left)
    return {'count': len(values), 'mean': statistics.mean(values), 'median': statistics.median(values),
            'p95': p95, 'max': max(values)}
summary = {'phase': args.phase, 'model': 'llama3.2:latest', 'max_reply_tokens': 360,
           'note': 'Audio availability is measured, not physical speaker onset. Small sample; P95 is descriptive only.',
           'samples': results, 'summary': {category: {metric: summarize([row[metric] for row in results if row['category'] == category and metric in row])
           for metric in ('first_text_seconds', 'generation_seconds', 'first_audio_available_seconds', 'speech_generation_seconds')}
           for category, _ in workloads}}
(root / 'docs' / ('latency-' + args.phase + '.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
print('Benchmark report saved.', flush=True)

