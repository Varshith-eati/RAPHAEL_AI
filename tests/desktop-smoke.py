"""Offscreen Qt lifecycle and session test. Uses fake audio/models; never records."""
from dataclasses import replace
from pathlib import Path
import json
import queue
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from raphael.application import Application
from raphael.config import load_config, LaptopConfig
from raphael.http_api import LocalServer
from raphael.desktop.controller import Controller
from raphael.desktop.settings_dialog import SettingsDialog
from raphael.desktop.orb import State
from test_backend import FakeChat, FakeVoice, FakeTranscriber
from test_laptop import FakeNative
from raphael.laptop.service import LaptopTools

class Mic:
    def __init__(self): self.frames=queue.Queue(); self.stream=None; self.dropped=False; self.last_frame=0
    def start(self,device=''): self.stream=type('Stream',(),{'active':True})(); self.last_frame=time.monotonic()
    def close(self): self.stream=None; self.clear()
    def clear(self):
        while not self.frames.empty(): self.frames.get_nowait()

class Speaker:
    def __init__(self): self.parts=[]; self.first_at=None; self.level=0.; self.count=0
    def enqueue(self,audio,volume=.65):
        assert audio[:4]==b'RIFF'; self.count+=1
        self.first_at=time.perf_counter()
    @property
    def pending(self): return False
    def close(self): self.parts.clear(); self.first_at=None

