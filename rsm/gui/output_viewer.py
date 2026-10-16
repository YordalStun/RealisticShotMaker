"""Render output: the real frames of a queued render, shown as they finish and playable back.

Follows the newest frame while a shot renders (with the sample count of the frame in progress), or plays
and scrubs through everything rendered so far. Uses the small preview copies Blender writes next to the
job, falling back to the full frames for renders made before those existed.
"""
from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from .draft_player import _FrameView

_NUM = re.compile(r"frame_(\d+)\.png$")
CACHE = 96   # frames kept decoded (960×540 previews: ~2 MB each)


class OutputViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item = None
        self.dirs: list[Path] = []
        self.frames: list[tuple[int, str]] = []     # (frame number, path), sorted
        self.cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.total = 0
        self.fps = 24.0
        self.i = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.title = QLabel("Render output")
        self.title.setObjectName("SectionTitle")
        self.status = QLabel("")
        self.status.setObjectName("Caption")
        self.sample_bar = QProgressBar()
        self.sample_bar.setRange(0, 1000)
        self.sample_bar.setFixedWidth(150)
        self.sample_bar.setTextVisible(True)
        self.sample_bar.setToolTip("Progress of the frame being rendered right now")
        self.sample_bar.hide()
        head.addWidget(self.title)
        head.addWidget(self.status, 1)
        head.addWidget(self.sample_bar)
        lay.addLayout(head)

        self.view = _FrameView(fixed_aspect=False)
        self.view.setMinimumHeight(200)
        self.view.text = ("The real frames of a render appear here as they finish.\n"
                          "Select a shot in the render queue to look through its output.")
        lay.addWidget(self.view, 1)

        ctl = QHBoxLayout()
        self.play_btn = QToolButton()
        self.play_btn.setText("▶")
        self.play_btn.setFixedWidth(30)
        self.play_btn.setToolTip("Play the frames rendered so far")
        self.play_btn.clicked.connect(self.toggle_play)
        self.scrub = QSlider(Qt.Horizontal)
        self.scrub.setRange(0, 0)
        self.scrub.valueChanged.connect(self._scrubbed)
        self.frame_lbl = QLabel("–")
        self.frame_lbl.setObjectName("Caption")
        self.frame_lbl.setMinimumWidth(120)
        self.follow = QCheckBox("Follow newest")
        self.follow.setChecked(True)
        self.follow.setToolTip("Jump to each frame as soon as it's rendered")
        self.open_btn = QPushButton("Open frames folder")
        self.open_btn.clicked.connect(self._open_folder)
        ctl.addWidget(self.play_btn)
        ctl.addWidget(self.scrub, 1)
        ctl.addWidget(self.frame_lbl)
        ctl.addWidget(self.follow)
        ctl.addWidget(self.open_btn)
        lay.addLayout(ctl)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._poll = QTimer(self)      # picks up frames written while nobody was watching (e.g. after a restart)
        self._poll.timeout.connect(self.rescan)
        self._poll.start(4000)

    # ------------------------------------------------------------------ which shot
    def show_item(self, item):
        if item is self.item:
            return
        self.item = item
        self.cache.clear()
        self.frames = []
        self.dirs = []
        self.i = 0
        self._stop()
        if item is None:
            self.title.setText("Render output")
            self.view.pix = None
            self.view.text = ("The real frames of a render appear here as they finish.\n"
                              "Select a shot in the render queue to look through its output.")
            self._labels()
            self.view.update()
            return
        self.title.setText(f"Render output · {item.title}")
        self.fps = float(item.spec.output.fps or 24.0)
        self.total = item.total_frames
        self._find_dirs()
        self.rescan()
        if not self.frames:
            self.view.pix = None
            self.view.text = ("No frames yet. They appear here as soon as each one is rendered."
                              if item.state in ("waiting", "running") else "This shot has no rendered frames.")
            self.view.update()
        else:
            self._show(len(self.frames) - 1)
        self.update_progress(item)

    def _find_dirs(self):
        jp = getattr(self.item, "job_path", None)
        if not jp or not os.path.exists(jp):
            return
        try:
            job = json.loads(Path(jp).read_text(encoding="utf-8"))
            frames = Path(job["paths"]["frames"])
        except (OSError, ValueError, KeyError):
            return
        self.dirs = [frames.parent / "thumbs", frames]

    def rescan(self):
        if self.item is None:
            return
        if not self.dirs:
            self._find_dirs()
        found: dict[int, str] = {}
        for d in reversed(self.dirs):        # thumbs win over full frames
            if d.is_dir():
                for f in d.iterdir():
                    m = _NUM.search(f.name)
                    if m:
                        found[int(m.group(1))] = str(f)
        frames = sorted(found.items())
        if len(frames) != len(self.frames):
            grew = len(frames) > len(self.frames)
            self.frames = frames
            self.scrub.setRange(0, max(0, len(frames) - 1))
            if grew and self.follow.isChecked() and not self._timer.isActive():
                self._show(len(frames) - 1)
            self._labels()

    # ------------------------------------------------------------------ live updates from the queue
    def frame_arrived(self, item, path: str):
        if item is not self.item:
            return
        if not self.dirs:
            self._find_dirs()
        self.rescan()

    def update_progress(self, item):
        if item is not self.item or item is None:
            return
        self.total = item.total_frames or self.total
        job = getattr(item, "job", None)
        p = getattr(job, "progress", None) if job else None
        if item.state == "running" and p is not None and p.samples:
            self.sample_bar.show()
            self.sample_bar.setValue(int(1000 * p.sample / max(1, p.samples)))
            self.sample_bar.setFormat(f"sample {p.sample}/{p.samples}")
        else:
            self.sample_bar.hide()
        self.status.setText(item.message if item.state == "running" else "")
        self._labels()

    # ------------------------------------------------------------------ playback
    def toggle_play(self):
        if self._timer.isActive():
            self._stop()
        elif self.frames:
            self.follow.setChecked(False)
            self._timer.start(int(1000 / max(1.0, self.fps)))
            self.play_btn.setText("❚❚")

    def _stop(self):
        self._timer.stop()
        self.play_btn.setText("▶")

    def _tick(self):
        if self.frames:
            self._show((self.i + 1) % len(self.frames))

    def _scrubbed(self, v: int):
        if v != self.i:
            self.follow.setChecked(False)
            self._show(v)

    def _pixmap(self, path: str) -> QPixmap | None:
        pix = self.cache.get(path)
        if pix is None:
            pix = QPixmap(path)
            if pix.isNull():
                return None
            if pix.width() > 1280:     # a full-size frame (older render): keep a screen-sized copy
                pix = pix.scaled(1280, 720, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cache[path] = pix
            while len(self.cache) > CACHE:
                self.cache.popitem(last=False)
        else:
            self.cache.move_to_end(path)
        return pix

    def _show(self, k: int):
        if not self.frames:
            return
        k = max(0, min(len(self.frames) - 1, k))
        self.i = k
        pix = self._pixmap(self.frames[k][1])
        if pix is not None:
            self.view.pix = pix
            self.view.text = ""
        self.scrub.blockSignals(True)
        self.scrub.setValue(k)
        self.scrub.blockSignals(False)
        self._labels()
        self.view.update()

    def _labels(self):
        if not self.frames:
            self.frame_lbl.setText(f"0 of {self.total} rendered" if self.total else "–")
            return
        num = self.frames[self.i][0]
        self.frame_lbl.setText(f"Frame {num} · {len(self.frames)} of {self.total or len(self.frames)} rendered")
        self.view.fraction = len(self.frames) / self.total if self.total and len(self.frames) < self.total else 0.0

    def _open_folder(self):
        from .render_queue import _open_path
        target = next((str(d) for d in reversed(self.dirs) if d.is_dir()), None)
        if target:
            _open_path(target)
