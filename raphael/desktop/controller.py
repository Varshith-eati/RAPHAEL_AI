"""Qt session owner. Engine work stays in existing bounded background workers."""
from collections import deque
import difflib
import logging
import queue
import re
import threading
import time
from ..user_apps import open_browser
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from ..errors import AppError
from ..realtime.settings import validate
from ..realtime.streaming import SpeechBuffer
from .audio import Microphone, Speaker, Endpoint
from .orb import Orb, State
from .windows import set_startup, startup_snapshot, restore_startup, hotkey_filter

LOG = logging.getLogger('raphael.desktop')

def wake_command(text, sensitivity=.65):
    prefix = r'^(?:hey|hi|hello)[,\s]+(?:raphael|rafael|rafaelle|raphel)\b[,.!\s]*'
    if sensitivity >= .85: prefix = r'^(?:(?:hey|hi|hello)[,\s]+)?(?:raphael|rafael|rafaelle|raphel)\b[,.!\s]*'
    match = re.match(prefix, text.strip(), re.I)
    return text.strip()[match.end():].strip() if match else None

def interruption(text, spoken):
    """Only named interruptions are accepted during output; discard matching echo."""
    clean = re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()
    echo = re.sub(r'[^a-z0-9 ]', '', spoken.lower())
    if clean and (clean in echo or difflib.SequenceMatcher(None, clean, echo[-len(clean):]).ratio() > .9): return None
    match = re.match(r'^(?:(?:hey|hi)\s+)?(?:raphael|rafael)[,\s]+(?:stop|wait|pause)\b[,.!\s]*', text.strip(), re.I)
    return text.strip()[match.end():].strip() if match else None

