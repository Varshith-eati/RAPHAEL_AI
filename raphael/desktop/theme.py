"""Use Windows' installed text fonts, including when Qt runs offscreen in tests."""
import os
from pathlib import Path
from PySide6.QtGui import QFontDatabase, QFont

def initialize_fonts(app):
    directory = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    # Some Qt platform plugins do not enumerate the Windows font store.
    if 'Segoe UI' not in QFontDatabase.families():
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'Nirmala.ttf'):
            path = directory / name
            if path.is_file(): QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI', 10))
