"""One validated settings model shared with the HTTP interface."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout,
    QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QDialogButtonBox, QLabel, QMessageBox, QScrollArea)
from ..realtime.settings import LIMITS, OPTIONS

GROUPS = {
    'General': [('startup_enabled','Start with Windows (enables wake listening)'),('launch_minimized','Launch minimized to tray'),
        ('crash_recovery','Recover after a crash (up to three retries)'),
        ('background_enabled','Keep running after the browser closes'),('startup_notification','Show startup notification'),
        ('startup_delay','Startup delay (seconds)'),('hotkey','Activation shortcut')],
    'Voice': [('wake_enabled','Listen locally for “Hey Raphael”'),('wake_sensitivity','Wake phrase sensitivity'),
        ('vad_sensitivity','Voice activity sensitivity'),('silence_seconds','End of speech silence (seconds)'),
        ('followup_seconds','Follow-up window (seconds)'),('barge_in','Listen for “Raphael, stop” during replies'),
        ('microphone','Microphone'),('speech_streaming','Stream speech in phrases'),('voice','Speaking voice'),
        ('speed','Speaking speed'),('volume','Speaker volume'),('input_language','Spoken language')],
    'Orb': [('orb_enabled','Show floating orb'),('orb_size','Orb size'),('orb_x','Position X (-1 = default)'),
        ('orb_y','Position Y (-1 = default)'),('draggable_orb','Allow dragging (otherwise clicks pass through)'),
        ('orb_glow','Glow intensity'),('animation_quality','Animation quality'),('audio_reactive','React to audio'),
        ('hide_timeout','Inactivity timeout (seconds)'),('orb_for_text','Show orb for browser text'),('reduced_motion','Reduced motion')],
    'Performance': [('response_streaming','Stream text as it arrives'),('preferred_model','Preferred model'),
        ('fast_conversation','Use a smaller prompt for standalone questions'),
        ('model_routing','Choose a model by question complexity'),('fast_model','Fast model'),('advanced_model','Advanced model'),
        ('memory_limit','Maximum saved notes per request'),('low_resource','Low resource animation'),('diagnostics','Save content-free timing logs')],
}

class SettingsDialog(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle('Raphael · Background & Real-Time Interaction')
        self.resize(660, 650)
        self.setStyleSheet('QWidget { background: #0b171c; color: #d6eef0; font: 10pt "Segoe UI"; } QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox { padding: 6px; background:#14272e; } QPushButton {padding:8px 16px;}')
        layout = QVBoxLayout(self)
        note = QLabel('Wake listening and startup are optional. Ctrl+Alt+M mutes the microphone immediately.\nBarge-in uses local recognition; headphones help prevent speaker echo. No audio is saved.')
        note.setWordWrap(True); layout.addWidget(note)
        tabs = QTabWidget(); layout.addWidget(tabs)
        self.controls = {}
        values = controller.app.settings.get()
        for name, fields in GROUPS.items():
            page = QWidget(); form = QFormLayout(page)
            for key, label in fields:
                value = values[key]
                if type(value) is bool:
                    widget = QCheckBox(); widget.setChecked(value)
                elif type(value) is int:
                    widget = QSpinBox(); widget.setRange(*LIMITS[key]); widget.setValue(value)
                elif type(value) is float:
                    widget = QDoubleSpinBox(); widget.setRange(*LIMITS[key]); widget.setSingleStep(.05); widget.setValue(value)
                elif key in OPTIONS:
                    widget = QComboBox(); widget.addItems(OPTIONS[key]); widget.setCurrentText(value)
                elif key.endswith('_model'):
                    widget = QComboBox(); widget.setEditable(True)
                    widget.addItems([''] + list(controller.app.config.chat.models)); widget.setCurrentText(value)
                elif key == 'microphone':
                    widget = QComboBox(); widget.addItem('Windows default', '')
                    try:
                        from .audio import microphones
                        for device in microphones(): widget.addItem(device, device)
                    except Exception: pass
                    if value and widget.findData(value) == -1: widget.addItem(value, value)
                    widget.setCurrentIndex(max(0, widget.findData(value)))
                else: widget = QLineEdit(value)
                self.controls[key] = widget; form.addRow(label, widget)
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page); tabs.addTab(scroll, name)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def save(self):
        values = {}
        for key, widget in self.controls.items():
            if isinstance(widget, QCheckBox): value = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)): value = widget.value()
            elif isinstance(widget, QComboBox): value = widget.currentData() if key == 'microphone' else widget.currentText()
            else: value = widget.text()
            values[key] = value
        try: self.controller.change_settings(values)
        except Exception as error:
            QMessageBox.warning(self, 'Settings were not saved', str(error)); return
        self.accept()
