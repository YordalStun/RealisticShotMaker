"""Floating player that loops a camera move's preview clip while the mouse is over it."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QWidget

from .. import catalog
from ..previews import frames_for

W, H = 427, 240  # shown at half size; the clips themselves are 854×480


class PreviewPopup(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(W, H + 26)
        self._frames: list[QPixmap] = []
        self._i = 0
        self._move = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next)
        self._cache: dict[str, list[QPixmap]] = {}

    def show_move(self, move: str, anchor: QPoint):
        if move != self._move:
            self._move = move
            self._frames = self._load(move)
            self._i = 0
            fps = 24.0
            frames = frames_for(move)
            if frames:
                info = frames[0].parent / "info.json"
                try:
                    fps = float(json.loads(info.read_text())["fps"])
                except Exception:
                    pass
            self._timer.start(int(1000 / max(1.0, fps)))
        self.move(anchor)
        self.show()
        self.raise_()
        self.update()

    def hide_preview(self):
        self._timer.stop()
        self._move = ""
        self.hide()

    def _load(self, move: str) -> list[QPixmap]:
        if move not in self._cache:
            pix = []
            for f in frames_for(move):
                p = QPixmap(str(f))
                if not p.isNull():
                    pix.append(p.scaled(W, H, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self._cache[move] = pix
        return self._cache[move]

    def forget(self):
        self._cache.clear()

    def _next(self):
        if self._frames:
            self._i = (self._i + 1) % len(self._frames)
            self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0f0e0d"))
        if self._frames:
            p.drawPixmap(0, 0, self._frames[self._i % len(self._frames)])
        else:
            p.setPen(QColor("#9d9184"))
            p.drawText(self.rect().adjusted(16, 0, -16, -26), Qt.AlignCenter | Qt.TextWordWrap,
                       "No preview for this move yet.\nUse Blender → Build shot previews to render them on "
                       "your graphics card.")
        p.setPen(QColor("#efe5d8"))
        f = QFont()
        f.setPointSize(9)
        p.setFont(f)
        name = catalog.option_name(catalog.MOVES, self._move)
        p.drawText(self.rect().adjusted(10, H + 2, -10, 0), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setPen(QColor("#36312c"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class MoveHoverWatcher(QObject):
    """Wires a camera-move combo box to the popup: hovering the list items or the closed box plays clips."""

    def __init__(self, combo: QComboBox, popup: PreviewPopup):
        super().__init__(combo)
        self.combo = combo
        self.popup = popup
        view = combo.view()
        view.setMouseTracking(True)
        view.entered.connect(self._item_hovered)
        combo.installEventFilter(self)
        view.installEventFilter(self)
        view.window().installEventFilter(self)

    def _anchor(self) -> QPoint:
        view = self.combo.view()
        if view.isVisible():
            g = view.mapToGlobal(QPoint(view.width() + 8, 0))
        else:
            g = self.combo.mapToGlobal(QPoint(self.combo.width() + 8, 0))
        return g

    def _item_hovered(self, index):
        move = index.data(Qt.UserRole)
        if move:
            self.popup.show_move(move, self._anchor())

    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is self.combo and t == QEvent.Enter and not self.combo.view().isVisible():
            self.popup.show_move(self.combo.currentData(), self._anchor())
        elif obj is self.combo and t == QEvent.Leave and not self.combo.view().isVisible():
            self.popup.hide_preview()
        elif t == QEvent.Hide and obj is self.combo.view().window():
            self.popup.hide_preview()
        return False
