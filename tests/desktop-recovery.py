"""Actual Windows process crashes, bounded recovery and stop-during-backoff.

Only this test's own temporary companion is terminated. No audio is captured.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from raphael.realtime.settings import SettingsStore
from raphael.desktop.windows import startup_value

def wait_for(function,seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=function()
        if result:return result
        time.sleep(.1)
    raise AssertionError('Timed out: '+str(function))

def read_status(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def visible_windows(pids):
    user=ctypes.windll.user32;found=[]
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def inspect(window,param):
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(window,ctypes.byref(pid))
        if pid.value in pids and user.IsWindowVisible(window):found.append(int(window))
        return True
    user.EnumWindows(callback(inspect),0)
    return found

def kill_test_child(pid):
    dll=ctypes.WinDLL('kernel32',use_last_error=True)
    dll.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];dll.OpenProcess.restype=wintypes.HANDLE
    dll.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    dll.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=dll.OpenProcess(1,False,pid);assert handle
    try:assert dll.TerminateProcess(handle,23)
    finally:dll.CloseHandle(handle)

checks=[];before=startup_value()
with tempfile.TemporaryDirectory() as folder:
    data=Path(folder);config=data/'config.toml'
    config.write_text('data_dir="runtime"\n[server]\nport=18982\n[chat]\nport=11463\n[laptop]\nenabled=false\n',encoding='utf-8')
    settings=SettingsStore(data/'runtime'/'interaction-settings.json')
    settings.update({'startup_delay':1,'wake_enabled':False})
    arguments=[sys.executable,'-E','-s','-B',str(ROOT/'desktop.py'),'--config',str(config)]
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    parent=subprocess.Popen(arguments+['--startup','--background'],creationflags=flags)
    path=data/'runtime'/'desktop-supervisor.json'
    def ready():
        try:
            connection=http.client.HTTPConnection('127.0.0.1',18982,timeout=.5)
            connection.request('GET','/api/status');response=connection.getresponse();response.read();connection.close()
            return response.status==403
        except OSError:return False
    try:
        first=wait_for(lambda:read_status(path).get('desktop_pid'))
        assert not visible_windows({parent.pid,first})
        wait_for(ready)
        assert not visible_windows({parent.pid,first})
        checks.append('Sign-in-style startup has no visible main window or orb before or after initialization')
        duplicate=subprocess.run(arguments+['--background'],creationflags=flags,timeout=10)
        assert duplicate.returncode==0 and read_status(path)['desktop_pid']==first
        checks.append('Repeated startup keeps exactly the same supervised desktop process')
        kill_test_child(first)
        wait_for(lambda:read_status(path).get('state')=='backoff')
        def replacement():
            state=read_status(path)
            return state.get('desktop_pid') if state.get('state')=='running' and state.get('desktop_pid')!=first else None
        second=wait_for(replacement)
        wait_for(ready);assert parent.poll() is None
        assert not visible_windows({parent.pid,second})
        checks.append('An actual desktop crash restarts once after backoff, hidden, with the backend reachable')
        kill_test_child(second)
        wait_for(lambda:read_status(path).get('state')=='backoff')
        stopped=subprocess.run(arguments+['--exit'],creationflags=flags,timeout=12)
        assert stopped.returncode==0 and parent.wait(timeout=10)==0
        assert read_status(path)['state']=='stopped'
        checks.append('Stop during crash backoff cancels recovery without relaunching')
        settings.update({'crash_recovery':False})
        old_supervisor=read_status(path)['supervisor_pid']
        parent=subprocess.Popen(arguments+['--background'],creationflags=flags)
        wait_for(lambda:(state:=read_status(path)).get('state')=='running' and state.get('supervisor_pid')!=old_supervisor and state.get('desktop_pid'))
        wait_for(ready);third=read_status(path)['desktop_pid'];kill_test_child(third)
        assert parent.wait(timeout=10)!=0
        assert read_status(path)['state']=='recovery_exhausted'
        checks.append('Disabling crash recovery prevents an abnormal exit from restarting')
        assert startup_value()==before
    except BaseException:
        print('Supervisor status:',read_status(path))
        log=data/'runtime'/'recovery.log'
        if log.exists():print(log.read_text())
        raise
    finally:
        if parent.poll() is None:
            subprocess.run(arguments+['--exit'],creationflags=flags,timeout=12)
            try:parent.wait(timeout=10)
            except subprocess.TimeoutExpired:parent.terminate();parent.wait(timeout=10)
report={'result':'passed','microphone':'not opened','startup_registration_changed':False,'checks':checks}
(ROOT/'docs'/'startup-recovery-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
