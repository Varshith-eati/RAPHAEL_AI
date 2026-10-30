"""Resource-probe child: real local Whisper, generated silence, no device capture."""
from pathlib import Path
import json
import os
import queue
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer
from raphael.desktop import controller
import desktop

class SilentMicrophone:
    def __init__(self):
        self.frames=queue.Queue(maxsize=64);self.stream=None;self.dropped=False;self.last_frame=0
        self.timer=QTimer();self.timer.setInterval(30);self.timer.timeout.connect(self.feed)
    def feed(self):
        import numpy as np
        self.last_frame=time.monotonic()
        try:self.frames.put_nowait(np.zeros(480,dtype='float32'))
        except queue.Full:self.dropped=True
    def start(self,device=''):
        self.stream=type('Stream',(),{'active':True})();self.last_frame=time.monotonic();self.timer.start()
    def clear(self):
        while not self.frames.empty():self.frames.get_nowait()
    def close(self):self.timer.stop();self.stream=None;self.clear()

Original=controller.Controller
class ProbeController(Original):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.probe=QTimer(self);self.probe.setInterval(500);self.probe.timeout.connect(self.record);self.probe.start()
        QTimer.singleShot(60000,self.exit)
    def record(self):
        health=self.app.jobs.health()
        if health['transcription']['state']=='ready' and self.mic.stream:
            (self.app.config.data_dir/'idle-probe.json').write_text(json.dumps({
                'pid':os.getpid(),'engines':health,'orb':self.orb.state.value,'paint_timer':self.orb.timer.isActive(),
                'capture':'generated silence','job_count':len(self.app.jobs._jobs),'poll_ms':self.timer.interval()}),encoding='utf-8')
        elif health['transcription']['state']=='error':
            (self.app.config.data_dir/'idle-probe.json').write_text(json.dumps({'error':health['transcription']['error']}),encoding='utf-8')

controller.Microphone=SilentMicrophone
controller.Controller=ProbeController
raise SystemExit(desktop.main())
