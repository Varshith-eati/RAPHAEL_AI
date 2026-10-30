"""Native transparent overlay: zero paint timer activity while hidden."""
from enum import Enum
import math
import time
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget

class State(str, Enum):
    HIDDEN = 'hidden'
    ACTIVATING = 'activating'
    LISTENING = 'listening'
    THINKING = 'thinking'
    SPEAKING = 'speaking'
    DEACTIVATING = 'deactivating'

class Orb(QWidget):
    moved = Signal(int, int)
    def __init__(self, settings):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.state = State.HIDDEN
        self.level = 0.
        self.display_level = 0.
        self.phase = 0.
        self.opacity = 0.
        self.last_frame = time.monotonic()
        self.caption = ''
        self.drag_origin = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.apply(settings)
        QGuiApplication.instance().screenAdded.connect(self.watch_screen)
        QGuiApplication.instance().screenRemoved.connect(self.fit)
        for screen in QGuiApplication.screens(): self.watch_screen(screen)

    def watch_screen(self, screen):
        screen.availableGeometryChanged.connect(self.fit)
        self.fit()

    def apply(self, settings):
        self.options = settings
        self.setWindowFlag(Qt.WindowTransparentForInput, not settings['draggable_orb'])
        self.resize(settings['orb_size'], settings['orb_size'] + 56)
        if settings['orb_x'] != -1 or settings['orb_y'] != -1:
            self.move(settings['orb_x'], settings['orb_y'])
        else:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.right() - self.width() - 40, screen.bottom() - self.height() - 60)
        self.fit()
        self.timer.setInterval(100 if settings['reduced_motion'] or settings['low_resource'] else {'low': 66, 'balanced': 33, 'high': 20}[settings['animation_quality']])
        if self.state != State.HIDDEN and settings['orb_enabled']:
            self.last_frame = time.monotonic(); self.show(); self.timer.start()
        elif not settings['orb_enabled']: self.hide(); self.timer.stop()

    def fit(self, *_):
        center = self.geometry().center()
        screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
        rect = screen.availableGeometry()
        self.move(max(rect.left(), min(self.x(), rect.right() - self.width() + 1)),
                  max(rect.top(), min(self.y(), rect.bottom() - self.height() + 1)))

    def transition(self, state, caption=''):
        state = State(state)
        if state == State.HIDDEN:
            self.state = state; self.opacity = 0.; self.level = self.display_level = 0.
            self.hide(); self.timer.stop(); return
        if self.state == State.HIDDEN:
            self.opacity = 0.; self.last_frame = time.monotonic()
        if state != self.state: self.level = 0.
        self.state, self.caption = state, caption
        if self.options['orb_enabled']:
            self.fit(); self.show()
            if not self.timer.isActive():
                self.last_frame = time.monotonic(); self.timer.start()

    def advance(self):
        now = time.monotonic()
        elapsed = min(.15, max(0., now - self.last_frame)); self.last_frame = now
        if self.state == State.DEACTIVATING:
            self.opacity = max(0., self.opacity - elapsed / .35)
            if self.opacity == 0: self.transition(State.HIDDEN); return
        else: self.opacity = min(1., self.opacity + elapsed / .28)
        target = min(1., max(0., self.level)) if self.options['audio_reactive'] and self.state in (State.LISTENING, State.SPEAKING) else 0.
        # Fast attack and gentle release make actual audio visible without flicker.
        smoothing = .06 if target > self.display_level else .18
        self.display_level += (target - self.display_level) * (1 - math.exp(-elapsed / smoothing))
        if not self.options['reduced_motion']: self.phase += elapsed * .76
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self.opacity)
        size = self.width()
        center = QPointF(size / 2, size / 2)
        energy = self.display_level if self.options['audio_reactive'] else 0.
        if self.options['reduced_motion']: energy *= .25
        tint = {State.THINKING: (170, 135, 255), State.SPEAKING: (105, 255, 200)}.get(self.state, (75, 224, 255))
        pulse = 0 if self.options['reduced_motion'] else math.sin(self.phase * 3) * .018
        radius = size * (.29 + pulse + energy * .045)
        glow = self.options['orb_glow']
        halo = QRadialGradient(center, size * .48)
        halo.setColorAt(0, QColor(120, 250, 255, int(95 * glow)))
        halo.setColorAt(.5, QColor(*tint, int((70 + energy * 70) * glow)))
        halo.setColorAt(1, QColor(0, 100, 240, 0))
        p.setPen(Qt.NoPen); p.setBrush(halo); p.drawEllipse(center, size * .49, size * .49)
        p.setBrush(Qt.NoBrush)
        for ring in range(3):
            r = radius * (1 + ring * .16)
            p.setPen(QPen(QColor(*tint, int((165 - ring * 35) * (.4 + .6 * glow))), 1.3 if ring else 2.2))
            rect = QRectF(center.x() - r, center.y() - r, 2*r, 2*r)
            spin = self.phase * (70 if self.state == State.THINKING else 25) * (1 if ring % 2 else -1)
            p.drawArc(rect, int((spin + ring * 85) * 16), int((250 + 35 * energy) * 16))
        count = 32 if self.options['animation_quality'] == 'low' or self.options['low_resource'] else 64
        points = []
        for i in range(count):
            angle = math.tau * i / count
            lobes = 5 if self.state == State.LISTENING else 9 if self.state == State.SPEAKING else 7
            wave = math.sin(angle * lobes + self.phase * 2) * (.04 + energy * .08)
            r = radius * (.81 + wave)
            points.append(QPointF(center.x() + math.cos(angle) * r, center.y() + math.sin(angle) * r))
        p.setPen(QPen(QColor(120, 244, 255, 210), 1.2))
        for i, point in enumerate(points): p.drawLine(point, points[(i + 1) % count])
        for i in range(12):
            angle = i * math.tau / 12 + self.phase * .15
            point = QPointF(center.x() + math.cos(angle) * radius * .7, center.y() + math.sin(angle) * radius * .7)
            other = QPointF(center.x() + math.cos(angle + 2.6) * radius * .7, center.y() + math.sin(angle + 2.6) * radius * .7)
            p.setPen(QPen(QColor(115, 235, 255, 75), .8)); p.drawLine(point, other)
        core = QRadialGradient(center, radius * .43)
        core.setColorAt(0, QColor(240, 255, 255, 250)); core.setColorAt(.2, QColor(130, 245, 255, 190)); core.setColorAt(1, QColor(20, 170, 255, 0))
        p.setPen(Qt.NoPen); p.setBrush(core); p.drawEllipse(center, radius * .43, radius * .43)
        p.setPen(QColor(185, 240, 248)); p.setFont(QFont('Segoe UI', 9))
        label = self.caption or self.state.value.title()
        p.drawText(QRectF(8, size - 7, size - 16, 46), Qt.AlignHCenter | Qt.TextWordWrap, label)

    def mousePressEvent(self, event):
        if self.options['draggable_orb'] and event.button() == Qt.LeftButton:
            self.drag_origin = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None: self.move(event.globalPosition().toPoint() - self.drag_origin)

    def mouseReleaseEvent(self, event):
        if self.drag_origin is not None:
            self.drag_origin = None; self.fit(); self.moved.emit(self.x(), self.y())
