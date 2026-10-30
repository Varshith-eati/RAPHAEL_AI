"""Small Windows supervisor: bounded restart, interruptible waits, owned process tree.

No Qt, audio or inference libraries are imported in the supervisor process.
"""
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from .windows import Instance, instance_name

RESTART = 75
BACKOFF = (5, 15, 45)
STABLE_SECONDS = 600
LOG = logging.getLogger('raphael.recovery')

def kernel():
    dll = ctypes.WinDLL('kernel32',use_last_error=True)
    for name, args, result in (
        ('CreateEventW',[ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR],wintypes.HANDLE),
        ('OpenEventW',[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR],wintypes.HANDLE),
        ('SetEvent',[wintypes.HANDLE],wintypes.BOOL),
        ('WaitForSingleObject',[wintypes.HANDLE,wintypes.DWORD],wintypes.DWORD),
        ('CloseHandle',[wintypes.HANDLE],wintypes.BOOL),
        ('CreateJobObjectW',[ctypes.c_void_p,wintypes.LPCWSTR],wintypes.HANDLE),
        ('SetInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD],wintypes.BOOL),
        ('AssignProcessToJobObject',[wintypes.HANDLE,wintypes.HANDLE],wintypes.BOOL),
    ):
        function=getattr(dll,name);function.argtypes=args;function.restype=result
    return dll

class StopEvent:
    def __init__(self,port):
        self.dll=kernel()
        self.handle=self.dll.CreateEventW(None,True,False,'Local\\'+instance_name(port,'supervisor')+'-stop')
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
    def wait(self,seconds):
        result=self.dll.WaitForSingleObject(self.handle,int(max(0,seconds)*1000))
        if result not in (0,258): raise ctypes.WinError(ctypes.get_last_error())
        return result==0
    def close(self):
        if self.handle:self.dll.CloseHandle(self.handle);self.handle=None

def request_stop(port):
    if os.name!='nt':return False
    dll=kernel();handle=dll.OpenEventW(2,False,'Local\\'+instance_name(port,'supervisor')+'-stop')
    if not handle:return False
    try:return bool(dll.SetEvent(handle))
    finally:dll.CloseHandle(handle)

class ProcessTree:
    """A crash cannot leave this companion's Ollama descendants behind."""
    def __init__(self,child):
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
                ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                ('active',wintypes.DWORD),('affinity',ctypes.c_size_t),
                ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_ulonglong) for name in ('reads','writes','other','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),
                ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.dll=kernel();self.handle=self.dll.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        # Explicit user-app launches may break away; model/server descendants stay owned.
        limits=Extended();limits.basic.flags=0x2000 | 0x800  # KILL_ON_JOB_CLOSE | BREAKAWAY_OK
        if not self.dll.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not self.dll.AssignProcessToJobObject(self.handle,int(child._handle)):
            error=ctypes.WinError(ctypes.get_last_error());self.close();raise error
    def close(self):
        if self.handle:self.dll.CloseHandle(self.handle);self.handle=None

def retry_delay(code,failures,uptime,enabled=True):
    if code==0:return None,failures
    if code==RESTART:return 0,failures
    if uptime>=STABLE_SECONDS:failures=0
    if not enabled or failures>=len(BACKOFF):return None,failures
    return BACKOFF[failures],failures+1

def supervise(entry,config_path,config,args):
    from ..realtime.settings import SettingsStore
    guard=Instance(config.server.port,'supervisor')
    command=[sys.executable,'-E','-s','-B',str(entry),'--config',str(config_path),'--managed']
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    if not guard.owner:
        guard.close()
        if args.open or not (args.background or args.startup):
            return subprocess.run(command+['--forward-only','--open'],creationflags=flags,timeout=10).returncode
        return 0
    config.data_dir.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(config.data_dir/'recovery.log',maxBytes=256000,backupCount=2,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'));LOG.addHandler(handler);LOG.setLevel(logging.INFO)
    stop=None;child=None;tree=None
    failures=0;desktop_pid=None
    def status(state,code=None):
        path=config.data_dir/'desktop-supervisor.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'state':state,'supervisor_pid':os.getpid(),
            'desktop_pid':desktop_pid,'launcher_pid':child.pid if child else None,'restarts':failures,'exit_code':code}),encoding='utf-8')
        # A diagnostics reader may briefly hold a Windows file handle without delete sharing.
        for attempt in range(5):
            try:os.replace(temporary,path);break
            except PermissionError:
                if attempt==4:LOG.warning('status_write_busy');break
                time.sleep(.02)
    try:
        stop=StopEvent(config.server.port)
        first=True
        while not stop.wait(0):
            desktop_pid=None;launch_id=uuid.uuid4().hex
            launch=command+(['--startup','--background'] if first and args.startup else ['--background'])
            launch+=['--launch-id',launch_id]
            if first and (args.open or not(args.startup or args.background)):launch+=['--open']
            child=subprocess.Popen(launch,creationflags=flags,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                env={**os.environ,'RAPHAEL_SUPERVISED':'1'})
            try:tree=ProcessTree(child)
            except Exception:
                child.terminate();child.wait(timeout=10);raise
            started=time.monotonic();status('running');LOG.info('desktop_started pid=%d',child.pid)
            first=False
            while child.poll() is None:
                if desktop_pid is None:
                    try:
                        record=json.loads((config.data_dir/'desktop-instance.json').read_text())
                        if record.get('launch_id')==launch_id:
                            desktop_pid=record['pid'];status('running')
                    except (OSError,ValueError,KeyError):pass
                if stop.wait(1):
                    # The same owner-only IPC used by the tray requests graceful cleanup.
                    subprocess.run(command+['--exit','--forward-only'],creationflags=flags,timeout=10)
                    try:child.wait(timeout=35)
                    except subprocess.TimeoutExpired:
                        LOG.warning('shutdown_timeout');tree.close();child.wait(timeout=10)
                    status('stopped');return 0
            code=child.returncode
            tree.close();tree=None
            enabled=SettingsStore(config.data_dir/'interaction-settings.json').get()['crash_recovery']
            delay,failures=retry_delay(code,failures,time.monotonic()-started,enabled)
            LOG.info('desktop_exit code=%s retries=%s',code,failures)
            if delay is None or ctypes.windll.user32.GetSystemMetrics(0x2000):
                status('stopped' if code==0 else 'recovery_exhausted',code);return code
            status('backoff',code)
            if stop.wait(delay):status('stopped');return 0
        status('stopped');return 0
    finally:
        if tree:tree.close()
        if child and child.poll() is None:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        if stop:stop.close()
        guard.close();LOG.removeHandler(handler);handler.close()
