"""Reusable Qt widgets."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QSlider, QWidget)


class ImageView(QLabel):
    """Shows an image scaled to fit, letterboxed on a dark background."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._placeholder = placeholder
        self.setMinimumSize(240, 135)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("ImageView")

    def set_image(self, img: QImage | QPixmap | str | None):
        if img is None:
            self._pix = None
        elif isinstance(img, str):
            self._pix = QPixmap(img)
        elif isinstance(img, QImage):
            self._pix = QPixmap.fromImage(img)
        else:
            self._pix = img
        self.update()

    def set_placeholder(self, text: str):
        self._placeholder = text
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0f0e0d"))
        if self._pix and not self._pix.isNull():
            scaled = self._pix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        elif self._placeholder:
            p.setPen(QColor("#8a8076"))
            p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap, self._placeholder)
        p.end()

    def sizeHint(self):
        return QSize(960, 540)


class SliderField(QWidget):
    """Slider + number box for a float value."""
    valueChanged = Signal(float)

    def __init__(self, minimum: float, maximum: float, step: float = 0.01, suffix: str = "", parent=None):
        super().__init__(parent)
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self.steps = max(1, int(round((maximum - minimum) / step)))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.steps)
        self.box = QDoubleSpinBox()
        decimals = 0 if step >= 1 else (1 if step >= 0.1 else 2)
        self.box.setDecimals(decimals)
        self.box.setRange(minimum, maximum)
        self.box.setSingleStep(step)
        self.box.setSuffix(suffix)
        self.box.setFixedWidth(84)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.box)
        self.slider.valueChanged.connect(self._from_slider)
        self.box.valueChanged.connect(self._from_box)
        self._block = False

    def _from_slider(self, i):
        if self._block:
            return
        v = self.minimum + i * (self.maximum - self.minimum) / self.steps
        self._block = True
        self.box.setValue(v)
        self._block = False
        self.valueChanged.emit(v)

    def _from_box(self, v):
        if self._block:
            return
        self._block = True
        self.slider.setValue(int(round((v - self.minimum) / (self.maximum - self.minimum) * self.steps)))
        self._block = False
        self.valueChanged.emit(v)

    def setValue(self, v: float):
        self._block = True
        self.box.setValue(v)
        self.slider.setValue(int(round((v - self.minimum) / (self.maximum - self.minimum) * self.steps)))
        self._block = False

    def value(self) -> float:
        return self.box.value()


class PhotoPicker(QWidget):
    """Choose a built-in sample picture or load your own file."""
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        for value, label in options:
            self.combo.addItem(label, value)
        self.btn = QPushButton("Your photo…")
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.btn)
        self.combo.currentIndexChanged.connect(lambda _: self.changed.emit(self.combo.currentData()))
        self.btn.clicked.connect(self._browse)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a photo", "",
                                              "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp *.heic)")
        if path:
            self.set_value(path)
            self.changed.emit(path)

    def set_value(self, value: str):
        idx = self.combo.findData(value)
        if idx < 0:
            import os
            self.combo.addItem(f"Your photo: {os.path.basename(value)}", value)
            idx = self.combo.count() - 1
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)


class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, color="#232c5e", parent=None):
        super().__init__(parent)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, color: str):
        self._color = color
        self.setText(color)
        self.setStyleSheet(f"QPushButton {{ background: {color}; color: white; border-radius: 4px; padding: 4px; }}")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Ink colour")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(c.name())


class FolderPicker(QWidget):
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.label.setObjectName("PathLabel")
        self.btn = QPushButton("Choose…")
        lay.addWidget(self.label, 1)
        lay.addWidget(self.btn)
        self.btn.clicked.connect(self._browse)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save renders to")
        if d:
            self.set_value(d)
            self.changed.emit(d)

    def set_value(self, v: str):
        self.label.setText(v or "Videos\\RealisticShotMaker (default)")
