"""Measure actual Windows CPU time and working set; wake probe uses fake silence."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from raphael.config import load_config
from raphael.realtime.settings import SettingsStore

def metrics(pid):
    dll=ctypes.WinDLL('kernel32',use_last_error=True)
    dll.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];dll.OpenProcess.restype=wintypes.HANDLE
    dll.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    dll.CloseHandle.argtypes=[wintypes.HANDLE]
    class Memory(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(key,ctypes.c_size_t) for key in ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
    handle=dll.OpenProcess(0x410,False,pid);assert handle
    try:
        times=[wintypes.FILETIME() for _ in range(4)]
        assert dll.GetProcessTimes(handle,*(ctypes.byref(t) for t in times))
        cpu=sum((t.dwHighDateTime<<32)|t.dwLowDateTime for t in times[2:])/10_000_000
        memory=Memory();memory.cb=ctypes.sizeof(memory)
        psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
        assert psapi.GetProcessMemoryInfo(handle,ctypes.byref(memory),ctypes.sizeof(memory))
        return {'cpu_seconds':cpu,'working_set_mb':round(memory.ws/1024**2,1),'private_commit_mb':round(memory.pagefile/1024**2,1)}
    finally:dll.CloseHandle(handle)

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def wait_for(function,seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=function()
        if result:return result
        time.sleep(.1)
    raise AssertionError('Probe timed out')

def measure(pids):
    before=[metrics(pid) for pid in pids];started=time.monotonic();time.sleep(10)
    after=[metrics(pid) for pid in pids];elapsed=time.monotonic()-started
    cpu=sum(b['cpu_seconds']-a['cpu_seconds'] for a,b in zip(before,after))
    return {'sample_seconds':round(elapsed,2),'cpu_one_core_percent':round(cpu/elapsed*100,2),
        'cpu_whole_machine_percent':round(cpu/elapsed*100/(os.cpu_count() or 1),2),
        'working_set_mb':round(sum(v['working_set_mb'] for v in after),1),
        'private_commit_mb':round(sum(v['private_commit_mb'] for v in after),1),'processes':len(pids)}

report={};flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
base=load_config(ROOT/'config.toml')
with tempfile.TemporaryDirectory() as folder:
    data=Path(folder);config=data/'config.toml'
    config.write_text('data_dir="runtime"\n[server]\nport=18984\n[chat]\nport=11464\n[transcription]\nmodel='+json.dumps(str(base.resolve(base.transcription.model)).replace('\\','/'))+'\n[laptop]\nenabled=false\n',encoding='utf-8')
    store=SettingsStore(data/'runtime'/'interaction-settings.json');store.update({'startup_delay':1})
    arguments=[sys.executable,'-E','-s','-B',str(ROOT/'desktop.py'),'--config',str(config)]
    parent=subprocess.Popen(arguments+['--background'],creationflags=flags)
    try:
        pid=wait_for(lambda:read(data/'runtime'/'desktop-supervisor.json').get('desktop_pid'))
        time.sleep(3)
        report['microphone_off_with_supervisor']=measure([read(data/'runtime'/'desktop-supervisor.json')['supervisor_pid'],pid])
    finally:
        subprocess.run(arguments+['--exit'],creationflags=flags,timeout=12);parent.wait(timeout=15)
    store.update({'wake_enabled':True})
    child=subprocess.Popen([sys.executable,'-E','-s','-B',str(ROOT/'tests'/'desktop-idle-child.py'),'--managed','--startup','--background','--config',str(config)],creationflags=flags)
    try:
        state=wait_for(lambda:read(data/'runtime'/'idle-probe.json'))
        assert not state.get('error'),state
        assert state['engines']['chat']['state']=='sleeping' and state['engines']['voice']['state']=='sleeping'
        assert state['orb']=='hidden' and not state['paint_timer'] and state['job_count']==0
        report['wake_ready_real_whisper_generated_silence']=measure([state['pid']])
        state=read(data/'runtime'/'idle-probe.json');assert state['job_count']==0
        report['wake_state']=state
    finally:
        subprocess.run(arguments+['--managed','--exit'],creationflags=flags,timeout=12);child.wait(timeout=15)
report['result']='passed'
report['limitations']='10-second idle samples; silence is generated, not hardware capture. Wake sample excludes the supervisor. No per-frame inference; no chat/TTS models loaded. Real room speech will invoke Whisper and use more CPU.'
(ROOT/'docs'/'startup-idle-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
