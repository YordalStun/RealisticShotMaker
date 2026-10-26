"""The render queue: line up as many shots as you like and let them render one after another.

The queue is saved to disk, so shots still waiting (or stopped half way) are there next time the program
opens; a stopped render carries on from its last finished frame.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import catalog, power
from ..estimate import estimate
from ..spec import ShotSpec
from .workers import JobThread, RenderJob

WAITING, RUNNING, DONE, FAILED, STOPPED = "waiting", "running", "done", "failed", "stopped"
STATE_TEXT = {WAITING: "Waiting", RUNNING: "Rendering", DONE: "Finished", FAILED: "Failed", STOPPED: "Stopped"}


def fmt_time(seconds) -> str:
    if seconds is None:
        return "–"
    s = int(max(0, seconds))
    if s >= 3600:
        return f"{s // 3600} h {s % 3600 // 60:02d} min"
    if s >= 60:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s} s"


class QueueItem:
    def __init__(self, spec: ShotSpec, mode: str = "video", job_path: str | None = None, uid: str | None = None,
                 state: str = WAITING, output: str = "", message: str = "", added: float | None = None,
                 done_frames: int = 0, total_frames: int = 0):
        self.spec = spec
        self.mode = mode
        self.job_path = job_path
        self.uid = uid or uuid.uuid4().hex[:12]
        self.state = state
        self.output = output
        self.message = message
        self.added = added or time.time()
        self.done_frames = done_frames
        self.total_frames = total_frames or estimate(spec)[2]
        self.eta: float | None = None
        self.job: RenderJob | None = None
        self.thread: JobThread | None = None

    @property
    def title(self) -> str:
        name = self.spec.output.name or "shot"
        return f"{name} · regrade" if self.mode == "regrade" else name

    def time_left(self) -> float:
        if self.state == RUNNING and self.eta is not None:
            return self.eta
        if self.state in (WAITING, STOPPED, RUNNING):
            per, total, frames = estimate(self.spec)
            if self.mode == "regrade":
                return frames * 1.0
            return max(0.0, total - per * self.done_frames)
        return 0.0

    def to_dict(self) -> dict:
        return dict(uid=self.uid, spec=self.spec.to_dict(), mode=self.mode, job_path=self.job_path,
                    state=self.state, output=self.output, message=self.message, added=self.added,
                    done_frames=self.done_frames, total_frames=self.total_frames)

    @classmethod
    def from_dict(cls, d: dict) -> "QueueItem":
        state = d.get("state", WAITING)
        if state == RUNNING:  # the program closed while it was rendering: it picks up where it stopped
            state = STOPPED
        return cls(ShotSpec.from_dict(d["spec"]), d.get("mode", "video"), d.get("job_path"), d.get("uid"), state,
                   d.get("output", ""), d.get("message", ""), d.get("added"), int(d.get("done_frames", 0)),
                   int(d.get("total_frames", 0)))


class RenderQueue(QObject):
    changed = Signal()                 # items added, removed, moved or changed state
    progressed = Signal(object)        # QueueItem whose progress moved
    frame_ready = Signal(object, str)  # QueueItem, path of its newest finished frame
    all_done = Signal()                # the last waiting shot finished

    def __init__(self, blender_getter, store: Path, parent=None):
        super().__init__(parent)
        self._blender = blender_getter
        self.store = Path(store)
        self.items: list[QueueItem] = []
        self.active = True             # False = paused: nothing new starts
        self._finished_since_start = 0
        self.load()

    # ------------------------------------------------------------------ persistence
    def load(self):
        try:
            data = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for d in data.get("items", []):
            try:
                self.items.append(QueueItem.from_dict(d))
            except Exception:
                continue
        self.active = not any(i.state in (WAITING, STOPPED) for i in self.items)

    def save(self):
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store.with_suffix(".tmp")
            tmp.write_text(json.dumps({"items": [i.to_dict() for i in self.items]}, indent=1), encoding="utf-8")
            os.replace(tmp, self.store)
        except OSError:
            pass

    # ------------------------------------------------------------------ editing the queue
    def add(self, spec: ShotSpec, mode: str = "video", job_path: str | None = None) -> QueueItem:
        item = QueueItem(spec.copy(), mode, job_path)
        self.items.append(item)
        self._touch()
        self.pump()
        return item

    def remove(self, item: QueueItem):
        if item.state == RUNNING:
            self.stop(item)
        if item in self.items:
            self.items.remove(item)
        self._touch()

    def move(self, item: QueueItem, delta: int):
        i = self.items.index(item)
        j = max(0, min(len(self.items) - 1, i + delta))
        if i != j:
            self.items.insert(j, self.items.pop(i))
            self._touch()

    def stop(self, item: QueueItem):
        """Stop a render; it keeps its finished frames and can be resumed."""
        if item.state == RUNNING and item.job:
            item.state = STOPPED
            item.message = "Stopped. Resume to carry on from the last finished frame."
            item.job.cancel()
        elif item.state == WAITING:
            item.state = STOPPED
            item.message = "Held back"
        self._touch()

    def resume(self, item: QueueItem):
        if item.state in (STOPPED, FAILED):
            item.state = WAITING
            item.message = ""
            self._touch()
            self.pump()

    def clear_finished(self):
        self.items = [i for i in self.items if i.state != DONE]
        self._touch()

    def set_active(self, on: bool):
        self.active = on
        if on:
            self._finished_since_start = 0
        self._touch()
        self.pump()

    def running(self) -> QueueItem | None:
        return next((i for i in self.items if i.state == RUNNING), None)

    def waiting(self) -> list[QueueItem]:
        return [i for i in self.items if i.state == WAITING]

    def _touch(self):
        self.save()
        # no sleeping in the middle of a render; normal sleep comes back once nothing is rendering
        power.keep_awake(self.running() is not None)
        self.changed.emit()

    # ------------------------------------------------------------------ running
    def pump(self):
        if not self.active or self.running() is not None:
            return
        nxt = next((i for i in self.items if i.state == WAITING), None)
        if nxt is None:
            if self._finished_since_start:
                self._finished_since_start = 0
                self.all_done.emit()
            return
        blender = self._blender()
        if not blender:
            return
        job = RenderJob(nxt.spec, blender, nxt.mode, job_path=Path(nxt.job_path) if nxt.job_path else None)
        nxt.job = job
        nxt.state = RUNNING
        nxt.message = "Starting…"
        job.updated.connect(lambda p, it=nxt: self._on_progress(it, p))
        job.frame_ready.connect(lambda path, it=nxt: self.frame_ready.emit(it, path))
        job.finished.connect(lambda ok, msg, it=nxt: self._on_finished(it, ok, msg))
        nxt.thread = JobThread(job)
        nxt.thread.start()
        self._touch()

    def _on_progress(self, item: QueueItem, p):
        if item.job and item.job.job_path and str(item.job.job_path) != item.job_path:
            item.job_path = str(item.job.job_path)   # known now: a stopped render can resume from here
            self.save()
        if p.total:
            item.total_frames = p.total
            item.done_frames = p.done
        item.eta = p.eta
        if item.state == RUNNING:
            item.message = p.message or p.stage
        self.progressed.emit(item)

    def _on_finished(self, item: QueueItem, ok: bool, msg: str):
        if item.job and item.job.job_path:
            item.job_path = str(item.job.job_path)
        if item.state == STOPPED:
            pass                                       # stopped by the user; message already set
        elif ok:
            item.state = DONE
            item.output = msg
            item.message = ""
            item.done_frames = item.total_frames
            self._finished_since_start += 1
        else:
            item.state = FAILED
            item.message = msg
        item.job = None
        item.eta = None
        self._touch()
        QTimer.singleShot(0, self.pump)

    def shutdown(self):
        """The program is closing: stop the running render (it resumes next time)."""
        r = self.running()
        if r and r.job:
            r.job.cancel()
            r.state = STOPPED
            r.message = "Stopped when the program closed. Resume to carry on."
        self.save()
        power.keep_awake(False)


class QueuePanel(QWidget):
    """The queue as a table with the controls people need for a night of rendering."""
    load_requested = Signal(object)      # ShotSpec to load into the editor
    regrade_requested = Signal(object)   # finished QueueItem
    selected_changed = Signal(object)    # QueueItem or None

    COLS = ["#", "Shot", "Set", "Size", "Status", "Progress", "Time left"]

    def __init__(self, queue: RenderQueue, parent=None):
        super().__init__(parent)
        self.q = queue
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        title = QLabel("Render queue")
        title.setObjectName("SectionTitle")
        self.start_btn = QPushButton()
        self.start_btn.clicked.connect(lambda: self.q.set_active(not self.q.active))
        self.summary = QLabel("")
        self.summary.setObjectName("Caption")
        self.when_done = QComboBox()
        for key, text in (("nothing", "Do nothing"), ("sleep", "Put the PC to sleep"), ("shutdown", "Shut the PC down")):
            self.when_done.addItem(text, key)
        self.when_done.setToolTip("For overnight renders: what to do once every shot in the queue has finished.")
        top.addWidget(title)
        top.addWidget(self.start_btn)
        top.addWidget(self.summary, 1)
        top.addWidget(QLabel("When the queue finishes:"))
        top.addWidget(self.when_done)
        lay.addLayout(top)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 170)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemSelectionChanged.connect(lambda: self.selected_changed.emit(self.selected()))
        self.table.cellDoubleClicked.connect(lambda r, c: self._double(r))
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btns = {}
        for key, text, tip in (
                ("up", "Up", "Move up the queue"), ("down", "Down", "Move down the queue"),
                ("stop", "Stop", "Stop this render (it keeps its frames) or hold a waiting one back"),
                ("resume", "Resume", "Carry on from the last finished frame, or try a failed render again"),
                ("load", "Load into editor", "Open this shot's settings in the editor"),
                ("again", "Render again", "Add a copy of this shot to the end of the queue"),
                ("regrade", "Regrade", "Apply the editor's current Look to a finished render without re-rendering"),
                ("remove", "Remove", "Take this shot out of the queue (files on disk are kept)"),
                ("folder", "Open folder", "Show the output folder"),
                ("clear", "Clear finished", "Remove every finished shot from the list")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self._act(k))
            row.addWidget(b)
            self.btns[key] = b
            if key in ("down", "resume", "regrade"):
                row.addSpacing(8)
        row.addStretch(1)
        lay.addLayout(row)

        self.q.changed.connect(self.refresh)
        self.q.progressed.connect(self._progress)
        self.refresh()

    # ------------------------------------------------------------------ display
    def selected(self) -> QueueItem | None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return None
        r = min(rows)
        return self.q.items[r] if r < len(self.q.items) else None

    def refresh(self):
        sel = self.selected()
        self.table.setRowCount(len(self.q.items))
        for r, it in enumerate(self.q.items):
            res = catalog.RESOLUTIONS.get(it.spec.output.resolution, ("", 0, 0))
            q = catalog.QUALITY.get(it.spec.output.quality)
            cells = [str(r + 1), it.title, catalog.option_name(catalog.LOCATIONS, it.spec.scene.location),
                     f"{res[1]}×{res[2]} · {q.name if q else ''}", self._status(it), None,
                     fmt_time(it.time_left()) if it.state != DONE else ""]
            for c, text in enumerate(cells):
                if c == 5:
                    bar = self.table.cellWidget(r, 5)
                    if not isinstance(bar, QProgressBar):
                        bar = QProgressBar()
                        bar.setRange(0, 1000)
                        self.table.setCellWidget(r, 5, bar)
                    self._fill_bar(bar, it)
                    continue
                cell = self.table.item(r, c)
                if cell is None:
                    cell = QTableWidgetItem()
                    self.table.setItem(r, c, cell)
                cell.setText(text)
                if c == 4:
                    cell.setToolTip(it.message or it.output)
        if sel in self.q.items:
            self.table.selectRow(self.q.items.index(sel))
        self.start_btn.setText("Pause queue" if self.q.active else "Start queue")
        self.start_btn.setToolTip("Pausing lets the current render finish, then waits." if self.q.active else
                                  "Start rendering the waiting shots, one after another.")
        self._summary()
        self._update_buttons()

    def _status(self, it: QueueItem) -> str:
        if it.state == RUNNING:
            return it.message or "Rendering"
        if it.state == DONE:
            return f"Finished · {Path(it.output).name}" if it.output else "Finished"
        if it.state == FAILED:
            return f"Failed: {it.message}"
        if it.state == STOPPED:
            return f"Stopped at frame {it.done_frames}/{it.total_frames}" if it.done_frames else "Held back"
        return "Waiting" if self.q.active else "Waiting (queue paused)"

    def _fill_bar(self, bar: QProgressBar, it: QueueItem):
        frac = it.done_frames / it.total_frames if it.total_frames else 0.0
        if it.state == DONE:
            frac = 1.0
        bar.setValue(int(frac * 1000))
        bar.setFormat(f"{it.done_frames}/{it.total_frames} frames" if it.state != DONE else "Done")

    def _progress(self, it: QueueItem):
        if it not in self.q.items:
            return
        r = self.q.items.index(it)
        if self.table.item(r, 4):
            self.table.item(r, 4).setText(self._status(it))
            self.table.item(r, 6).setText(fmt_time(it.time_left()) if it.state != DONE else "")
        bar = self.table.cellWidget(r, 5)
        if isinstance(bar, QProgressBar):
            self._fill_bar(bar, it)
        self._summary()

    def _summary(self):
        waiting = [i for i in self.q.items if i.state in (WAITING, RUNNING)]
        stopped = [i for i in self.q.items if i.state == STOPPED]
        done = [i for i in self.q.items if i.state == DONE]
        parts = []
        if waiting:
            parts.append(f"{len(waiting)} to render · about {fmt_time(sum(i.time_left() for i in waiting))} left")
        if stopped:
            parts.append(f"{len(stopped)} stopped")
        if done:
            parts.append(f"{len(done)} finished")
        if self.q.running() is not None and sys.platform == "win32":
            parts.append("PC kept awake while rendering")
        self.summary.setText("   ".join(parts) if parts else "Nothing queued. Set up a shot and press Add to queue.")

    def _update_buttons(self):
        it = self.selected()
        st = it.state if it else None
        n = len(self.q.items)
        idx = self.q.items.index(it) if it else -1
        en = {"up": it is not None and idx > 0, "down": it is not None and 0 <= idx < n - 1,
              "stop": st in (RUNNING, WAITING), "resume": st in (STOPPED, FAILED), "load": it is not None,
              "again": it is not None and it.mode == "video", "regrade": st == DONE and it.mode == "video",
              "remove": it is not None, "folder": True, "clear": any(i.state == DONE for i in self.q.items)}
        for k, b in self.btns.items():
            b.setEnabled(bool(en.get(k)))
        self.btns["stop"].setText("Hold back" if st == WAITING else "Stop")
        self.btns["resume"].setText("Try again" if st == FAILED else "Resume")

    # ------------------------------------------------------------------ actions
    def _act(self, key: str, it: QueueItem | None = None):
        it = it or self.selected()
        if key == "clear":
            self.q.clear_finished()
        elif key == "folder":
            self._open_folder(it)
        elif it is None:
            return
        elif key == "up":
            self.q.move(it, -1)
        elif key == "down":
            self.q.move(it, 1)
        elif key == "stop":
            self.q.stop(it)
        elif key == "resume":
            self.q.resume(it)
        elif key == "load":
            self.load_requested.emit(it.spec.copy())
        elif key == "again":
            self.q.add(it.spec)
        elif key == "regrade":
            self.regrade_requested.emit(it)
        elif key == "remove":
            if it.state == RUNNING and QMessageBox.question(
                    self, "Remove render", "This shot is rendering. Stop it and take it out of the queue?") \
                    != QMessageBox.Yes:
                return
            self.q.remove(it)

    def _menu(self, pos):
        it = self.selected()
        m = QMenu(self)
        for key, b in self.btns.items():
            if key in ("up", "down"):
                continue
            a = m.addAction(b.text())
            a.setEnabled(b.isEnabled())
            a.triggered.connect(lambda _=False, k=key: self._act(k, it))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _double(self, row: int):
        it = self.q.items[row] if row < len(self.q.items) else None
        if it is None:
            return
        if it.state == DONE and it.output and os.path.exists(it.output):
            _open_path(it.output)
        else:
            self.load_requested.emit(it.spec.copy())

    def _open_folder(self, it: QueueItem | None):
        folder = None
        if it and it.job_path:
            folder = str(Path(it.job_path).parent)
        elif it and it.spec.output.output_dir:
            folder = it.spec.output.output_dir
        from ..paths import default_output_dir
        folder = folder or str(default_output_dir())
        os.makedirs(folder, exist_ok=True)
        _open_path(folder)


def _open_path(path: str):
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def power_action(kind: str):
    """Sleep or shut down the PC (Windows). Called after a countdown the user can cancel."""
    if sys.platform != "win32":
        return
    flags = subprocess.CREATE_NO_WINDOW
    if kind == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "30", "/c", "RealisticShotMaker: render queue finished"],
                         creationflags=flags)
    elif kind == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=flags)
