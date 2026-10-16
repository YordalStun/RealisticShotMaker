"""Main application window."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal, QObject
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QVBoxLayout, QWidget)

from .. import __version__, catalog
from ..blender_locator import download_blender, find_blender
from ..spec import ShotSpec
from .fields import SECTIONS, Field, get_attr, set_attr
from .widgets import ColorButton, FolderPicker, ImageView, PhotoPicker, SliderField
from .workers import JobThread, PolaroidPreview, RenderJob

PRESETS = {
    "Golden hour memory": dict(scene=dict(location="study_desk", time_of_day="golden", light_shafts=0.5, dust=0.6),
                               camera=dict(move="push_in", lens="vintage_prime", body="film_35", fstop=2.0),
                               look=dict(grade="warm_nostalgia")),
    "Quiet morning": dict(scene=dict(location="kitchen_table", time_of_day="morning", light_shafts=0.3, dust=0.3),
                          camera=dict(move="slide_right", lens="cinema_soft", body="digital_cinema", fstop=2.8),
                          look=dict(grade="cool_morning")),
    "Attic discovery": dict(scene=dict(location="attic_trunk", time_of_day="midday", light_shafts=0.9, dust=1.0,
                                       placement="pile"),
                            camera=dict(move="tilt_reveal", lens="swirly_petzval", body="film_16", fstop=1.4),
                            look=dict(grade="faded_film")),
    "Late night letter": dict(scene=dict(location="bedside_night", time_of_day="night", light_shafts=0.1, dust=0.2),
                              camera=dict(move="rack_in", lens="vintage_prime", body="film_35", fstop=1.4),
                              look=dict(grade="golden_memory")),
    "Home movie": dict(scene=dict(location="mantelpiece", time_of_day="evening"),
                       camera=dict(move="handheld", lens="vintage_prime", body="super8", fstop=2.8),
                       look=dict(grade="faded_film")),
}


class _Bridge(QObject):
    blender_found = Signal(str, str)
    download_progress = Signal(float, str)
    download_done = Signal(str, str)


def fmt_time(seconds) -> str:
    if seconds is None:
        return "–"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealisticShotMaker")
        self.settings = QSettings("RealisticShotMaker", "RealisticShotMaker")
        self.spec = ShotSpec()
        self.spec.output.output_dir = self.settings.value("output_dir", "") or ""
        self.current_file: str | None = None
        self.widgets: dict[str, QWidget] = {}
        self.blender = self.settings.value("blender_path", "") or os.environ.get("RSM_BLENDER", "")
        self._preview_ticket = 0
        self._preview_threads: list[PolaroidPreview] = []
        self.queue: list[RenderJob] = []
        self.threads: dict[int, JobThread] = {}
        self.running: RenderJob | None = None
        self.still_job: RenderJob | None = None
        self.bridge = _Bridge()
        self.bridge.blender_found.connect(self._on_blender_found)
        self.bridge.download_progress.connect(lambda f, m: self.blender_label.setText(m))
        self.bridge.download_done.connect(self._on_download_done)

        self._build_ui()
        self._load_into_widgets()
        self._schedule_polaroid_preview()
        QTimer.singleShot(200, self._locate_blender)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)
        act_new = QAction("New shot", self, shortcut=QKeySequence.New, triggered=self.new_shot)
        act_open = QAction("Open…", self, shortcut=QKeySequence.Open, triggered=self.open_shot)
        act_save = QAction("Save", self, shortcut=QKeySequence.Save, triggered=self.save_shot)
        act_save_as = QAction("Save as…", self, triggered=lambda: self.save_shot(True))
        for a in (act_new, act_open, act_save, act_save_as):
            tb.addAction(a)
        tb.addSeparator()
        tb.addWidget(QLabel("  Quick start: "))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Choose a look…")
        for k in PRESETS:
            self.preset_combo.addItem(k)
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        tb.addWidget(self.preset_combo)

        menu = self.menuBar()
        fm = menu.addMenu("&File")
        for a in (act_new, act_open, act_save, act_save_as):
            fm.addAction(a)
        fm.addSeparator()
        fm.addAction(QAction("Quit", self, shortcut=QKeySequence.Quit, triggered=self.close))
        bm = menu.addMenu("&Blender")
        bm.addAction(QAction("Find Blender…", self, triggered=self.choose_blender))
        bm.addAction(QAction("Download Blender 4.5 LTS", self, triggered=self.download_blender))
        hm = menu.addMenu("&Help")
        hm.addAction(QAction("About", self, triggered=self.about))

        # settings tabs
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(470)
        for section, fields in SECTIONS.items():
            self.tabs.addTab(self._build_section(section, fields), section)

        # monitor + polaroid
        self.monitor = ImageView("Press “Preview frame” to see a quick render of your shot.\n\n"
                                 "Final renders are path traced at full quality and can take hours.")
        self.card_view = ImageView("")
        self.card_view.setMinimumSize(220, 260)
        self.card_view.setMaximumWidth(300)
        card_box = QVBoxLayout()
        lbl = QLabel("Your print")
        lbl.setObjectName("Caption")
        card_box.addWidget(lbl)
        card_box.addWidget(self.card_view, 1)
        top = QHBoxLayout()
        top.addWidget(self.monitor, 1)
        top.addLayout(card_box)

        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.setValue(50)
        self.time_label = QLabel("Middle of the shot")
        self.time_slider.valueChanged.connect(self._time_changed)
        self.preview_btn = QPushButton("Preview frame")
        self.preview_btn.clicked.connect(self.preview_frame)
        self.render_btn = QPushButton("Render video")
        self.render_btn.setObjectName("Primary")
        self.render_btn.clicked.connect(self.queue_render)
        self.estimate_label = QLabel("")
        self.estimate_label.setObjectName("Caption")
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Position:"))
        ctrl.addWidget(self.time_slider, 1)
        ctrl.addWidget(self.time_label)
        ctrl.addSpacing(12)
        ctrl.addWidget(self.preview_btn)
        ctrl.addWidget(self.render_btn)

        # queue
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Shot", "Status", "Progress", "Time left", "Output"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 180)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        qbtns = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel selected")
        self.cancel_btn.clicked.connect(self.cancel_selected)
        self.open_btn = QPushButton("Open output folder")
        self.open_btn.clicked.connect(self.open_selected)
        qbtns.addWidget(QLabel("Render queue"))
        qbtns.addStretch(1)
        qbtns.addWidget(self.cancel_btn)
        qbtns.addWidget(self.open_btn)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addLayout(top, 3)
        rl.addLayout(ctrl)
        rl.addWidget(self.estimate_label)
        rl.addLayout(qbtns)
        rl.addWidget(self.table, 1)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tabs)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([480, 1080])
        self.setCentralWidget(split)

        self.blender_label = QLabel("Looking for Blender…")
        self.statusBar().addWidget(self.blender_label, 1)
        self.resize(1560, 940)

    def _build_section(self, section: str, fields: list[Field]) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        groups: dict[str, QFormLayout] = {}
        for f in fields:
            g = f.group or section
            if g not in groups:
                box = QGroupBox(g)
                form = QFormLayout(box)
                form.setLabelAlignment(Qt.AlignRight)
                groups[g] = form
                lay.addWidget(box)
            w = self._make_widget(f)
            if f.tip:
                w.setToolTip(f.tip)
            groups[g].addRow(f.label, w)
            self.widgets[f.path] = w
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _make_widget(self, f: Field) -> QWidget:
        if f.kind == "combo":
            w = QComboBox()
            for value, label in f.options:
                w.addItem(label, value)
            w.currentIndexChanged.connect(lambda _, f=f, w=w: self._changed(f, w.currentData()))
            return w
        if f.kind == "slider":
            w = SliderField(f.minimum, f.maximum, f.step, f.suffix)
            w.valueChanged.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "spin":
            w = QSpinBox()
            w.setRange(int(f.minimum), int(f.maximum))
            w.setSingleStep(int(f.step))
            w.valueChanged.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "dspin":
            w = QDoubleSpinBox()
            w.setRange(f.minimum, f.maximum)
            w.setSingleStep(f.step)
            w.setSuffix(f.suffix)
            w.valueChanged.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "check":
            w = QCheckBox()
            w.toggled.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "text":
            w = QLineEdit()
            w.textChanged.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "photo":
            w = PhotoPicker(f.options)
            w.changed.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "color":
            w = ColorButton()
            w.changed.connect(lambda v, f=f: self._changed(f, v))
            return w
        if f.kind == "folder":
            w = FolderPicker()
            w.changed.connect(lambda v, f=f: self._changed(f, v))
            return w
        return QLabel("?")

    # ------------------------------------------------------------------ spec <-> widgets
    def _load_into_widgets(self):
        self._loading = True
        for section, fields in SECTIONS.items():
            for f in fields:
                w = self.widgets[f.path]
                v = get_attr(self.spec, f.path)
                if f.kind == "combo":
                    idx = w.findData(str(v) if not isinstance(v, str) else v)
                    if idx < 0 and isinstance(v, float):
                        idx = w.findData(f"{v:g}")
                        if idx < 0:
                            idx = w.findData(str(int(v)) if v == int(v) else str(v))
                    if idx >= 0:
                        w.blockSignals(True)
                        w.setCurrentIndex(idx)
                        w.blockSignals(False)
                elif f.kind == "slider":
                    w.setValue(float(v))
                elif f.kind in ("spin", "dspin"):
                    w.blockSignals(True)
                    w.setValue(v)
                    w.blockSignals(False)
                elif f.kind == "check":
                    w.blockSignals(True)
                    w.setChecked(bool(v))
                    w.blockSignals(False)
                elif f.kind == "text":
                    w.blockSignals(True)
                    w.setText(str(v))
                    w.blockSignals(False)
                elif f.kind == "photo":
                    w.set_value(str(v))
                elif f.kind == "color":
                    w.set_color(str(v))
                elif f.kind == "folder":
                    w.set_value(str(v))
        self._loading = False
        self._update_estimate()

    def _changed(self, f: Field, value):
        if getattr(self, "_loading", False):
            return
        set_attr(self.spec, f.path, value)
        if f.path == "polaroid.condition":
            c = dict(catalog.CONDITIONS.get(value, {}))
            c.pop("name", None)
            for k, v in c.items():
                setattr(self.spec.polaroid, k, v)
            self._load_into_widgets()
        if f.path == "camera.move":
            mv = catalog.MOVES.get(value)
            if mv:
                self.spec.camera.duration = mv.default_duration
                self._load_into_widgets()
        if f.path == "output.output_dir":
            self.settings.setValue("output_dir", value)
        if f.path.startswith("polaroid."):
            self._schedule_polaroid_preview()
        self._update_estimate()

    def _update_estimate(self):
        res = catalog.RESOLUTIONS.get(self.spec.output.resolution)
        q = catalog.QUALITY.get(self.spec.output.quality)
        frames = int(round(self.spec.camera.duration * self.spec.output.fps))
        if not res or not q:
            return
        samples = self.spec.output.custom_samples or q.samples
        mpix = res[1] * res[2] / 1e6
        # rough guide for an RTX 4080/5080 class card with this kind of interior scene
        sec_per_frame = mpix * samples / 1024 * 9.0 * (1.6 if self.spec.scene.light_shafts > 0.05 else 1.0)
        total = sec_per_frame * frames
        self.estimate_label.setText(
            f"{frames} frames at {res[1]}×{res[2]}, {samples} samples per pixel. "
            f"Rough estimate on a high-end graphics card: about {fmt_time(sec_per_frame)} per frame, "
            f"{fmt_time(total)} in total.")

    # ------------------------------------------------------------------ polaroid preview
    def _schedule_polaroid_preview(self):
        if not hasattr(self, "_pp_timer"):
            self._pp_timer = QTimer(self)
            self._pp_timer.setSingleShot(True)
            self._pp_timer.timeout.connect(self._run_polaroid_preview)
        self._pp_timer.start(250)

    def _run_polaroid_preview(self):
        self._preview_ticket += 1
        t = PolaroidPreview(self.spec, self._preview_ticket, 560)
        t.ready.connect(self._on_polaroid_preview)
        t.finished.connect(lambda t=t: self._preview_threads.remove(t) if t in self._preview_threads else None)
        self._preview_threads.append(t)
        t.start()

    def _on_polaroid_preview(self, img: QImage, ticket: int):
        if ticket == self._preview_ticket:
            self.card_view.set_image(img)

    # ------------------------------------------------------------------ blender
    def _locate_blender(self):
        if self.blender and os.path.exists(self.blender):
            self._on_blender_found(self.blender, "")
            return

        def work():
            path, ver = find_blender()
            self.bridge.blender_found.emit(path or "", ".".join(map(str, ver)) if ver else "")
        threading.Thread(target=work, daemon=True).start()

    def _on_blender_found(self, path: str, ver: str):
        if path:
            self.blender = path
            self.settings.setValue("blender_path", path)
            self.blender_label.setText(f"Blender {ver} ready: {path}" if ver else f"Blender: {path}")
        else:
            self.blender_label.setText("Blender 4.5 or newer was not found. Use the Blender menu to download or "
                                       "locate it.")

    def choose_blender(self):
        path, _ = QFileDialog.getOpenFileName(self, "Find blender.exe", "", "Blender (blender.exe blender)")
        if path:
            self._on_blender_found(path, "")

    def download_blender(self):
        if QMessageBox.question(self, "Download Blender",
                                "Download the portable Blender 4.5 LTS (about 400 MB) from blender.org?") \
                != QMessageBox.Yes:
            return

        def work():
            try:
                exe = download_blender(lambda f, m: self.bridge.download_progress.emit(f, m))
                self.bridge.download_done.emit(exe, "")
            except Exception as exc:
                self.bridge.download_done.emit("", str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _on_download_done(self, exe, err):
        if exe:
            self._on_blender_found(exe, "4.5")
        else:
            QMessageBox.warning(self, "Download failed", err)

    def _need_blender(self) -> bool:
        if self.blender and os.path.exists(self.blender):
            return True
        QMessageBox.information(self, "Blender needed",
                                "RealisticShotMaker renders with Blender's Cycles path tracer. "
                                "Use Blender → Download Blender 4.5 LTS, or Find Blender if it's installed.")
        return False

    # ------------------------------------------------------------------ rendering
    def _time_changed(self, v):
        t = v / 100 * self.spec.camera.duration
        self.time_label.setText(f"{t:.1f} s")

    def preview_frame(self):
        if not self._need_blender():
            return
        if self.still_job is not None:
            return
        s = self.spec.copy()
        s.output.resolution = "preview"
        s.output.quality = "preview"
        s.output.custom_samples = 0
        s.output.name = "preview"
        s.output.output_dir = str(Path(self._work_root()) / "previews")
        job = RenderJob(s, self.blender, "still", self.time_slider.value() / 100)
        job.updated.connect(lambda p: self.monitor.set_placeholder(p.message or "Rendering preview…"))
        job.finished.connect(self._still_finished)
        self.still_job = job
        self.preview_btn.setEnabled(False)
        self.preview_btn.setText("Rendering…")
        self.monitor.set_image(None)
        self.monitor.set_placeholder("Building the scene…")
        th = JobThread(job)
        self.threads[id(job)] = th
        th.start()

    def _still_finished(self, ok: bool, msg: str):
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText("Preview frame")
        if ok:
            self.monitor.set_image(msg)
        else:
            self.monitor.set_placeholder("Preview failed: " + msg)
        self.still_job = None

    def _work_root(self) -> str:
        return self.spec.output.output_dir or str(Path.home() / "Videos" / "RealisticShotMaker")

    def queue_render(self):
        if not self._need_blender():
            return
        job = RenderJob(self.spec, self.blender, "video")
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = f"{self.spec.output.name} · {catalog.option_name(catalog.LOCATIONS, self.spec.scene.location)}"
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem("Waiting"))
        bar = QProgressBar()
        bar.setRange(0, 1000)
        self.table.setCellWidget(row, 2, bar)
        self.table.setItem(row, 3, QTableWidgetItem("–"))
        self.table.setItem(row, 4, QTableWidgetItem(""))
        job.row = row
        job.updated.connect(lambda p, job=job: self._job_update(job, p))
        job.finished.connect(lambda ok, msg, job=job: self._job_finished(job, ok, msg))
        job.frame_ready.connect(lambda path: self.monitor.set_image(path))
        self.queue.append(job)
        self._pump()

    def _pump(self):
        if self.running is not None:
            return
        for job in self.queue:
            if getattr(job, "state", "waiting") == "waiting":
                job.state = "running"
                self.running = job
                th = JobThread(job)
                self.threads[id(job)] = th
                th.start()
                return

    def _job_update(self, job: RenderJob, p):
        row = job.row
        self.table.item(row, 1).setText(p.message or p.stage)
        bar: QProgressBar = self.table.cellWidget(row, 2)
        bar.setValue(int(p.fraction * 1000))
        bar.setFormat(f"{p.done}/{p.total} frames" if p.total else "")
        self.table.item(row, 3).setText(fmt_time(p.eta))

    def _job_finished(self, job: RenderJob, ok: bool, msg: str):
        job.state = "done" if ok else "failed"
        row = job.row
        self.table.item(row, 1).setText("Finished" if ok else msg)
        if ok:
            self.table.cellWidget(row, 2).setValue(1000)
            self.table.item(row, 4).setText(msg)
            self.table.item(row, 3).setText("")
        self.running = None
        self._pump()

    def _selected_job(self) -> RenderJob | None:
        rows = {i.row() for i in self.table.selectedIndexes()}
        for job in self.queue:
            if job.row in rows:
                return job
        return None

    def cancel_selected(self):
        job = self._selected_job()
        if job:
            if getattr(job, "state", "") == "waiting":
                job.state = "cancelled"
                self.table.item(job.row, 1).setText("Cancelled")
            else:
                job.cancel()

    def open_selected(self):
        job = self._selected_job()
        folder = None
        if job and job.job_path:
            folder = str(Path(job.job_path).parent)
        folder = folder or self._work_root()
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    # ------------------------------------------------------------------ files and presets
    def new_shot(self):
        self.spec = ShotSpec()
        self.spec.output.output_dir = self.settings.value("output_dir", "") or ""
        self.current_file = None
        self._load_into_widgets()
        self._schedule_polaroid_preview()

    def open_shot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open shot", "", "Shot files (*.rsm.json *.json)")
        if path:
            try:
                self.spec = ShotSpec.load(path)
            except Exception as exc:
                QMessageBox.warning(self, "Could not open", str(exc))
                return
            self.current_file = path
            self._load_into_widgets()
            self._schedule_polaroid_preview()

    def save_shot(self, save_as=False):
        path = self.current_file
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save shot", f"{self.spec.output.name}.rsm.json",
                                                  "Shot files (*.rsm.json)")
        if path:
            self.spec.save(path)
            self.current_file = path

    def apply_preset(self, name: str):
        p = PRESETS.get(name)
        if not p:
            return
        for section, values in p.items():
            obj = getattr(self.spec, section)
            for k, v in values.items():
                setattr(obj, k, v)
        self._load_into_widgets()
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

    def about(self):
        QMessageBox.about(self, "RealisticShotMaker",
                          f"<b>RealisticShotMaker {__version__}</b><br>Cinematic documentary insert shots, path "
                          "traced with Blender Cycles.<br><br>Handwriting fonts: SIL Open Font License. "
                          "Sample photos: CC0.")

    def closeEvent(self, ev):
        running = [j for j in self.queue if getattr(j, "state", "") == "running"]
        if running and QMessageBox.question(self, "Renders running",
                                            "A render is still running. Stop it and quit? Finished frames are kept.") \
                != QMessageBox.Yes:
            ev.ignore()
            return
        for j in running:
            j.cancel()
        ev.accept()
