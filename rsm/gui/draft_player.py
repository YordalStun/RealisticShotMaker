"""Draft preview in the editing panel: a quick low-resolution render of the whole move, played on a loop.

Frames appear as they finish, so you see the start of the move within seconds of changing something.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

_NUM = re.compile(r"(\d+)(?=\.\w+$)")


class _FrameView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pix: QPixmap | None = None
        self.text = ""
        self.fraction = 0.0      # how much of the draft has rendered (thin bar along the bottom)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(180)

    def heightForWidth(self, w):
        return int(w * 9 / 16)

    def hasHeightForWidth(self):
        return True

    def sizeHint(self):
        return QSize(448, 252)

    def resizeEvent(self, ev):
        self.setFixedHeight(int(self.width() * 9 / 16))
        super().resizeEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0f0e0d"))
        if self.pix and not self.pix.isNull():
            s = self.pix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - s.width()) // 2, (self.height() - s.height()) // 2, s)
        if self.text:
            p.setPen(QColor("#9d9184"))
            r = self.rect().adjusted(16, 16, -16, -16)
            if self.pix:
                p.fillRect(self.rect().adjusted(0, self.height() - 26, 0, 0), QColor(0, 0, 0, 150))
                p.setPen(QColor("#efe5d8"))
                r = self.rect().adjusted(10, self.height() - 26, -10, 0)
                p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, self.text)
            else:
                p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, self.text)
        if 0.0 < self.fraction < 1.0:
            p.fillRect(0, self.height() - 3, int(self.width() * self.fraction), 3, QColor("#d08a3a"))
        p.end()


class DraftPlayer(QWidget):
    make_requested = Signal()
    auto_changed = Signal(bool)
    engine_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames: dict[int, QPixmap] = {}
        self.order: list[int] = []
        self.total = 0
        self.fps = 12.0
        self.i = 0
        self.playing = True
        self.rendering = False
        self._pending_reset = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        head = QHBoxLayout()
        self.fold = QToolButton()
        self.fold.setText("▾  Draft preview")
        self.fold.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.fold.setAutoRaise(True)
        self.fold.setCheckable(True)
        self.fold.setChecked(True)
        self.fold.toggled.connect(self._fold)
        self.auto = QCheckBox("Update as I edit")
        self.auto.setToolTip("Re-render the draft a few seconds after you change something.")
        self.auto.setChecked(True)
        self.auto.toggled.connect(self.auto_changed)
        head.addWidget(self.fold)
        head.addStretch(1)
        head.addWidget(self.auto)
        lay.addLayout(head)

        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        self.view = _FrameView()
        self.view.text = ("A quick low-resolution draft of the whole move plays here, so you can check the "
                          "framing and timing before you queue the real render.")
        bl.addWidget(self.view)
        ctl = QHBoxLayout()
        self.play_btn = QToolButton()
        self.play_btn.setText("❚❚")
        self.play_btn.setFixedWidth(30)
        self.play_btn.clicked.connect(self.toggle_play)
        self.scrub = QSlider(Qt.Horizontal)
        self.scrub.setRange(0, 0)
        self.scrub.sliderMoved.connect(self._scrubbed)
        self.scrub.sliderPressed.connect(lambda: self._timer.stop())
        self.scrub.sliderReleased.connect(lambda: self.playing and self._start_timer())
        self.time_lbl = QLabel("0.0 s")
        self.time_lbl.setObjectName("Caption")
        self.time_lbl.setFixedWidth(46)
        self.make_btn = QPushButton("Make draft")
        self.make_btn.setToolTip("Render a fast draft of the whole shot (low resolution, few samples).")
        self.make_btn.clicked.connect(self.make_requested)
        ctl.addWidget(self.play_btn)
        ctl.addWidget(self.scrub, 1)
        ctl.addWidget(self.time_lbl)
        ctl.addWidget(self.make_btn)
        bl.addLayout(ctl)
        eng = QHBoxLayout()
        eng.addWidget(QLabel("Draft engine:"))
        self.engine = QComboBox()
        self.engine.addItem("Fast (no ray tracing)", "eevee")
        self.engine.addItem("Ray traced (matches the final look)", "cycles")
        self.engine.setToolTip("Fast drafts use Blender's EEVEE: near-instant, good for framing and timing, but "
                               "lighting, glass and the lens are approximated.\nRay-traced drafts use the same "
                               "path tracer as the final render at low resolution, so the light looks right.\n"
                               "Renders in the queue are always fully ray traced.")
        self.engine.currentIndexChanged.connect(lambda _: self.engine_changed.emit(self.engine.currentData()))
        eng.addWidget(self.engine, 1)
        bl.addLayout(eng)
        lay.addWidget(self.body)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ feeding frames
    def begin(self, total: int, fps: float):
        """A new draft is starting; keep showing the old one until its first frame arrives."""
        self.total = max(1, total)
        self.fps = max(1.0, fps)
        self.rendering = True
        self._pending_reset = True
        self.view.fraction = 0.001
        self.set_status("Building the scene…")

    def add_frame(self, path: str):
        m = _NUM.search(path)
        idx = int(m.group(1)) if m else len(self.order)
        pix = QPixmap(path)
        if pix.isNull():
            return
        if getattr(self, "_pending_reset", False):
            self.frames.clear()
            self.order.clear()
            self.i = 0
            self._pending_reset = False
        self.frames[idx] = pix.scaled(960, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.order = sorted(self.frames)
        self.scrub.setRange(0, max(0, self.total - 1))
        self.view.fraction = len(self.order) / self.total
        if self.playing and not self._timer.isActive():
            self._start_timer()
        if len(self.order) == 1:
            self._show(0)

    def finish(self, ok: bool, message: str = ""):
        self.rendering = False
        self.view.fraction = 1.0 if ok else self.view.fraction
        if ok:
            self.set_status("")
        else:
            self.set_status(message)

    def set_status(self, text: str):
        self.view.text = text
        self.view.update()

    # ------------------------------------------------------------------ playback
    def toggle_play(self):
        self.playing = not self.playing
        self.play_btn.setText("❚❚" if self.playing else "▶")
        if self.playing:
            self._start_timer()
        else:
            self._timer.stop()

    def _start_timer(self):
        self._timer.start(int(1000 / self.fps))

    def _tick(self):
        if not self.order:
            return
        # loop over what has rendered so far; once complete, over the whole move
        n = len(self.order)
        self.i = (self.i + 1) % n
        self._show(self.i)

    def _show(self, k: int):
        if not self.order:
            return
        k = max(0, min(len(self.order) - 1, k))
        self.i = k
        idx = self.order[k]
        self.view.pix = self.frames[idx]
        self.scrub.blockSignals(True)
        self.scrub.setValue(k)
        self.scrub.blockSignals(False)
        self.time_lbl.setText(f"{k / self.fps:.1f} s")
        self.view.update()

    def _scrubbed(self, v: int):
        self._show(v)

    def _fold(self, open_: bool):
        self.body.setVisible(open_)
        self.fold.setText(("▾" if open_ else "▸") + "  Draft preview")