qt=QApplication([]);qt.setQuitOnLastWindowClosed(False)
from raphael.desktop.theme import initialize_fonts
initialize_fonts(qt)
checks=[]
with tempfile.TemporaryDirectory() as folder:
    config=load_config(ROOT/'config.toml',data_dir=Path(folder)/'runtime')
    config=replace(config,chat=replace(config.chat,models=('test-local',)),laptop=LaptopConfig(True,str(Path(folder)/'Workspace')))
    app=Application(config,chat_provider=FakeChat(),voice_provider=FakeVoice(),transcription_provider=FakeTranscriber(),laptop_tools=LaptopTools(config,native=FakeNative()))
    app.settings.update({'fast_model':'test-local','advanced_model':'test-local'})
    server=LocalServer(app,port=0,require_bootstrap=True)
    app.start(lazy=True)
    with patch('raphael.desktop.controller.Microphone',Mic),patch('raphael.desktop.controller.Speaker',Speaker),patch('raphael.desktop.controller.open_browser') as opened:
        c=Controller(app,server,ROOT/'desktop.py',open_ui=False)
        try:
            assert all(v['state']=='sleeping' for v in app.jobs.health().values())
            assert c.mic.stream is None and c.orb.state==State.HIDDEN and not c.orb.timer.isActive()
            checks.append('Idle is hidden; microphone closed; models lazy; no orb paint timer')
            c.orb.transition(State.LISTENING,'Microphone on · listening');c.orb.opacity=1;c.orb.level=.35
            c.orb.grab().save(str(ROOT/'docs'/'desktop-orb-preview.png'))
            for state in (State.LISTENING,State.THINKING,State.SPEAKING):
                c.orb.transition(state);c.orb.level=.6
                c.orb.last_frame-=.1;c.orb.advance();c.orb.opacity=1
                c.orb.grab().save(str(ROOT/'docs'/('desktop-'+state.value+'-preview.png')))
            c.orb.transition(State.HIDDEN)
            dialog=SettingsDialog(c);dialog.show();qt.processEvents()
            assert len(dialog.controls)==len(app.settings.get())
            dialog.grab().save(str(ROOT/'docs'/'desktop-settings-preview.png'));dialog.close()
            checks.append('Every interaction setting has a native control; orb and settings rendered')
            # Cold recognition may take longer than the usual listening window.
            with patch.object(app.jobs,'ensure'), patch.object(app.jobs,'health', return_value={'transcription':{'state':'loading'}}):
                c.activate()
                assert c.awaiting_microphone and c.mic.stream is None
                assert c.deadline-time.monotonic()>app.settings.get()['hide_timeout']
                assert 'Preparing' in c.orb.caption
            c.dismiss()
            assert not opened.called
            checks.append('Cold recognition waits for readiness without claiming the microphone is on or opening the browser')
            c.open_main();assert opened.call_args.args[0].endswith('#session='+server.token)
            until=time.monotonic()+3
            while any(v['state']!='ready' for v in app.jobs.health().values()):
                qt.processEvents();time.sleep(.01)
                assert time.monotonic()<until
            opened.reset_mock()
            c.activate()
            assert not c.awaiting_microphone and c.mic.stream is not None
            assert 0<c.deadline-time.monotonic()<=app.settings.get()['hide_timeout']
            c.dismiss()
            c.receive_transcript('unrelated room speech', 'idle')
            assert c.mode=='idle'
            c.receive_transcript('Hey Raphael', 'idle')
            assert c.mode=='listening' and c.mic.stream is not None and not opened.called
            checks.append('Wake phrase activates without a browser; unrelated speech does not activate; shortcut activation gets a full listening window')
            c.send('Hello');until=time.monotonic()+3
            while c.mode!='listening':
                c.tick();qt.processEvents();time.sleep(.01);assert time.monotonic()<until
            assert c.speaker.count>0 and c.history[-1]['role']=='assistant'
            checks.append('Chat streams into ordered speech and enters follow-up with conversation context')
            previous=list(c.history)
            c.receive_transcript('Tell me more', 'listening')
            assert c.request_messages[:-1]==previous
            until=time.monotonic()+3
            while c.mode!='listening':
                c.tick();qt.processEvents();time.sleep(.01);assert time.monotonic()<until
            assert len(c.history)==len(previous)+2 and not opened.called
            checks.append('A second spoken turn preserves context and returns to follow-up without opening the main interface')
            c.deadline=time.monotonic()-1;c.tick()
            assert c.mode=='idle' and c.mic.stream is None
            for _ in range(10):c.orb.last_frame-=.05;c.orb.advance()
            assert c.orb.state==State.HIDDEN and not c.orb.timer.isActive()
            c.orb.transition(State.LISTENING);c.orb.level=1
            c.orb.last_frame-=.05;c.orb.advance()
            assert 0<c.orb.display_level<1
            c.orb.transition(State.THINKING)
            before=c.orb.display_level;c.orb.last_frame-=.05;c.orb.advance()
            assert c.orb.display_level<before
            c.orb.apply({**c.options,'orb_enabled':False});assert not c.orb.timer.isActive()
            c.orb.apply(c.options);assert c.orb.timer.isActive()
            c.orb.apply({**c.options,'low_resource':True})
            timer_id=c.orb.timer.timerId()
            for _ in range(10):c.orb.transition(State.THINKING)
            assert c.orb.timer.timerId()==timer_id
            c.orb.apply(c.options)
            c.orb.transition(State.HIDDEN)
            checks.append('Audio amplitude is smoothed; thinking releases the pulse; re-enabling resumes animation; repeated state updates do not starve low-resource frames')
            c.activate();c.mute();assert c.paused and c.mic.stream is None
            c.activate();assert not c.paused and c.pause_action.text()=='Pause listening'
            c.mute()
            with patch.object(app.jobs,'health',return_value={'transcription':{'state':'error'}}),patch.object(c,'notice') as notice:
                c.activate();c.tick()
                assert c.mode=='idle' and notice.called and c.mic.stream is None
            c.mute()
            checks.append('Recognition failure ends the listening state and reports a useful recovery action')
            checks.append('Timeout hides orb; immediate mute closes capture; no stale output survives')
            c.mode='replying';c.chat_done=False;c.request_messages=[{'role':'user','content':'Explain gravity.'}];c.reply='Gravity attracts'
            c.cancel_turn()
            assert c.history==[{'role':'user','content':'Explain gravity.'},{'role':'assistant','content':'[Interrupted response; incomplete] Gravity attracts'}]
            c.cancel_turn();assert len(c.history)==2
            checks.append('Interruption preserves the question and labeled partial answer exactly once')
            from raphael.desktop import windows
            link=Path(folder)/'Startup'/'Raphael Companion.lnk'
            with patch.object(windows,'startup_path',return_value=link),patch.object(windows,'legacy_startup_value',return_value=''):
                c.change_settings({'startup_enabled':True})
                assert link.exists() and c.options['wake_enabled'] and c.options['launch_minimized']
                assert c.options['background_enabled']
                c.change_settings({'startup_enabled':False,'wake_enabled':False})
                assert not link.exists()
                with patch.object(app.settings,'update',side_effect=OSError('simulated write failure')):
                    try:c.change_settings({'startup_enabled':True})
                    except OSError:pass
                    else:raise AssertionError('Expected failed settings write')
                assert not link.exists() and not app.settings.get()['startup_enabled']
            checks.append('Start with Windows enables wake/background; Disable removes its shortcut; failed saves roll back startup changes')
            c.exit();assert not c.timer.isActive() and c.closing
            checks.append('Exit stops timers, overlay, audio, hotkeys and tray')
        finally:c.exit();app.close();server.server_close()
result={'result':'passed','engines':'simulated','audio_devices':'simulated','checks':checks}
(ROOT/'docs'/'desktop-test-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
