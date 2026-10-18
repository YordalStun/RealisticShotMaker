"""RealisticShotMaker Render Server: a small window that sits on a rendering machine and works through packs.

Drop .rsmpack files (exported from the main program) into the watch folder (a network share works) or onto
the window. Each one is unpacked, queued and rendered in turn; the window shows the queue, progress and the
real frames as they finish. The queue is saved, so after a restart it carries on where it stopped.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..blender_locator import find_blender
from ..pack import EXT, import_pack
from ..paths import app_data_dir, default_output_dir, settings as _settings
from .output_viewer import OutputViewer
from .render_queue import QueuePanel, RenderQueue


class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealisticShotMaker Render Server")
        self.settings = _settings()
        self.blender = self.settings.value("blender_path", "") or os.environ.get("RSM_BLENDER", "")
        if not (self.blender and os.path.exists(self.blender)):
            self.blender = find_blender()[0] or ""
        root = app_data_dir() / "server"
        self.watch = Path(self.settings.value("server_watch", "") or (root / "Drop packs here"))
        self.out_root = Path(self.settings.value("server_output", "") or (default_output_dir() / "Server"))
        self.unpacked = root / "packs"
        for d in (self.watch, self.out_root, self.unpacked):
            d.mkdir(parents=True, exist_ok=True)
        self.rq = RenderQueue(lambda: self.blender if self.blender and os.path.exists(self.blender) else "",
                              root / "queue.json", self)
        self.rq.active = True    # a server just gets on with it

        top = QHBoxLayout()
        self.watch_lbl = QLabel()
        self.watch_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.watch_lbl.setWordWrap(True)
        b_watch = QPushButton("Watch folder…")
        b_watch.clicked.connect(self._pick_watch)
        b_out = QPushButton("Output folder…")
        b_out.clicked.connect(self._pick_out)
        b_add = QPushButton("Add pack…")
        b_add.clicked.connect(self._add_dialog)
        top.addWidget(self.watch_lbl, 1)
        for b in (b_add, b_watch, b_out):
            top.addWidget(b)

        self.viewer = OutputViewer()
        self.panel = QueuePanel(self.rq)
        self.panel.btns["load"].hide()       # no editor on the server
        self.panel.btns["regrade"].hide()
        self.panel.selected_changed.connect(lambda it: it is not None and self.viewer.show_item(it))
        self.rq.frame_ready.connect(self._frame)
        self.rq.progressed.connect(self._progress)
        self.rq.changed.connect(lambda: self.viewer.update_progress(self.viewer.item))

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.viewer)
        split.addWidget(self.panel)
        split.setSizes([520, 300])
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.setAcceptDrops(True)
        self.resize(1180, 900)
        self._labels()

        self._seen: dict[str, tuple[float, int]] = {}
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan_watch)
        self.scan_timer.start(3000)
        QTimer.singleShot(300, self.scan_watch)
        QTimer.singleShot(500, self.rq.pump)

    # ------------------------------------------------------------------ packs in
    def scan_watch(self):
        """Pick up packs dropped in the watch folder once they've finished copying (size stable for a scan)."""
        try:
            files = [p for p in self.watch.iterdir() if p.suffix.lower() == EXT and p.is_file()]
        except OSError:
            return
        for p in files:
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p)
            sig = (st.st_mtime, st.st_size)
            if self._seen.get(key) != sig:
                self._seen[key] = sig      # still arriving (or new): look again next scan
                continue
            self._seen.pop(key, None)
            if self.add_pack(p):
                done = self.watch / "Queued"
                done.mkdir(exist_ok=True)
                try:
                    shutil.move(str(p), str(done / p.name))
                except OSError:
                    pass

    def add_pack(self, path: Path) -> bool:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = self.unpacked / f"{path.stem}_{stamp}"
        try:
            spec = import_pack(path, dest)
        except Exception as exc:
            self.status.setText(f"Couldn't read {path.name}: {exc}")
            return False
        spec.output.output_dir = str(self.out_root)
        item = self.rq.add(spec)
        self.status.setText(f"Queued “{item.title}” from {path.name}")
        return True

    def _add_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add render packs", "", f"Render packs (*{EXT})")
        for f in files:
            self.add_pack(Path(f))

    def dragEnterEvent(self, ev):
        if any(u.toLocalFile().lower().endswith(EXT) for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            f = u.toLocalFile()
            if f.lower().endswith(EXT):
                self.add_pack(Path(f))

    # ------------------------------------------------------------------ display
    def _frame(self, item, path):
        if self.viewer.item is None or (self.panel.selected() is None and item.state == "running"):
            self.viewer.show_item(item)
        self.viewer.frame_arrived(item, path)

    def _progress(self, item):
        if self.viewer.item is None and item.state == "running":
            self.viewer.show_item(item)
        self.viewer.update_progress(item)

    def _labels(self):
        self.watch_lbl.setText(f"<b>Watching:</b> {self.watch}<br><b>Renders go to:</b> {self.out_root}")
        if not (self.blender and os.path.exists(self.blender)):
            self.status.setText("Blender wasn't found. Put the server in the program's folder (it uses the "
                                "bundled Blender) or set RSM_BLENDER.")
        else:
            self.status.setText(f"Ready · Blender: {self.blender} · version {__version__}")

    def _pick_watch(self):
        d = QFileDialog.getExistingDirectory(self, "Folder to watch for render packs", str(self.watch))
        if d:
            self.watch = Path(d)
            self.settings.setValue("server_watch", d)
            self._labels()

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Where finished renders go", str(self.out_root))
        if d:
            self.out_root = Path(d)
            self.settings.setValue("server_output", d)
            self._labels()

    def closeEvent(self, ev):
        if self.rq.running() is not None and QMessageBox.question(
                self, "Rendering", "A shot is rendering. Stop and close? It carries on from the last finished "
                                   "frame when the server starts again.") != QMessageBox.Yes:
            ev.ignore()
            return
        self.rq.shutdown()
        ev.accept()

    def wait_for_threads(self, ms: int = 8000):
        for i in self.rq.items:
            if i.thread is not None:
                try:
                    if i.thread.isRunning():
                        i.thread.wait(ms)
                except RuntimeError:
                    pass