class Controller(QObject):
    action = Signal(str)
    settings_changed = Signal(dict)
    def __init__(self, app, server, entry, *, open_ui=True, config_path=None):
        super().__init__()
        self.app, self.server, self.entry = app, server, entry
        self.config_path = config_path or entry.with_name('config.toml')
        app.desktop = self
        self.settings_lock = threading.RLock()
        self.options = app.settings.get()
        self.closing = False
        self.history = []
        self.request_messages = None
        self.mode = 'idle'
        self.paused = False
        self.chat_job = self.stt_job = None
        self.stt_mode = None
        self.speech_jobs = deque()
        self.phrases = deque()
        self.chat_done = False
        self.reply = ''
        self.buffer = SpeechBuffer()
        self.turn_started = 0.
        self.first_audio = False
        self.first_text = False
        self.input_completed = None
        self.deadline = 0.
        self.awaiting_microphone = False
        self.listening_window = self.options['hide_timeout']
        self.mic_retry_at = 0.
        self.mic_failures = 0
        self.last_tick = time.monotonic()
        self.web_seen = 0.
        self.text_active = False
        self.mic, self.speaker = Microphone(), Speaker()
        self.endpoint = Endpoint(self.options['vad_sensitivity'], self.options['silence_seconds'])
        self.orb = Orb(self.options)
        self.orb.moved.connect(lambda x, y: self.change_settings({'orb_x': x, 'orb_y': y}))
        self.action.connect(self.handle_action)
        self.settings_changed.connect(self.apply_settings)
        icon = QPixmap(64,64); icon.fill(Qt.transparent)
        painter = QPainter(icon); painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor('#35d9ec')); painter.setPen(QColor('#d3fbff')); painter.drawEllipse(10,10,44,44); painter.end()
        self.idle_icon = QIcon(icon)
        mic_icon = icon.copy(); painter = QPainter(mic_icon); painter.setBrush(QColor('#ffab79')); painter.setPen(Qt.NoPen); painter.drawEllipse(44,44,18,18); painter.end()
        self.mic_icon = QIcon(mic_icon); self.mic_visible = False
        self.tray = QSystemTrayIcon(self.idle_icon, self)
        menu = QMenu()
        for label, action in [('Open Raphael','open'),('Activate Raphael','activate'),('Dismiss · Ctrl+Alt+Esc','dismiss'),('Mute microphone · Ctrl+Alt+M','mute')]:
            menu.addAction(label, lambda checked=False, action=action: self.handle_action(action))
        self.pause_action = menu.addAction('Pause listening', self.toggle_pause)
        self.wake_action = QAction('Enable “Hey Raphael”', self); self.wake_action.setCheckable(True)
        self.wake_action.triggered.connect(lambda enabled: self.safe_settings({'wake_enabled': enabled}))
        menu.addAction(self.wake_action)
        self.startup_action = QAction('Start with Windows', self); self.startup_action.setCheckable(True)
        self.startup_action.triggered.connect(lambda enabled: self.safe_settings({'startup_enabled': enabled}))
        menu.addAction(self.startup_action); menu.addSeparator()
        menu.addAction('Background & Real-Time Interaction', lambda: self.handle_action('settings'))
        menu.addAction('Restart Raphael', lambda: self.handle_action('restart'))
        menu.addAction('Exit Raphael', self.exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.open_main() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        self.hotkeys = hotkey_filter(self.activate, self.dismiss, self.mute)
        QApplication.instance().installNativeEventFilter(self.hotkeys)
        self.dialog = None
        self.restart_requested = False
        self.timer = QTimer(self); self.timer.setInterval(80); self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.apply_settings(self.options)
        if open_ui: QTimer.singleShot(0, self.open_main)
        if self.options['startup_notification']: self.notice('Raphael is in the system tray. Wake listening is ' + ('on.' if self.options['wake_enabled'] else 'off.'))

    def request_action(self, action): self.action.emit(action)

    def notice(self, message):
        self.tray.showMessage('Raphael', message, QSystemTrayIcon.Information, 5000)

    def change_settings(self, changes):
        with self.settings_lock:
            old = self.app.settings.get()
            if changes.get('startup_enabled') is True and not old['startup_enabled']:
                changes = {**changes,'wake_enabled':True,'background_enabled':True,'launch_minimized':True}
            proposed = validate({**old, **changes})
            for key in ('preferred_model','fast_model','advanced_model'):
                if proposed[key] and proposed[key] not in self.app.config.chat.models:
                    raise AppError('Choose a model listed in config.toml.')
            startup_changed = proposed['startup_enabled'] != old['startup_enabled']
            snapshot = startup_snapshot() if startup_changed else None
            try:
                if startup_changed: set_startup(proposed['startup_enabled'], self.entry, self.config_path)
                result = self.app.settings.update(changes)
            except BaseException:
                if startup_changed: restore_startup(snapshot)
                raise
            self.app.performance.enabled = result['diagnostics']
        self.settings_changed.emit(result)
        return result

    def safe_settings(self, changes):
        try: self.change_settings(changes)
        except Exception as error:
            LOG.warning('settings_failed exception=%s', type(error).__name__)
            self.notice('Could not save that setting. Check the application folder permissions.')
            self.apply_settings(self.options)

    def apply_settings(self, options):
        old = self.options
        self.options = options
        self.wake_action.setChecked(options['wake_enabled'])
        self.startup_action.setChecked(options['startup_enabled'])
        self.orb.apply(options)
        self.endpoint.sensitivity = options['vad_sensitivity']; self.endpoint.silence = options['silence_seconds']
        if old['microphone'] != options['microphone']: self.mic.close(); self.mic_failures = 0
        if not options['wake_enabled'] and self.mode == 'idle': self.mic.close(); self.cancel_stt()
        if options['wake_enabled']: self.app.jobs.ensure('transcription')
        if not self.hotkeys.register(options['hotkey']): self.notice('A global shortcut is already in use. Tray controls remain available; choose another shortcut in Settings.')
        self.sync_capture()

    def handle_action(self, action):
        if self.closing: return
        if action == 'open': self.open_main()
        elif action == 'activate': self.activate()
        elif action == 'dismiss': self.dismiss()
        elif action == 'mute': self.mute()
        elif action == 'exit': self.exit()
        elif action == 'restart': self.restart_requested = True; self.exit()
        elif action == 'settings':
            from .settings_dialog import SettingsDialog
            if self.dialog: self.dialog.close()
            self.dialog = SettingsDialog(self); self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()
        elif action == 'web_heartbeat': self.web_seen = time.monotonic()
        elif action == 'web_closed': self.web_seen = time.monotonic() - 26
        elif action == 'text_start':
            self.text_active = True
            if self.mode == 'idle' and self.options['orb_for_text']: self.orb.transition(State.THINKING, 'Replying in your conversation')
        elif action == 'text_end':
            self.text_active = False
            if self.mode == 'idle': self.orb.transition(State.DEACTIVATING)

    def open_main(self):
        for kind in ('chat','voice','transcription'): self.app.jobs.ensure(kind)
        open_browser(f'http://127.0.0.1:{self.server.server_port}/#session={self.server.token}')

    def cancel_stt(self):
        if self.stt_job: self.app.jobs.cancel(self.stt_job)
        self.stt_job = self.stt_mode = None

    def cancel_turn(self):
        if self.mode == 'replying' and not self.chat_done and self.request_messages:
            self.history = list(self.request_messages)
            if self.reply:
                self.history.append({'role':'assistant','content':('[Interrupted response; incomplete] ' + self.reply)[:6000]})
            self.history = self.history[-24:]
        self.request_messages = None
        if self.chat_job: self.app.jobs.cancel(self.chat_job)
        self.chat_job = None
        for key in self.speech_jobs: self.app.jobs.cancel(key)
        self.speech_jobs.clear(); self.phrases.clear(); self.speaker.close()
        self.cancel_stt(); self.endpoint.reset(); self.mic.clear()
        self.chat_done = False
        self.reply = ''

    def activate(self):
        self.cancel_turn(); self.paused = False; self.mic_failures = 0
        self.mic_retry_at = 0.
        self.pause_action.setText('Pause listening')
        for kind in ('chat','voice','transcription'): self.app.jobs.ensure(kind)
        self.begin_listening(self.options['hide_timeout'])
        self.sync_capture()

    def begin_listening(self, seconds):
        # Loading a local model must not consume the user's listening window.
        self.mode = 'listening'; self.awaiting_microphone = True
        self.listening_window = seconds
        self.deadline = time.monotonic() + self.app.config.jobs.deadline_seconds
        self.orb.transition(State.ACTIVATING, 'Preparing microphone')

    def dismiss(self):
        self.cancel_turn(); self.mode = 'idle'; self.awaiting_microphone = False
        self.orb.transition(State.DEACTIVATING); self.sync_capture()

    def mute(self):
        self.paused = True; self.dismiss(); self.mic.close()
        self.pause_action.setText('Resume listening')
        self.notice('Microphone muted. Use Activate Raphael or Resume listening when ready.')

    def toggle_pause(self):
        if not self.paused: self.mute()
        else:
            self.paused = False; self.mic_failures = 0
            self.pause_action.setText('Pause listening'); self.sync_capture()

    def sync_capture(self):
        if self.closing: return
        want = not self.paused and not self.stt_job and (
            self.mode == 'listening' or (self.mode == 'idle' and self.options['wake_enabled']) or
            (self.mode == 'replying' and self.options['barge_in']))
        health = self.app.jobs.health()['transcription']['state']
        if want and health == 'sleeping': self.app.jobs.ensure('transcription')
        if want and health == 'ready' and self.mic.stream is None and time.monotonic() >= self.mic_retry_at and self.mic_failures < 3:
            try: self.mic.start(self.options['microphone'])
            except Exception as error:
                self.mic_failures += 1; self.mic_retry_at = time.monotonic() + 2 ** self.mic_failures
                LOG.warning('microphone_failed attempt=%d exception=%s', self.mic_failures, type(error).__name__)
                self.notice('Microphone unavailable. Check Windows microphone access and the selected device. Automatic retries are limited to three; Activate retries again.')
        elif not want and self.mic.stream is not None: self.mic.close(); self.endpoint.reset()
        if self.mode == 'listening' and self.awaiting_microphone and self.mic.stream is not None:
            self.awaiting_microphone = False
            self.deadline = time.monotonic() + self.listening_window
            self.orb.transition(State.LISTENING, 'Microphone on · listening')
        if self.paused: status = 'Paused · microphone off'
        elif self.mic.stream: status = 'Wake monitoring · microphone on' if self.mode == 'idle' else 'Microphone on · ' + self.mode
        else: status = 'Microphone off · ' + self.mode
        self.tray.setToolTip('Raphael · ' + status)
        active = self.mic.stream is not None
        if active != self.mic_visible:
            self.mic_visible = active; self.tray.setIcon(self.mic_icon if active else self.idle_icon)

    def receive_transcript(self, text, mode):
        text = text.strip()
        if not text: return
        if mode == 'idle':
            command = wake_command(text, self.options['wake_sensitivity'])
            if command is None: return
            self.activate()
            if command: self.send(command, self.input_completed)
        elif mode == 'replying':
            command = interruption(text, self.reply)
            if command is not None:
                self.activate()
                if command: self.send(command, self.input_completed)
        elif re.fullmatch(r'(?:go to sleep|goodbye|stop|dismiss)[.!\s]*', text, re.I): self.dismiss()
        else:
            command = wake_command(text, self.options['wake_sensitivity'])
            self.send(command if command is not None and command else text, self.input_completed)

    def send(self, text, input_completed=None):
        self.cancel_turn()
        self.mode = 'replying'; self.turn_started = input_completed or time.perf_counter()
        self.first_audio = self.first_text = False
        self.buffer = SpeechBuffer(); self.pending_user = text
        messages = self.history + [{'role':'user','content':text}]
        while len(messages) > 24 or sum(len(m['content']) for m in messages) > 8000:
            if len(messages) < 3: break
            messages = messages[2:]
        self.request_messages = messages
        self.orb.transition(State.THINKING, 'Thinking')
        self.app.jobs.ensure('chat'); self.app.jobs.ensure('voice')
        self.deadline = time.monotonic() + self.app.config.jobs.deadline_seconds
        self.sync_capture()

    def process_reply(self):
        health = self.app.jobs.health()
        if health['chat']['state'] == 'error': raise AppError(health['chat']['error'])
        if not self.chat_job and not self.chat_done and health['chat']['state'] == 'ready':
            self.chat_job = self.app.submit_chat({'model':'auto','messages':self.request_messages})
        if self.chat_job:
            status = self.app.jobs.snapshot(self.chat_job)
            if status['state'] in ('error','cancelled'): raise AppError(status['error'] or 'Reply stopped.')
            self.reply = status['text']
            if self.reply and not self.first_text:
                self.first_text = True
                self.app.performance.record('input_to_first_text', time.perf_counter() - self.turn_started, 'desktop')
            if self.options['speech_streaming']:
                self.phrases.extend(self.buffer.feed(self.reply, status['state'] == 'ready'))
            if status['state'] == 'ready':
                self.chat_job = None; self.chat_done = True
                if not self.options['speech_streaming']: self.phrases.extend(self.buffer.feed(self.reply, True))
                self.history = (self.request_messages + [{'role':'assistant','content':self.reply}])[-24:]
                if status['details'].get('approvals'):
                    self.dismiss(); self.notice('An action needs your approval. Review it in Laptop access.'); self.open_main(); return
        if self.phrases and health['voice']['state'] == 'error': raise AppError('Voice is unavailable. Open Raphael to continue with text.')
        while self.phrases and len(self.speech_jobs) < 2 and health['voice']['state'] == 'ready':
            key = self.app.submit_speech({'text': self.phrases[0], 'voice':self.options['voice'], 'speed':self.options['speed']})
            self.phrases.popleft(); self.speech_jobs.append(key)
        if self.speech_jobs and len(self.speaker.parts) < 2:
            status = self.app.jobs.snapshot(self.speech_jobs[0])
            if status['state'] in ('error','cancelled'): raise AppError(status['error'] or 'Speech stopped.')
            if status['state'] == 'ready':
                self.speaker.enqueue(self.app.jobs.audio(self.speech_jobs.popleft()), self.options['volume'])
        if self.speaker.first_at is not None and not self.first_audio:
            self.first_audio = True
            self.app.performance.record('input_to_first_audio', self.speaker.first_at - self.turn_started, 'desktop')
        if self.speaker.pending:
            self.orb.transition(State.SPEAKING, 'Speaking · Ctrl+Alt+Esc to stop')
            self.orb.level = self.speaker.level
        elif not self.chat_done: self.orb.transition(State.THINKING, 'Thinking')
        if self.chat_done and not self.phrases and not self.speech_jobs and not self.speaker.pending:
            self.app.performance.record('input_to_complete', time.perf_counter() - self.turn_started, 'desktop')
            self.speaker.close(); self.endpoint.reset(); self.mic.clear()
            self.begin_listening(self.options['followup_seconds'])
            self.sync_capture()
            if not self.awaiting_microphone: self.orb.transition(State.LISTENING, 'Microphone on · anything else?')

    def tick(self):
        if self.closing: return
        now = time.monotonic()
        try:
            if now - self.last_tick > 15:
                # Sleep/resume: never replay stale audio or continue an old recording.
                self.mic.close(); self.dismiss(); self.mic_failures = 0
            self.last_tick = now
            if self.web_seen and now - self.web_seen > 45 and not self.options['background_enabled']:
                self.exit(); return
            if self.mic.stream and (not self.mic.stream.active or now - self.mic.last_frame > 3):
                self.mic.close(); self.endpoint.reset(); self.mic_failures += 1
                self.mic_retry_at = now + 2 ** min(self.mic_failures, 3)
                self.notice('Microphone disconnected. Raphael will retry up to three times.')
            if self.mic.dropped:
                self.mic.clear(); self.endpoint.reset(); self.mic.dropped = False
            for _ in range(64):
                try: frame = self.mic.frames.get_nowait()
                except queue.Empty: break
                level, audio, delay = self.endpoint.feed(frame)
                if self.mode == 'listening':
                    self.orb.level = min(1., level * 9)
                    self.orb.transition(State.LISTENING, 'Microphone on · listening')
                    if self.endpoint.parts: self.deadline = now + self.options['followup_seconds']
                if audio and self.stt_job is None:
                    self.input_completed = time.perf_counter() - delay
                    self.app.performance.record('vad_endpoint', delay, 'desktop')
                    self.stt_mode = self.mode
                    self.stt_job = self.app.submit_transcription(audio, self.options['input_language'])
                    self.mic.close()
                    if self.mode == 'listening': self.orb.transition(State.THINKING, 'Understanding your voice')
                    break
            if self.stt_job:
                status = self.app.jobs.snapshot(self.stt_job)
                if status['state'] in ('ready','error','cancelled'):
                    mode = self.stt_mode; self.stt_job = self.stt_mode = None
                    if status['state'] == 'ready': self.receive_transcript(status['text'], mode)
                    elif mode != 'idle': self.notice('Recognition could not finish. Please try again.')
                    self.endpoint.reset()
                    if self.mode == 'listening': self.deadline = now + self.options['followup_seconds']
            if self.mode == 'replying':
                if now > self.deadline: raise AppError('The reply timed out. Activate Raphael to try again.')
                self.process_reply()
            elif self.mode == 'listening':
                if self.app.jobs.health()['transcription']['state'] == 'error':
                    raise AppError('Voice recognition is unavailable. Open Raphael to continue with text.')
                if self.mic_failures >= 3 and self.mic.stream is None:
                    raise AppError('Microphone unavailable. Choose a microphone in tray settings, then activate Raphael again.')
                if now > self.deadline and not self.stt_job: self.dismiss()
            self.sync_capture()
            self.timer.setInterval(80 if self.mode != 'idle' else 160 if self.options['wake_enabled'] and not self.paused else 1000)
        except Exception as error:
            LOG.warning('session_failed exception=%s', type(error).__name__)
            self.dismiss(); self.notice(str(error) if isinstance(error, AppError) else 'The voice session stopped. Check the audio device or open Raphael for text chat.')

    def exit(self):
        if self.closing: return
        self.closing = True; self.timer.stop(); self.cancel_turn(); self.mic.close()
        self.orb.transition(State.HIDDEN); self.hotkeys.close(); self.tray.hide()
        if self.dialog: self.dialog.close()
        QApplication.instance().quit()
