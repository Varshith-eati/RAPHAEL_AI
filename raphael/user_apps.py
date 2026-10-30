"""User-opened apps must outlive the background assistant's process cleanup."""
import os
import subprocess
import sys
import webbrowser

def creation_flags():
    return getattr(subprocess,'CREATE_BREAKAWAY_FROM_JOB',0) if os.environ.get('RAPHAEL_SUPERVISED')=='1' else 0

def _open(target, browser):
    flags=creation_flags()
    if not flags:
        return webbrowser.open(target) if browser else os.startfile(target)
    # Only fixed Python source is executable; the target is data on stdin.
    source='import sys, webbrowser; webbrowser.open(sys.stdin.read())' if browser else 'import sys, os; os.startfile(sys.stdin.read())'
    subprocess.run([sys.executable,'-E','-s','-B','-c',source],input=target,text=True,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,
        creationflags=flags|getattr(subprocess,'CREATE_NO_WINDOW',0))

def open_browser(url):return _open(url,True)
def open_associated(target):return _open(target,False)
