"""Bounded in-memory audio. PortAudio callbacks do no inference, disk IO or UI work."""
from collections import deque
import io
import math
import queue
import time
import wave

RATE = 16000

class Endpoint:
    def __init__(self, sensitivity=.55, silence=.9):
        self.sensitivity, self.silence = sensitivity, silence
        self.noise = .002
        self.reset()

    def reset(self):
        self.pre = deque(maxlen=10)
        self.parts, self.duration, self.quiet, self.voiced = [], 0., 0., 0.

    def feed(self, frame):
        import numpy as np
        level = float(np.sqrt(np.mean(frame * frame)))
        duration = len(frame) / RATE
        threshold = max(.004 + (1 - self.sensitivity) * .016, self.noise * 2.7)
        speech = level > threshold
        if not self.parts and not speech: self.noise = .98 * self.noise + .02 * min(level, .025)
        if speech:
            if not self.parts: self.parts = list(self.pre); self.duration = sum(len(p) for p in self.parts) / RATE
            self.voiced += duration
            self.quiet = 0.
        elif self.parts: self.quiet += duration
        if self.parts or speech:
            self.parts.append(frame)
            self.duration += duration
        else: self.pre.append(frame)
        # A short utterance gets extra pause tolerance; all recordings have a hard cap.
        endpoint = self.silence + (.15 if self.voiced < .8 else 0)
        if self.parts and (self.quiet >= endpoint or self.duration >= 30):
            parts, voiced, delay = self.parts, self.voiced, self.quiet
            self.reset()
            if voiced < .18: return level, None, delay
            pcm = np.clip(np.concatenate(parts)[:RATE * 30], -1, 1)
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE)
                wav.writeframes((pcm * 32767).astype('<i2').tobytes())
            return level, output.getvalue(), delay
        return level, None, 0.

class Microphone:
    def __init__(self):
        self.frames = queue.Queue(maxsize=64)
        self.stream = None
        self.dropped = False
        self.last_frame = 0.

    def start(self, device=''):
        import sounddevice as sd
        if self.stream: return
        self.dropped = False
        def callback(data, frames, timing, status):
            self.last_frame = time.monotonic()
            if status: self.dropped = True
            try: self.frames.put_nowait(data[:, 0].copy())
            except queue.Full: self.dropped = True
        stream = sd.InputStream(samplerate=RATE, channels=1, dtype='float32', blocksize=480,
                                device=device or None, callback=callback)
        try: stream.start()
        except BaseException: stream.close(); raise
        self.stream = stream
        self.last_frame = time.monotonic()

    def close(self):
        if self.stream:
            stream, self.stream = self.stream, None
            try: stream.abort()
            except Exception: pass
            try: stream.close()
            except Exception: pass
        self.clear()

    def clear(self):
        while True:
            try: self.frames.get_nowait()
            except queue.Empty: break

class Speaker:
    def __init__(self):
        self.stream = None
        self.parts = deque()
        self.offset = 0
        self.level = 0.
        self.played = False
        self.first_at = None
        self.last_activity = time.monotonic()

    def enqueue(self, audio, volume=.65):
        import numpy as np
        import sounddevice as sd
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            if wav.getsampwidth() != 2 or wav.getnchannels() != 1: raise ValueError('Unsupported speech format')
            rate = wav.getframerate()
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype('float32') * (volume / 32768)
        if len(pcm) > rate * 180 or len(self.parts) >= 3: raise ValueError('Speech buffer limit reached')
        if self.stream is None:
            def callback(output, frames, timing, status):
                output.fill(0)
                used = 0
                while self.parts and used < frames:
                    piece = self.parts[0]
                    count = min(frames - used, len(piece) - self.offset)
                    output[used:used + count, 0] = piece[self.offset:self.offset + count]
                    self.offset += count; used += count
                    if self.offset >= len(piece): self.parts.popleft(); self.offset = 0
                self.level = min(1., float(np.sqrt(np.mean(output * output))) * 5)
                if used:
                    self.played = True
                    self.last_activity = time.monotonic()
                    if self.first_at is None: self.first_at = time.perf_counter()
            self.stream = sd.OutputStream(samplerate=rate, channels=1, dtype='float32', blocksize=960, callback=callback)
            try: self.stream.start()
            except BaseException: self.close(); raise
        elif int(self.stream.samplerate) != rate: raise ValueError('Speech sample rate changed')
        self.parts.append(pcm)

    @property
    def pending(self): return bool(self.parts) or (self.played and time.monotonic() - self.last_activity < .15)

    def close(self):
        if self.stream:
            stream, self.stream = self.stream, None
            try: stream.abort()
            except Exception: pass
            try: stream.close()
            except Exception: pass
        self.parts.clear(); self.offset = 0; self.level = 0.; self.played = False; self.first_at = None

def microphones():
    import sounddevice as sd
    return list(dict.fromkeys(item['name'] for item in sd.query_devices() if item['max_input_channels'] > 0))
