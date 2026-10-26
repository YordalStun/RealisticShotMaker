"""3D view of the camera path: the set as simple shaded shapes, the photos, and the camera's route through it.

Drag to orbit, right-drag to pan, scroll to zoom, double-click to reset. Each shot of the shot list has its own
colour (the same as in the shot strip); cuts are marked where the camera jumps. The scrubber moves a camera
along the path, and 'Look through camera' shows the view from it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from .. import catalog
from .shot_timeline import SHOT_COLOURS

FACES = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2))
LIGHT = (0.35, -0.55, 0.76)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _mean(pts):
    k = 1.0 / len(pts)
    return (sum(p[0] for p in pts) * k, sum(p[1] for p in pts) * k, sum(p[2] for p in pts) * k)


class PathView(QWidget):
    frame_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.frame = 0
        self.through_camera = False
        self.highlight = -1            # the shot being edited: drawn bolder
        self.hero_img: QImage | None = None
        self.imgs: dict[int, QImage] = {}     # every photo's picture, so the wall of frames reads in 3D
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(240)
        self.setMouseTracking(False)
        self._last = None
        self._button = None
        self.reset_view()

    # ------------------------------------------------------------------ data
    def set_data(self, data: dict):
        first = self.data is None
        self.data = data
        self.frame = min(self.frame, len(data["frames"]) - 1)
        self.hero_img = None
        self.imgs = {}
        for i, p in enumerate(data.get("prints", [])):
            if p.get("image") and Path(p["image"]).exists():
                img = QImage(p["image"])
                if not img.isNull():
                    img = img.scaledToWidth(min(512 if p.get("hero") else 192, img.width()), Qt.SmoothTransformation)
                    self.imgs[i] = img
                    if p.get("hero"):
                        self.hero_img = img
        if first:
            self.reset_view()
        self.update()

    def reset_view(self):
        """Look at the action: centre on the photo, back far enough to see the whole path."""
        self.yaw, self.pitch = math.radians(-120), math.radians(28)
        self.target = (0.0, 0.3, 0.8)
        self.dist = 2.4
        if self.data:
            hero = next((p for p in self.data.get("prints", []) if p.get("hero")), None)
            pts = [tuple(f["p"]) for f in self.data["frames"]]
            if hero:
                self.target = _mean([tuple(c) for c in hero["quad"]])
            span = max(math.dist(self.target, p) for p in pts) if pts else 1.0
            self.dist = max(0.6, span * 2.4)
            f0 = self.data["frames"][0]
            back = _norm(_sub(tuple(f0["p"]), self.target))
            self.yaw = math.atan2(back[1], back[0]) - math.radians(35)
        self.update()

    # ------------------------------------------------------------------ projection
    def _eye_basis(self):
        if self.through_camera and self.data:
            f = self.data["frames"][self.frame]
            eye, fwd, up = tuple(f["p"]), _norm(tuple(f["f"])), _norm(tuple(f["u"]))
            right = _norm(_cross(fwd, up))
            up = _cross(right, fwd)
            # fit the camera's horizontal field of view to the widget's width
            fov_h = f["fov"]
            focal = (self.width() / 2) / math.tan(fov_h / 2)
            return eye, right, up, fwd, focal
        cp = math.cos(self.pitch)
        back = (cp * math.cos(self.yaw), cp * math.sin(self.yaw), math.sin(self.pitch))
        eye = _add(self.target, _mul(back, self.dist))
        fwd = _mul(back, -1)
        right = _norm(_cross(fwd, (0, 0, 1)))
        up = _cross(right, fwd)
        focal = (self.height() / 2) / math.tan(math.radians(45) / 2)
        return eye, right, up, fwd, focal

    def _project(self, basis, p):
        eye, right, up, fwd, focal = basis
        v = _sub(p, eye)
        z = _dot(v, fwd)
        if z < 0.02:
            return None, z
        x, y = _dot(v, right), _dot(v, up)
        return QPointF(self.width() / 2 + focal * x / z, self.height() / 2 - focal * y / z), z

    # ------------------------------------------------------------------ drawing
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#16130f"))
        if not self.data:
            p.setPen(QColor("#9d9184"))
            p.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap,
                       "The camera's route through the set shows here.\nPress Update path (it takes a few "
                       "seconds to build the set).")
            p.end()
            return
        basis = self._eye_basis()
        eye = basis[0]
        polys = []
        light = _norm(LIGHT)
        for b in self.data["boxes"]:
            cs = [tuple(c) for c in b["c"]]
            centre = _mean(cs)
            name = b.get("name", "")
            for face in FACES:
                pts = [cs[i] for i in face]
                fc = _mean(pts)
                n = _norm(_sub(fc, centre))
                facing = _dot(n, _sub(eye, fc)) > 0
                if b.get("room"):
                    # doll's-house view: see into the room through the walls nearest to us; no ceiling
                    if "Ceiling" in name or facing:
                        continue
                    shade = 0.55 + 0.25 * max(0.0, _dot(_mul(n, -1), light))
                else:
                    if not facing:
                        continue
                    shade = 0.45 + 0.55 * max(0.0, _dot(n, light))
                proj = [self._project(basis, q) for q in pts]
                if any(q[0] is None for q in proj):
                    continue
                depth = sum(q[1] for q in proj) / 4
                col = QColor.fromRgbF(*[min(1.0, max(0.0, c * shade)) for c in b["col"]])
                polys.append((depth, QPolygonF([q[0] for q in proj]), col, b.get("room")))
        for i, pr in enumerate(self.data.get("prints", [])):
            proj = [self._project(basis, tuple(c)) for c in pr["quad"]]
            if any(q[0] is None for q in proj):
                continue
            depth = sum(q[1] for q in proj) / 4 - 0.002
            polys.append((depth, QPolygonF([q[0] for q in proj]), "hero" if pr.get("hero") else "print", i))
        polys.sort(key=lambda x: -x[0])
        for depth, poly, col, extra in polys:     # extra: room flag for boxes, index for photos
            if col == "hero":
                self._draw_hero(p, poly)
            elif col == "print":
                p.setPen(QPen(QColor("#2a2622"), 1))
                p.setBrush(QBrush(QColor("#ece6da")))
                p.drawPolygon(poly)
                self._draw_image(p, poly, self.imgs.get(extra))
            else:
                p.setPen(QPen(col.darker(140), 0.6) if not extra else QPen(Qt.NoPen))
                p.setBrush(QBrush(col))
                p.drawPolygon(poly)
        if not self.through_camera:
            self._draw_path(p, basis)
        else:
            self._draw_frame_guides(p)
        p.end()

    def _draw_hero(self, p: QPainter, poly: QPolygonF):
        p.setPen(QPen(QColor("#f4ece0"), 1.5))
        p.setBrush(QBrush(QColor("#f4ece0")))
        p.drawPolygon(poly)
        self._draw_image(p, poly, self.hero_img)

    def _draw_image(self, p: QPainter, poly: QPolygonF, img: QImage | None):
        if img is None:
            return
        src = QPolygonF([QPointF(0, img.height()), QPointF(img.width(), img.height()),
                         QPointF(img.width(), 0), QPointF(0, 0)])
        t = QTransform()
        if QTransform.quadToQuad(src, poly, t):
            p.save()
            p.setTransform(t, True)
            p.drawImage(0, 0, img)
            p.restore()

    def _draw_path(self, p: QPainter, basis):
        frames = self.data["frames"]
        prev = None
        cut_no = 0
        for i, f in enumerate(frames):
            q, _ = self._project(basis, tuple(f["p"]))
            col = QColor(SHOT_COLOURS[f["shot"] % len(SHOT_COLOURS)])
            if prev is not None and q is not None:
                cut = frames[i - 1]["shot"] != f["shot"]
                if cut:
                    cut_no += 1
                    pen = QPen(QColor("#f4ece0"), 1.2, Qt.DashLine)
                    p.setPen(pen)
                    p.drawLine(prev, q)
                    p.setBrush(QBrush(QColor("#f4ece0")))
                    p.drawEllipse(q, 4, 4)
                    p.drawText(q + QPointF(6, -6), f"cut {cut_no}")
                else:
                    p.setPen(QPen(col, 6 if f["shot"] == self.highlight else 2.5, Qt.SolidLine, Qt.RoundCap))
                    p.drawLine(prev, q)
            prev = q
        step = max(1, len(frames) // 14)
        for i in range(0, len(frames), step):
            self._draw_camera(p, basis, frames[i], 0.035, QColor(SHOT_COLOURS[frames[i]["shot"] % len(SHOT_COLOURS)]), 1)
        cur = frames[self.frame]
        self._draw_camera(p, basis, cur, 0.07, QColor("#ffffff"), 2, focus=True)

    def _draw_camera(self, p, basis, f, size, col, width, focus=False):
        """A little camera: a pyramid showing which way it looks and how wide."""
        pos, fwd, up = tuple(f["p"]), _norm(tuple(f["f"])), _norm(tuple(f["u"]))
        right = _norm(_cross(fwd, up))
        up = _cross(right, fwd)
        aspect = self.data.get("aspect", 16 / 9)
        hw = math.tan(f["fov"] / 2) * size
        hh = hw / aspect
        tip = pos
        base = _add(pos, _mul(fwd, size))
        corners = [_add(_add(base, _mul(right, sx * hw)), _mul(up, sy * hh)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        pt, _ = self._project(basis, tip)
        pc = [self._project(basis, c)[0] for c in corners]
        if pt is None or any(c is None for c in pc):
            return
        p.setPen(QPen(col, width))
        p.setBrush(QBrush(Qt.NoBrush))
        for c in pc:
            p.drawLine(pt, c)
        p.drawPolygon(QPolygonF(pc))
        if focus:
            fp, _ = self._project(basis, _add(pos, _mul(fwd, f["fd"])))
            if fp is not None:
                p.setPen(QPen(QColor("#ffffff"), 1, Qt.DotLine))
                p.drawLine(pt, fp)
                p.setBrush(QBrush(QColor("#ff5050")))
                p.setPen(QPen(Qt.NoPen))
                p.drawEllipse(fp, 3.5, 3.5)

    def _draw_frame_guides(self, p: QPainter):
        """Looking through the camera: show the frame edges for the output aspect ratio."""
        aspect = self.data.get("aspect", 16 / 9)
        w = self.width()
        h = w / aspect
        y0 = (self.height() - h) / 2
        shade = QColor(0, 0, 0, 170)
        p.fillRect(QRectF(0, 0, w, y0), shade)
        p.fillRect(QRectF(0, y0 + h, w, self.height() - y0 - h), shade)
        p.setPen(QPen(QColor("#f4ece0"), 1))
        p.setBrush(QBrush(Qt.NoBrush))
        p.drawRect(QRectF(0.5, y0, w - 1, h))

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, ev):
        self._last = ev.position()
        self._button = ev.button()

    def mouseMoveEvent(self, ev):
        if self._last is None or self.through_camera:
            return
        d = ev.position() - self._last
        self._last = ev.position()
        if self._button == Qt.LeftButton:
            self.yaw -= d.x() * 0.01
            self.pitch = max(math.radians(-10), min(math.radians(89), self.pitch + d.y() * 0.01))
        else:
            eye, right, up, fwd, focal = self._eye_basis()
            k = self.dist / focal
            self.target = _add(self.target, _add(_mul(right, -d.x() * k), _mul(up, d.y() * k)))
        self.update()

    def mouseReleaseEvent(self, ev):
        self._last = None

    def wheelEvent(self, ev):
        if not self.through_camera:
            self.dist = max(0.15, min(30.0, self.dist * (0.9 if ev.angleDelta().y() > 0 else 1.1)))
            self.update()

    def mouseDoubleClickEvent(self, ev):
        self.reset_view()

    def set_frame(self, i: int):
        if self.data:
            self.frame = max(0, min(len(self.data["frames"]) - 1, i))
            self.update()


class PathPanel(QWidget):
    """The 3D view with its controls: update, auto-update, scrubber, play and look-through-camera."""
    update_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Caption")
        self.auto = QCheckBox("Update as I edit")
        self.auto.setChecked(True)
        self.update_btn = QPushButton("Update path")
        self.update_btn.clicked.connect(self.update_requested)
        self.through = QCheckBox("Look through camera")
        self.through.toggled.connect(self._through)
        head.addWidget(self.status, 1)
        head.addWidget(self.through)
        head.addWidget(self.auto)
        head.addWidget(self.update_btn)
        lay.addLayout(head)
        self.view = PathView()
        lay.addWidget(self.view, 1)
        ctl = QHBoxLayout()
        self.play_btn = QToolButton()
        self.play_btn.setText("▶")
        self.play_btn.setFixedWidth(30)
        self.play_btn.clicked.connect(self._toggle_play)
        self.scrub = QSlider(Qt.Horizontal)
        self.scrub.setRange(0, 0)
        self.scrub.valueChanged.connect(self._scrubbed)
        self.frame_lbl = QLabel("")
        self.frame_lbl.setObjectName("Caption")
        self.frame_lbl.setMinimumWidth(230)
        ctl.addWidget(self.play_btn)
        ctl.addWidget(self.scrub, 1)
        ctl.addWidget(self.frame_lbl)
        lay.addLayout(ctl)
        hint = QLabel("Drag to orbit · right-drag to pan · scroll to zoom · double-click to reset")
        hint.setObjectName("Caption")
        lay.addWidget(hint)
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.scrub.setValue((self.scrub.value() + 1) % (self.scrub.maximum() + 1)))

    def load(self, path: str):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.status.setText(f"Couldn't read the camera path: {exc}")
            return
        self.view.set_data(data)
        self.scrub.setRange(0, len(data["frames"]) - 1)
        self.fps = float(data.get("fps", 24))
        self._scrubbed(self.scrub.value())
        n = len(data.get("shots", []))
        self.status.setText(f"{len(data['frames'])} frames · {n} shot{'s' if n != 1 else ''}"
                            + (f" · {n - 1} cut{'s' if n > 2 else ''}" if n > 1 else ""))

    def _scrubbed(self, v: int):
        self.view.set_frame(v)
        d = self.view.data
        if not d:
            return
        f = d["frames"][self.view.frame]
        shot = d["shots"][f["shot"]] if d.get("shots") else {"move": ""}
        name = catalog.option_name(catalog.MOVES, shot["move"]) if shot["move"] else ""
        t = self.view.frame / max(1.0, float(d.get("fps", 24)))
        self.frame_lbl.setText(f"{t:.1f} s · shot {f['shot'] + 1}: {name}")

    def _toggle_play(self):
        if self._timer.isActive():
            self._timer.stop()
            self.play_btn.setText("▶")
        elif self.view.data:
            self._timer.start(int(1000 / max(1.0, getattr(self, "fps", 24.0))))
            self.play_btn.setText("❚❚")

    def show_shot(self, index: int):
        """Highlight a shot's stretch of the path and move the scrubber to its first frame."""
        self.view.highlight = index
        d = self.view.data
        if d:
            first = next((i for i, f in enumerate(d["frames"]) if f["shot"] == index), None)
            if first is not None:
                self.scrub.setValue(first)
        self.view.update()

    def _through(self, on: bool):
        self.view.through_camera = on
        self.view.update()
