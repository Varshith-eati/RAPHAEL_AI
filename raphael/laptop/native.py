"""Fixed Windows queries and app launch targets. Never executes model commands."""
from datetime import datetime, timezone
from pathlib import Path
import ctypes
import json
import os
import platform
import shutil
import subprocess

from ..errors import AppError
from ..user_apps import creation_flags, open_associated

APPS = {'calculator': 'Calculator', 'notepad': 'Notepad', 'workspace': 'File Explorer (Raphael Workspace)',
        'explorer': 'File Explorer', 'chrome': 'Chrome', 'gmail': 'Gmail', 'youtube': 'YouTube',
        'google': 'Google', 'github': 'GitHub', 'task_manager': 'Task Manager', 'settings': 'Windows About settings'}
SITES = {'gmail':'https://mail.google.com/', 'youtube':'https://www.youtube.com/',
         'google':'https://www.google.com/', 'github':'https://github.com/'}


class NativeLaptop:
    def __init__(self, workspace):
        self.workspace = workspace
        self.windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))

    def system_info(self):
        result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'operating_system': platform.platform(),
                  'architecture': platform.machine(), 'logical_processors': os.cpu_count(), 'cpu': platform.processor()}
        if os.name == 'nt':
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                    result['cpu'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
            except OSError:
                pass
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in
                    ('total_physical', 'free_physical', 'total_page', 'free_page', 'total_virtual', 'free_virtual', 'extended')]
            memory = Memory(); memory.length = ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result['ram_gb'] = round(memory.total_physical / 1024**3, 2)
                result['ram_available_gb'] = round(memory.free_physical / 1024**3, 2)
            script = ('[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); '
                      '$c=Get-CimInstance Win32_ComputerSystem; '
                      '$g=@(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name); '
                      '[pscustomobject]@{manufacturer=$c.Manufacturer;model=$c.Model;graphics=$g} | ConvertTo-Json -Compress')
            try:
                query = subprocess.run([str(self.windows/'System32/WindowsPowerShell/v1.0/powershell.exe'),
                                        '-NoProfile', '-NonInteractive', '-Command', script],
                                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=12,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                if query.returncode == 0:
                    info = json.loads(query.stdout)
                    result.update({key: info[key] for key in ('manufacturer', 'model', 'graphics') if key in info})
            except (OSError, ValueError, subprocess.TimeoutExpired):
                result['graphics_status'] = 'GPU details were unavailable; other measurements are current.'
        usage = shutil.disk_usage(self.workspace.root)
        result['workspace_disk'] = {'total_gb': round(usage.total/1024**3, 2), 'free_gb': round(usage.free/1024**3, 2)}
        return result

    def chrome_path(self):
        for variable in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
            base=os.environ.get(variable)
            if base:
                candidate=Path(base)/'Google/Chrome/Application/chrome.exe'
                if candidate.is_file():return candidate
        return None

    def open_app(self, app):
        if app not in APPS:
            raise AppError('Choose one of the supported apps: '+', '.join(APPS)+'.', 403, 'app_blocked')
        if os.name != 'nt':
            raise AppError('Laptop app launching is configured for Windows only.', 503, 'platform_unavailable')
        if app in SITES or app=='chrome':
            chrome=self.chrome_path()
            if chrome:
                subprocess.Popen([str(chrome),SITES.get(app,'about:blank')],stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=creation_flags())
            elif app in SITES:
                open_associated(SITES[app])
            else:
                raise AppError('Chrome was not found in its standard install locations. Website buttons can still use your default browser.',404,'chrome_missing')
        elif app == 'settings':
            open_associated('ms-settings:about')
        else:
            commands = {'calculator': [str(self.windows/'System32/calc.exe')],
                        'explorer': [str(self.windows/'explorer.exe')],
                        'notepad': [str(self.windows/'System32/notepad.exe')],
                        'workspace': [str(self.windows/'explorer.exe'), str(self.workspace.path('.', folder=True))],
                        'task_manager': [str(self.windows/'System32/Taskmgr.exe')]}
            subprocess.Popen(commands[app], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,creationflags=creation_flags())
        return {'message': 'Requested opening '+APPS[app]+'.', 'app': app}

    def open_text(self, relative):
        target = self.workspace.path(relative)
        self.workspace._read(target)
        if os.name != 'nt':
            raise AppError('Text-file opening is configured for Windows only.', 503, 'platform_unavailable')
        subprocess.Popen([str(self.windows/'System32/notepad.exe'), str(target)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,creationflags=creation_flags())
        return {'message': 'Requested opening '+relative+' in Notepad.', 'path': str(target)}
