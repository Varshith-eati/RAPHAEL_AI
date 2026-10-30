"""Per-user Windows integration; no shell commands or administrator permissions."""
import ctypes
from ctypes import wintypes
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'RaphaelCompanion'

def startup_command(entry, config=None):
    executable = Path(sys.executable)
    windowless = executable.with_name('pythonw.exe')
    if windowless.exists(): executable = windowless
    args = [str(executable), '-E', '-s', '-B', str(Path(entry).resolve()), '--startup', '--background']
    if config is not None: args += ['--config', str(Path(config).resolve())]
    return subprocess.list2cmdline(args)

def legacy_startup_value():
    if os.name != 'nt': return ''
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, RUN_NAME)
            return value if kind == winreg.REG_SZ else ''
    except FileNotFoundError: return ''

def startup_path():
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 7, None, 0, buffer)
    if result: raise OSError('Cannot locate the current user Startup folder.')
    return Path(buffer.value) / 'Raphael Companion.lnk'


def shortcut_operation(operation, path, **values):
    # Values travel as JSON on stdin, never interpolated into PowerShell source.
    script = r'''
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
$v=[Console]::In.ReadToEnd() | ConvertFrom-Json
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut($v.path)
if ($v.operation -eq 'write') {
    $link.TargetPath=$v.target
    $link.Arguments=$v.arguments
    $link.WorkingDirectory=$v.directory
    $link.WindowStyle=7
    $link.Description='Raphael background assistant'
    $link.Save()
} else {
    @{target=$link.TargetPath;arguments=$link.Arguments;directory=$link.WorkingDirectory} | ConvertTo-Json -Compress
}
'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        input=json.dumps({'operation':operation,'path':str(path),**values}), text=True,encoding='utf-8',
        capture_output=True, timeout=15, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise OSError('Could not update the Windows startup shortcut.')
    return json.loads(result.stdout) if operation == 'read' else None


def startup_spec(entry, config=None):
    executable = Path(sys.executable)
    windowless = executable.with_name('pythonw.exe')
    if windowless.exists(): executable = windowless
    entry = Path(entry).resolve()
    args = ['-E','-s','-B',str(entry),'--startup','--background']
    if config is not None: args += ['--config',str(Path(config).resolve())]
    return {'target':str(executable),'arguments':subprocess.list2cmdline(args),'directory':str(entry.parent)}


def startup_value():
    if os.name != 'nt': return ''
    path = startup_path()
    if path.exists(): return json.dumps(shortcut_operation('read',path),sort_keys=True)
    return legacy_startup_value()


def startup_matches(entry, config=None):
    value = startup_value()
    return value == json.dumps(startup_spec(entry,config),sort_keys=True)


def startup_snapshot():
    path=startup_path()
    return (path.read_bytes() if path.exists() else None,legacy_startup_value())


def restore_startup(snapshot):
    contents,legacy=snapshot
    path=startup_path()
    if contents is None:path.unlink(missing_ok=True)
    else:
        temporary=path.with_name('Raphael Companion.restore.lnk')
        temporary.write_bytes(contents);os.replace(temporary,path)
    if legacy:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,RUN_NAME,0,winreg.REG_SZ,legacy)


def set_startup(enabled, entry, config=None):
    if os.name != 'nt': raise OSError('Automatic startup is available on Windows.')
    path = startup_path()
    if enabled:
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary = path.with_name('Raphael Companion.pending.lnk')
        try:
            shortcut_operation('write',temporary,**startup_spec(entry,config))
            os.replace(temporary,path)
        finally: temporary.unlink(missing_ok=True)
    elif startup_matches(entry,config): path.unlink(missing_ok=True)
    # Only migrate/remove the legacy entry owned by this installation.
    import winreg
    if legacy_startup_value() in (startup_command(entry),startup_command(entry,config)):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
            try: winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError: pass

def instance_name(port, role=''):
    identity = (f'{getpass.getuser()}|{Path.home()}|{port}' + (f'|{role}' if role else '')).encode()
    return 'Raphael-' + hashlib.sha256(identity).hexdigest()[:24]


class Instance:
    """Named mutex closes the simultaneous-launch race; IPC has an owner-only ACL."""
    def __init__(self, port, role=''):
        self.name = instance_name(port,role)
        self.handle = None
        if os.name == 'nt':
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            self.handle = kernel.CreateMutexW(None, False, 'Local\\' + self.name)
            if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
            self.owner = ctypes.get_last_error() != 183
        else: self.owner = True

    def close(self):
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(self.handle)
            self.handle = None

def hotkey_filter(activate, dismiss, wake):
    from PySide6.QtCore import QAbstractNativeEventFilter
    class Filter(QAbstractNativeEventFilter):
        def __init__(self):
            super().__init__()
            self.ids = []
        def register(self, setting):
            self.close()
            if os.name != 'nt': return False
            modifier, key = {'Ctrl+Alt+R': (3, 0x52), 'Ctrl+Shift+R': (6, 0x52), 'Ctrl+Alt+Space': (3, 0x20)}[setting]
            okay = True
            for identifier, mods, code in ((0x5A10, modifier, key), (0x5A11, 3, 0x1B), (0x5A12, 3, 0x4D)):
                if ctypes.windll.user32.RegisterHotKey(None, identifier, mods | 0x4000, code): self.ids.append(identifier)
                else: okay = False
            return okay
        def nativeEventFilter(self, event_type, message):
            if os.name == 'nt':
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:
                    {0x5A10: activate, 0x5A11: dismiss, 0x5A12: wake}.get(msg.wParam, lambda: None)()
                    return True, 0
            return False, 0
        def close(self):
            if os.name == 'nt':
                for identifier in self.ids: ctypes.windll.user32.UnregisterHotKey(None, identifier)
            self.ids.clear()
    return Filter()
