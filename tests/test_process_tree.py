"""Ensure crash cleanup kills owned helpers but preserves user-app processes."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from raphael.desktop.recovery import ProcessTree

@unittest.skipUnless(os.name=='nt','Windows job objects')
class ProcessTreeTests(unittest.TestCase):
    def test_user_app_breakaway_survives_owned_tree_cleanup(self):
        root=Path(__file__).resolve().parents[1]
        dll=ctypes.WinDLL('kernel32',use_last_error=True)
        dll.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];dll.OpenProcess.restype=wintypes.HANDLE
        dll.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];dll.WaitForSingleObject.restype=wintypes.DWORD
        dll.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];dll.CloseHandle.argtypes=[wintypes.HANDLE]
        def alive(pid):
            handle=dll.OpenProcess(0x100000,False,pid)
            if not handle:return False
            try:return dll.WaitForSingleObject(handle,0)==258
            finally:dll.CloseHandle(handle)
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);result=data/'children.json';go=data/'go'
            script='''import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from raphael.user_apps import creation_flags
go=Path(sys.argv[2]);result=Path(sys.argv[3])
while not go.exists():time.sleep(.02)
normal=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
external=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],creationflags=creation_flags())
result.write_text(json.dumps([normal.pid,external.pid]))
time.sleep(60)
'''
            child=subprocess.Popen([sys._base_executable,'-E','-s','-B','-c',script,str(root),str(go),str(result)],
                creationflags=subprocess.CREATE_NO_WINDOW,env={**os.environ,'RAPHAEL_SUPERVISED':'1'})
            tree=None;pids=[]
            try:
                tree=ProcessTree(child);go.touch();deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    try:pids=json.loads(result.read_text());break
                    except (OSError,ValueError):time.sleep(.05)
                self.assertEqual(len(pids),2)
                self.assertTrue(all(alive(pid) for pid in pids))
                tree.close();child.wait(timeout=5)
                deadline=time.monotonic()+3
                while alive(pids[0]) and time.monotonic()<deadline:time.sleep(.05)
                self.assertFalse(alive(pids[0]),'Owned inference/helper process survived cleanup')
                self.assertTrue(alive(pids[1]),'User-opened application was closed by Raphael cleanup')
            finally:
                if tree:tree.close()
                if child.poll() is None:child.terminate();child.wait(timeout=5)
                for pid in pids:
                    handle=dll.OpenProcess(1,False,pid)
                    if handle:
                        dll.TerminateProcess(handle,0);dll.CloseHandle(handle)

if __name__=='__main__':unittest.main()
