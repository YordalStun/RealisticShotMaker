"""The shot list as a timeline strip: one block per shot (width = its length), drag the cut lines between them,
click a shot to edit its own camera settings."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .. import catalog

# shot colours (also used by the 3D path view, so a shot looks the same in both)
SHOT_COLOURS = ["#d08a3a", "#4f9bd9", "#7cc06b", "#c56bd1", "#e0c24f", "#e06666", "#59c9b8", "#a0a0ff"]
MIN_LEN = 0.25   # seconds


class ShotStrip(QWidget):
    selected = Signal(int)
    lengths_changed = Signal(list)     # new lengths in seconds (total unchanged)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.shots: list[dict] = []
        self.sel = 0
        self._drag = -1                # index of the cut line being dragged (between shot i and i+1)
        self.setMinimumHeight(54)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_shots(self, shots: list[dict], sel: int):
        self.shots = shots
        self.sel = max(0, min(sel, len(shots) - 1))
        self.update()

    def _total(self):
        return sum(s["length"] for s in self.shots) or 1.0

    def _edges(self) -> list[float]:
        """x position of every shot boundary, including both ends."""
        w = self.width() - 2
        xs, acc = [1.0], 0.0
        for s in self.shots:
            acc += s["length"]
            xs.append(1.0 + w * acc / self._total())
        return xs

    def _cut_near(self, x: float) -> int:
        xs = self._edges()
        for i in range(1, len(xs) - 1):
            if abs(xs[i] - x) <= 6:
                return i - 1
        return -1

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        xs = self._edges()
        h = self.height() - 2
        f = QFont()
        f.setPointSize(8)
        p.setFont(f)
        for i, s in enumerate(self.shots):
            r = QRectF(xs[i] + 1, 1, xs[i + 1] - xs[i] - 2, h)
            c = QColor(SHOT_COLOURS[i % len(SHOT_COLOURS)])
            fill = QColor(c)
            fill.setAlpha(235 if i == self.sel else 120)
            p.setBrush(fill)
            p.setPen(QPen(QColor("#f4ece0") if i == self.sel else QColor("#2a2622"), 2 if i == self.sel else 1))
            p.drawRoundedRect(r, 5, 5)
            p.setPen(QColor("#141210"))
            name = catalog.option_name(catalog.MOVES, s["move"])
            label = f"{i + 1}  {name}\n{s['length']:.1f} s · {s.get('focal_mm', 0):.0f} mm · f/{s.get('fstop', 0):g}"
            p.drawText(r.adjusted(6, 3, -4, -3), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, label)
        p.setPen(QPen(QColor("#f4ece0"), 2))
        for x in xs[1:-1]:
            p.drawLine(int(x), 0, int(x), h + 1)
        p.end()

    def mousePressEvent(self, ev):
        x = ev.position().x()
        self._drag = self._cut_near(x)
        if self._drag >= 0:
            return
        xs = self._edges()
        for i in range(len(self.shots)):
            if xs[i] <= x <= xs[i + 1]:
                self.sel = i
                self.selected.emit(i)
                self.update()
                return

    def mouseMoveEvent(self, ev):
        x = ev.position().x()
        if self._drag < 0:
            self.setCursor(Qt.SplitHCursor if self._cut_near(x) >= 0 else Qt.ArrowCursor)
            return
        i = self._drag
        xs = self._edges()
        w = self.width() - 2
        pair = self.shots[i]["length"] + self.shots[i + 1]["length"]
        left_x = xs[i]
        new_a = (x - left_x) / w * self._total()
        new_a = max(MIN_LEN, min(pair - MIN_LEN, new_a))
        self.shots[i]["length"] = round(new_a, 2)
        self.shots[i + 1]["length"] = round(pair - new_a, 2)
        self.update()

    def mouseReleaseEvent(self, ev):
        if self._drag >= 0:
            self._drag = -1
            self.lengths_changed.emit([s["length"] for s in self.shots])


class ShotListEditor(QWidget):
    """Timeline + buttons. The camera fields below it edit whichever shot is selected."""
    cut_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.strip = ShotStrip()
        lay.addWidget(self.strip)
        row = QHBoxLayout()
        self.info = QLabel("")
        self.info.setObjectName("Caption")
        self.info.setWordWrap(True)
        self.cut_btn = QPushButton("Add a cut")
        self.cut_btn.setToolTip("Cut the selected shot in two. The new shot starts as a copy; then change its "
                                "move, framing or lens.")
        self.cut_btn.clicked.connect(self.cut_requested)
        self.rm_btn = QPushButton("Remove shot")
        self.rm_btn.setToolTip("Remove the selected shot; its time goes to the shot before it.")
        self.rm_btn.clicked.connect(self.remove_requested)
        row.addWidget(self.info, 1)
        row.addWidget(self.cut_btn)
        row.addWidget(self.rm_btn)
        lay.addLayout(row)

    def set_shots(self, shots: list[dict], sel: int):
        self.strip.set_shots(shots, sel)
        self.rm_btn.setEnabled(len(shots) > 1)
        if len(shots) > 1:
            self.info.setText(f"Editing shot {self.strip.sel + 1} of {len(shots)}: the camera settings below "
                              "apply to this shot only. Drag the white lines to move the cuts.")
        else:
            self.info.setText("One continuous shot. Add a cut to change the move, framing or lens part-way "
                              "through.")
