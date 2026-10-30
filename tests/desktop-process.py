"""Windows single-instance and explicit-exit smoke test; no microphone/model startup."""
from pathlib import Path
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from raphael.desktop.windows import startup_value

before=startup_value()
with tempfile.TemporaryDirectory() as folder:
    data=Path(folder)
    config=data/'config.toml'
    config.write_text('data_dir="runtime"\n[server]\nport=18981\n[chat]\nport=11462\n[laptop]\nenabled=false\nworkspace='+json.dumps(str(data/'Workspace').replace('\\','/'))+'\n',encoding='utf-8')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    arguments=[sys.executable,'-E','-s','-B',str(ROOT/'desktop.py'),'--config',str(config)]
    child=subprocess.Popen(arguments+['--background'],creationflags=flags)
    try:
        deadline=time.monotonic()+20
        while True:
            try:
                connection=http.client.HTTPConnection('127.0.0.1',18981,timeout=1)
                connection.request('GET','/api/status');response=connection.getresponse();response.read();connection.close()
                assert response.status==403,'Unauthenticated bootstrap leaked';break
            except OSError:
                assert child.poll() is None,'Desktop exited unexpectedly'
                assert time.monotonic()<deadline,'Desktop startup timed out';time.sleep(.1)
        second=subprocess.run(arguments+['--startup','--background'],creationflags=flags,timeout=8)
        assert second.returncode==0 and child.poll() is None
        second=subprocess.run(arguments+['--background'],creationflags=flags,timeout=8)
        assert second.returncode==0 and child.poll() is None
        stop=subprocess.run(arguments+['--exit'],creationflags=flags,timeout=8)
        assert stop.returncode==0
        assert child.wait(timeout=15)==0
        assert startup_value()==before,'Test altered Windows startup'
        report={'result':'passed','microphone_opened':False,'startup_registration_changed':False,'checks':[
            'Native Windows process starts hidden with lazy models',
            'Public status cannot disclose the desktop session token',
            'Second launch connects to the owner-only IPC and exits without another backend',
            'Explicit IPC Exit stops the original process without relaunch']}
        (ROOT/'docs'/'desktop-process-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:
        if child.poll() is None: child.terminate();child.wait(timeout=10)
