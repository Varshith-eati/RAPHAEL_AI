"""Bounded text files under one explicit root; no scripts or link traversal."""
from pathlib import Path, PureWindowsPath
import difflib
import hashlib
import os
import re
import stat
import tempfile
import uuid

from ..errors import AppError

TEXT_TYPES = {'.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.log'}
MAX_BYTES = 32000


class Workspace:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.canonical = self.root.resolve()

    @staticmethod
    def _linked(path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)

    def path(self, relative, *, folder=False):
        if not self.root.is_dir() or self.root.resolve() != self.canonical or self._linked(self.root):
            raise AppError('The approved workspace is unavailable or has changed. Restart after checking its location.', 403, 'workspace_changed')
        if not isinstance(relative, str) or not relative or len(relative) > 400:
            raise AppError('Use a short path relative to Raphael Workspace.')
        if relative == '.' and folder:
            return self.root
        win = PureWindowsPath(relative)
        parts = relative.replace('\\', '/').split('/')
        if (win.drive or win.root or len(parts) > 8 or any(
            not part or part in ('.', '..') or part.startswith('.') or part.endswith((' ', '.'))
            or re.search(r'[<>:"|?*\x00-\x1f]', part)
            or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I)
            for part in parts)):
            raise AppError('That path is outside the allowed workspace rules.', 403, 'path_blocked')
        target = self.root.joinpath(*parts)
        if not target.resolve().is_relative_to(self.canonical):
            raise AppError('Files must stay inside Raphael Workspace.', 403, 'path_blocked')
        current = self.root
        for part in parts:
            current /= part
            if self._linked(current):
                raise AppError('Linked folders and files are not available to laptop tools.', 403, 'link_blocked')
        if target.is_file() and target.stat().st_nlink > 1:
            raise AppError('Hard-linked files are not available to laptop tools.', 403, 'link_blocked')
        if not folder and target.suffix.lower() not in TEXT_TYPES:
            raise AppError('Use a text, Markdown, CSV, JSON, YAML or log file. Executable files are not supported.', 403, 'file_type_blocked')
        return target

    def _read(self, target):
        if not target.is_file():
            raise AppError('That text file does not exist.', 404, 'file_missing')
        if target.stat().st_size > MAX_BYTES:
            raise AppError('This file is larger than the 32 KB text-file limit.', 413, 'file_too_large')
        data = target.read_bytes()
        if len(data) > MAX_BYTES:
            raise AppError('The file grew beyond the text-file limit.', 413, 'file_too_large')
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise AppError('This file is not UTF-8 text.') from None
        if '\0' in text:
            raise AppError('Binary file contents are not supported.')
        return data, text

    def list(self, relative='.'):
        folder = self.path(relative, folder=True)
        if not folder.is_dir():
            raise AppError('That workspace folder does not exist.', 404, 'folder_missing')
        items = []
        for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.name.startswith('.'):
                continue
            try:
                self.path(entry.relative_to(self.root).as_posix(), folder=entry.is_dir())
            except AppError:
                continue
            items.append({'name': entry.name, 'path': entry.relative_to(self.root).as_posix(),
                          'kind': 'folder' if entry.is_dir() else 'file',
                          'bytes': entry.stat().st_size if entry.is_file() else None})
            if len(items) >= 100:
                break
        return {'workspace': str(self.root), 'path': relative, 'items': items, 'limit': 100}

    def read(self, relative):
        data, text = self._read(self.path(relative))
        return {'path': relative, 'text': text[:12000], 'truncated': len(text) > 12000,
                'sha256': hashlib.sha256(data).hexdigest()}

    def prepare_write(self, relative, content):
        if not isinstance(content, str) or len(content) > 16000 or '\0' in content or len(content.encode('utf-8')) > MAX_BYTES:
            raise AppError('Proposed text must be at most 16,000 characters and 32 KB.')
        target = self.path(relative)
        if not target.parent.is_dir():
            raise AppError('Create the parent folder first.')
        data, previous = self._read(target) if target.exists() else (None, '')
        return {'tool': 'write_text', 'arguments': {'path': relative, 'content': content},
                'target': str(target), 'title': ('Update ' if data is not None else 'Create ') + relative,
                'expected_sha256': hashlib.sha256(data).hexdigest() if data is not None else None,
                'preview': ''.join(difflib.unified_diff(previous.splitlines(keepends=True), content.splitlines(keepends=True),
                                                       fromfile=relative+' (before)', tofile=relative+' (after)')),
                'content': content, 'backup_on_update': data is not None}

    def prepare_folder(self, relative):
        target = self.path(relative, folder=True)
        if target.exists() or not target.parent.is_dir():
            raise AppError('Choose a new folder name inside an existing workspace folder.')
        return {'tool': 'create_folder', 'arguments': {'path': relative}, 'target': str(target),
                'title': 'Create folder '+relative, 'preview': 'Create this empty folder: '+str(target)}

    def commit(self, proposal):
        relative = proposal['arguments']['path']
        if proposal['tool'] == 'create_folder':
            target = self.path(relative, folder=True)
            if target.exists() or not target.parent.is_dir():
                raise AppError('The folder changed since the preview. Ask Raphael to prepare it again.', 409, 'stale_preview')
            target.mkdir()
            return {'message': 'Created folder '+relative+'.', 'path': str(target)}
        target = self.path(relative)
        data = self._read(target)[0] if target.exists() else None
        actual = hashlib.sha256(data).hexdigest() if data is not None else None
        if actual != proposal['expected_sha256'] or str(target) != proposal['target']:
            raise AppError('The file changed since the preview. Review a new proposal before saving.', 409, 'stale_preview')
        backup = None
        if data is not None:
            backups = self.root / '.raphael-backups'
            if self._linked(backups):
                raise AppError('The backup folder must not be a link.', 403, 'link_blocked')
            backups.mkdir(exist_ok=True)
            backup = backups / (uuid.uuid4().hex + '-' + target.name)
            with backup.open('xb') as output:
                output.write(data)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.raphael-write-', suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(proposal['arguments']['content'].encode('utf-8'))
                output.flush(); os.fsync(output.fileno())
            self.path(relative)
            latest = self._read(target)[0] if target.exists() else None
            if (hashlib.sha256(latest).hexdigest() if latest is not None else None) != actual:
                raise AppError('The file changed while approval was being applied.', 409, 'stale_preview')
            if actual is None:
                # Windows rename fails when a file appeared after the preview.
                if os.name == 'nt':
                    os.rename(temporary, target)
                else:
                    os.link(temporary, target); temporary.unlink()
            else:
                os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {'message': 'Saved '+relative+'.', 'path': str(target), 'backup': str(backup) if backup else None}
