"""Main application window."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal, QObject
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QListWidget, QListWidgetItem, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QVBoxLayout, QWidget)

from .. import __version__, catalog
from ..blender_locator import app_data_dir, download_blender, find_blender
from ..estimate import estimate
from ..spec import ShotSpec
from .draft_player import DraftPlayer
from .output_viewer import OutputViewer
from .path_view import PathPanel
from .shot_timeline import ShotListEditor
from .. import shotlist
from .fields import SECTIONS, Field, get_attr, set_attr
from .preview_popup import MoveHoverWatcher, PreviewPopup
from .render_queue import QueuePanel, RenderQueue, power_action
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
    "Cold case board": dict(scene=dict(location="investigation_board", time_of_day="night", placement="pinned",
                                       light_shafts=0.5, dust=0.4),
                            camera=dict(move="pan_across", lens="anamorphic", body="digital_cinema", fstop=2.0),
                            look=dict(grade="bleach_bypass")),
    "Memory close-up cut": dict(scene=dict(location="study_desk", time_of_day="golden"),
                                camera=dict(move="macro_cut", cut_at=0.4, cut_to="push_in", lens="vintage_prime",
                                            body="film_35", fstop=2.8),
                                look=dict(grade="warm_nostalgia")),
    "Noir case file": dict(scene=dict(location="investigation_board", placement="pinned", mood="noir_blinds",
                                      light_shafts=0.4, dust=0.5),
                           camera=dict(move="push_in", lens="vintage_prime", body="film_35", fstop=2.0),
                           look=dict(grade="bleach_bypass")),
    "Searching in the dark": dict(scene=dict(location="attic_trunk", placement="flat", mood="torch", dust=0.8),
                                  camera=dict(move="handheld", lens="vintage_prime", body="film_16", fstop=1.8),
                                  look=dict(grade="faded_film")),
    "Storm night": dict(scene=dict(location="bedside_night", mood="lightning", dust=0.3),
                        camera=dict(move="push_in", lens="cinema_soft", body="digital_cinema", fstop=1.8),
                        look=dict(grade="cool_morning")),
    "Interrogation bulb": dict(scene=dict(location="kitchen_table", mood="bare_bulb", dust=0.6),
                               camera=dict(move="locked_off", lens="vintage_prime", body="film_35", fstop=2.8),
                               look=dict(grade="bleach_bypass")),
    "Home movie": dict(scene=dict(location="mantelpiece", time_of_day="evening"),
                       camera=dict(move="handheld", lens="vintage_prime", body="super8", fstop=2.8),
                       look=dict(grade="faded_film")),
}


class _Bridge(QObject):
    preview_progress = Signal(str)
    previews_done = Signal(list)
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
        from ..paths import settings as _settings
        self.settings = _settings()
        self.spec = ShotSpec()
        self.spec.output.output_dir = self.settings.value("output_dir", "") or ""
        self.current_file: str | None = None
        self.widgets: dict[str, QWidget] = {}
        self.blender = self.settings.value("blender_path", "") or os.environ.get("RSM_BLENDER", "")
        self._preview_ticket = 0
        self._preview_threads: list[PolaroidPreview] = []
        self.threads: dict[int, JobThread] = {}
        self.still_job: RenderJob | None = None
        self.draft_job: RenderJob | None = None
        self._draft_ticket = 0
        self.rq = RenderQueue(lambda: self.blender if self.blender and os.path.exists(self.blender) else "",
                              app_data_dir() / "queue.json", self)
        self.rq.frame_ready.connect(self._queue_frame)
        self.rq.all_done.connect(self._queue_finished)
        self.bridge = _Bridge()
        self.bridge.blender_found.connect(self._on_blender_found)
        self.bridge.download_progress.connect(lambda f, m: self.blender_label.setText(m))
        self.bridge.download_done.connect(self._on_download_done)

        self._build_ui()
        self.preview_popup = PreviewPopup()
        for key in ("camera.move",):
            MoveHoverWatcher(self.widgets[key], self.preview_popup)
        self.bridge.preview_progress.connect(lambda m: self.blender_label.setText(m))
        self.bridge.previews_done.connect(self._previews_done)
        self._preview_build_running = False
        self.path_job: RenderJob | None = None
        self._path_ticket = 0
        self._path_stale = True
        self._path_timer = QTimer(self)
        self._path_timer.setSingleShot(True)
        self._path_timer.timeout.connect(lambda: self.start_path(manual=False))
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.timeout.connect(lambda: self.start_draft(manual=False))
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
        fm.addAction(QAction("Export for render server…", self, triggered=self.export_pack))
        fm.addSeparator()
        fm.addAction(QAction("Quit", self, shortcut=QKeySequence.Quit, triggered=self.close))
        bm = menu.addMenu("&Blender")
        bm.addAction(QAction("Find Blender…", self, triggered=self.choose_blender))
        bm.addAction(QAction("Download Blender 4.5 LTS", self, triggered=self.download_blender))
        bm.addSeparator()
        bm.addAction(QAction("Build shot previews…", self, triggered=self.build_previews))
        hm = menu.addMenu("&Help")
        hm.addAction(QAction("About", self, triggered=self.about))

        # settings tabs
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(470)
        for section, fields in SECTIONS.items():
            self.tabs.addTab(self._build_section(section, fields), section)
            if section == "Camera":
                self.tabs.addTab(self._build_fun_tab(), "Fun moves")

        self.draft_player = DraftPlayer()
        self.draft_player.make_requested.connect(lambda: self.start_draft(manual=True))
        self.draft_player.auto_changed.connect(lambda on: on and self._schedule_draft())
        self.draft_player.auto.setChecked(self.settings.value("auto_draft", "true") == "true")
        self.draft_player.auto_changed.connect(lambda on: self.settings.setValue("auto_draft", "true" if on else "false"))
        self.draft_player.engine.setCurrentIndex(max(0, self.draft_player.engine.findData(
            self.settings.value("draft_engine", "eevee"))))
        self.draft_player.engine_changed.connect(lambda e: (self.settings.setValue("draft_engine", e),
                                                            self._schedule_draft()))
        editor = QWidget()
        el = QVBoxLayout(editor)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(self.draft_player)
        el.addWidget(self.tabs, 1)

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
        self.output_viewer = OutputViewer()
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.monitor, "Preview frame")
        self.view_tabs.addTab(self.output_viewer, "Render output")
        self.path_panel = PathPanel()
        self.path_panel.update_requested.connect(lambda: self.start_path(manual=True))
        self.view_tabs.addTab(self.path_panel, "Camera path (3D)")
        self.view_tabs.currentChanged.connect(lambda _: self._path_stale and self._schedule_path(0))
        top = QHBoxLayout()
        top.addWidget(self.view_tabs, 1)
        top.addLayout(card_box)

        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 100)
        self.time_slider.setValue(50)
        self.time_label = QLabel("Middle of the shot")
        self.time_slider.valueChanged.connect(self._time_changed)
        self.preview_btn = QPushButton("Preview frame")
        self.preview_btn.clicked.connect(self.preview_frame)
        self.render_btn = QPushButton("Add to render queue")
        self.render_btn.setObjectName("Primary")
        self.render_btn.setToolTip("Queue this shot for a full-quality render. Add as many as you like; they render "
                                   "one after another.")
        self.render_btn.clicked.connect(lambda: self.queue_render())
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
        self.queue_panel = QueuePanel(self.rq)
        self.queue_panel.load_requested.connect(self._load_spec)
        self.queue_panel.selected_changed.connect(self._queue_selected)
        self.rq.progressed.connect(self._queue_progress)
        self.rq.changed.connect(lambda: self.output_viewer.update_progress(self.output_viewer.item))
        self.queue_panel.regrade_requested.connect(self._regrade)
        self.queue_panel.when_done.setCurrentIndex(max(0, self.queue_panel.when_done.findData(
            self.settings.value("when_queue_done", "nothing"))))
        self.queue_panel.when_done.currentIndexChanged.connect(
            lambda _: self.settings.setValue("when_queue_done", self.queue_panel.when_done.currentData()))

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addLayout(top, 3)
        rl.addLayout(ctrl)
        rl.addWidget(self.estimate_label)
        self.queue_panel.setMinimumHeight(230)
        rl.addWidget(self.queue_panel, 2)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(editor)
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
        if section == "Camera":
            box = QGroupBox("Shots")
            bl = QVBoxLayout(box)
            self.shot_editor = ShotListEditor()
            bl.addWidget(self.shot_editor)
            self.shot_editor.strip.selected.connect(self._shot_selected)
            self.shot_editor.strip.lengths_changed.connect(self._shot_lengths)
            self.shot_editor.cut_requested.connect(self._shot_cut)
            self.shot_editor.remove_requested.connect(self._shot_remove)
            lay.insertWidget(0, box)
        if section == "Scene":
            box = QGroupBox("Location options")
            self.locopt_form = QFormLayout(box)
            self.locopt_form.setLabelAlignment(Qt.AlignRight)
            lay.insertWidget(1, box)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _build_fun_tab(self) -> QWidget:
        """Playful camera tricks: whip-pan cuts, crash zooms, the Vertigo effect, ..."""
        page = QWidget()
        lay = QVBoxLayout(page)
        intro = QLabel("Stylish camera tricks. Click one to use it; hover to see a preview. "
                       "Lens, aperture and camera body still come from the Camera tab.")
        intro.setWordWrap(True)
        intro.setObjectName("Caption")
        lay.addWidget(intro)
        self.fun_list = QListWidget()
        self.fun_list.setMouseTracking(True)
        self.fun_list.setWordWrap(True)
        self.fun_list.setSpacing(4)
        for k, mv in catalog.MOVES.items():
            if mv.group != "fun":
                continue
            item = QListWidgetItem(f"{mv.name}\n{mv.description}")
            item.setData(Qt.UserRole, k)
            self.fun_list.addItem(item)
        self.fun_list.itemClicked.connect(self._fun_chosen)
        self.fun_list.itemEntered.connect(
            lambda it: self.preview_popup.show_move(it.data(Qt.UserRole),
                                                    self.fun_list.mapToGlobal(self.fun_list.rect().topRight())))
        self.fun_list.viewport().installEventFilter(self)
        lay.addWidget(self.fun_list, 1)
        back = QPushButton("Back to the classic moves")
        back.clicked.connect(self._fun_cleared)
        lay.addWidget(back)
        return page

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if getattr(self, "fun_list", None) is not None and obj is self.fun_list.viewport() and ev.type() == QEvent.Leave:
            self.preview_popup.hide_preview()
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------------ shot list
    def _is_list(self) -> bool:
        return len(self.spec.camera.shots) >= 2

    def _set_shot_value(self, key: str, value):
        if self._is_list():
            shots = shotlist.shots_of(self.spec)
            self.sel_shot = min(getattr(self, "sel_shot", 0), len(shots) - 1)
            shots[self.sel_shot][key] = value
            shotlist.set_shots(self.spec, shots)
        else:
            setattr(self.spec.camera, key, value)

    def _shots_changed(self):
        self._load_into_widgets()
        self._schedule_draft()
        self._update_estimate()

    def _shot_selected(self, i: int):
        self.sel_shot = i
        self._load_into_widgets()
        self.path_panel.show_shot(i)

    def _shot_lengths(self, lengths: list):
        shots = shotlist.shots_of(self.spec)
        for s, ln in zip(shots, lengths):
            s["length"] = ln
        shotlist.set_shots(self.spec, shots)
        self._shots_changed()

    def _shot_cut(self):
        sel = getattr(self, "sel_shot", 0)
        shotlist.set_shots(self.spec, shotlist.split(shotlist.shots_of(self.spec), sel))
        self.sel_shot = sel + 1
        self._shots_changed()

    def _shot_remove(self):
        sel = getattr(self, "sel_shot", 0)
        shotlist.set_shots(self.spec, shotlist.remove(shotlist.shots_of(self.spec), sel))
        self.sel_shot = max(0, sel - 1)
        self._shots_changed()

    def _fun_chosen(self, item):
        move = item.data(Qt.UserRole)
        if self._is_list():
            self._set_shot_value("move", move)
            self._shots_changed()
            return
        self.spec.camera.move = move
        mv = catalog.MOVES[move]
        self.spec.camera.duration = mv.default_duration
        self._load_into_widgets()

    def _fun_cleared(self):
        self.spec.camera.move = "push_in"
        self.spec.camera.duration = catalog.MOVES["push_in"].default_duration
        self._load_into_widgets()

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
                key = f.path[7:] if f.path.startswith("camera.") else ""
                if key in shotlist.PER_SHOT and self._is_list():
                    shots = shotlist.shots_of(self.spec)
                    v = shots[min(getattr(self, "sel_shot", 0), len(shots) - 1)][key]
                if f.path == "camera.move":
                    fun = catalog.MOVES.get(v) is not None and catalog.MOVES[v].group == "fun"
                    ph = w.findData("__fun__")
                    if fun:
                        label = f"Fun move: {catalog.MOVES[v].name}"
                        if ph < 0:
                            w.addItem(label, "__fun__")
                            ph = w.count() - 1
                        w.setItemText(ph, label)
                        w.blockSignals(True)
                        w.setCurrentIndex(ph)
                        w.blockSignals(False)
                        if hasattr(self, "fun_list"):
                            for r in range(self.fun_list.count()):
                                if self.fun_list.item(r).data(Qt.UserRole) == v:
                                    self.fun_list.setCurrentRow(r)
                        continue
                    if ph >= 0:
                        w.blockSignals(True)
                        w.removeItem(ph)
                        w.blockSignals(False)
                    if hasattr(self, "fun_list"):
                        self.fun_list.clearSelection()
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
        self._limit_placements()
        if hasattr(self, "shot_editor"):
            shots = shotlist.shots_of(self.spec)
            self.sel_shot = min(getattr(self, "sel_shot", 0), len(shots) - 1)
            self.shot_editor.set_shots(shots, self.sel_shot)
        self._loading = False
        self._rebuild_location_options()
        self._print_type_fields()
        self._update_estimate()

    def _print_type_fields(self):
        """Frame settings only matter for a framed photo; film and border colour only for an instant print."""
        framed = self.spec.polaroid.print_type == "framed"
        for path, on in (("polaroid.frame_style", framed), ("polaroid.frame_size", framed),
                         ("polaroid.frame_mat", framed), ("polaroid.film", not framed),
                         ("polaroid.frame_color", not framed)):
            w = self.widgets.get(path)
            if w is not None:
                w.setEnabled(on)

    def _limit_placements(self):
        """Only offer the placements the chosen set can do (no 'pinned' on the kitchen table)."""
        w = self.widgets.get("scene.placement")
        loc = catalog.LOCATIONS.get(self.spec.scene.location)
        if w is None or loc is None:
            return
        model = w.model()
        for i in range(w.count()):
            item = model.item(i)
            if item is not None:
                item.setEnabled(w.itemData(i) in loc.placements)

    def _rebuild_location_options(self):
        """Options that only exist for the chosen location (string on the board, breakfast mess, …)."""
        form = getattr(self, "locopt_form", None)
        if form is None:
            return
        while form.rowCount():
            form.removeRow(0)
        loc = catalog.LOCATIONS.get(self.spec.scene.location)
        values = catalog.location_options(self.spec.scene.location, self.spec.scene.options)
        if not loc or not loc.options:
            form.addRow(QLabel("No extra options for this location."))
            return
        for o in loc.options:
            v = values[o.id]
            if o.kind == "combo":
                w = QComboBox()
                for val, label in o.choices:
                    w.addItem(label, val)
                w.setCurrentIndex(max(0, w.findData(v)))
                w.currentIndexChanged.connect(lambda _, o=o, w=w: self._loc_opt(o.id, w.currentData()))
            elif o.kind == "slider":
                w = SliderField(0.0, 1.0, 0.01)
                w.setValue(float(v))
                w.valueChanged.connect(lambda val, o=o: self._loc_opt(o.id, val))
            else:
                w = QCheckBox()
                w.setChecked(bool(v))
                w.toggled.connect(lambda val, o=o: self._loc_opt(o.id, bool(val)))
            if o.tip:
                w.setToolTip(o.tip)
            form.addRow(o.label, w)

    def _loc_opt(self, key, value):
        self.spec.scene.options[key] = value
        self._update_estimate()
        self._schedule_draft()

    def _changed(self, f: Field, value):
        if getattr(self, "_loading", False) or value == "__fun__":
            return
        key = f.path[7:] if f.path.startswith("camera.") else ""
        if key == "move" and value == "macro_cut":
            # the classic close-up cut is a two-shot list: start one and let the user edit each side
            self.spec.camera.move = "macro_cut"
            self.spec.camera.duration = catalog.MOVES["macro_cut"].default_duration
            shotlist.set_shots(self.spec, shotlist.shots_of(self.spec))
            self.sel_shot = 0
            self._shots_changed()
            return
        if key in shotlist.PER_SHOT and self._is_list():
            self._set_shot_value(key, value)
            if key == "framing":
                self._set_shot_value("focal_mm", {"extreme_close": 100.0, "close": 85.0, "medium": 50.0,
                                                  "wide": 35.0}.get(value, self.spec.camera.focal_mm))
            self._shots_changed()
            return
        if key == "duration" and self._is_list():
            shots = shotlist.shots_of(self.spec)
            k = float(value) / max(0.01, sum(s["length"] for s in shots))
            for s in shots:
                s["length"] *= k
            shotlist.set_shots(self.spec, shots)
            self._shots_changed()
            return
        set_attr(self.spec, f.path, value)
        if f.path == "polaroid.condition":
            c = dict(catalog.CONDITIONS.get(value, {}))
            c.pop("name", None)
            for k, v in c.items():
                setattr(self.spec.polaroid, k, v)
            self._load_into_widgets()
        if f.path == "scene.location":
            self.spec.scene.options = {}
            loc = catalog.LOCATIONS.get(value)
            if loc:
                self.spec.scene.time_of_day = loc.default_time
                if self.spec.scene.placement not in loc.placements:
                    self.spec.scene.placement = loc.placements[0]
                cur = catalog.MOVES.get(self.spec.camera.move)
                if loc.default_move and (cur is None or cur.group != "multi"):
                    # sets made for several photos start on a move that travels between them
                    self.spec.camera.move = loc.default_move
                    self.spec.camera.duration = catalog.MOVES[loc.default_move].default_duration
            self._load_into_widgets()
        if f.path == "camera.framing":
            # like a DP changing lenses: wider framings get wider lenses (the user can still override)
            self.spec.camera.focal_mm = {"extreme_close": 100.0, "close": 85.0, "medium": 50.0, "wide": 35.0}.get(
                value, self.spec.camera.focal_mm)
            self._load_into_widgets()
        if f.path == "camera.move":
            mv = catalog.MOVES.get(value)
            if mv:
                self.spec.camera.duration = mv.default_duration
                self._load_into_widgets()
        if f.path == "output.output_dir":
            self.settings.setValue("output_dir", value)
        if f.path == "polaroid.print_type":
            self._print_type_fields()
        if f.path.startswith("polaroid."):
            self._schedule_polaroid_preview()
        if not f.path.startswith("output."):
            self._schedule_draft()
        self.estimate_label.setWordWrap(True)
        self._update_estimate()

    def _update_estimate(self):
        res = catalog.RESOLUTIONS.get(self.spec.output.resolution)
        q = catalog.QUALITY.get(self.spec.output.quality)
        frames = int(round(self.spec.camera.duration * self.spec.output.fps))
        if not res or not q:
            return
        samples = self.spec.output.custom_samples or q.samples
        sec_per_frame, total, frames = estimate(self.spec)
        text = (f"{frames} frames at {res[1]}×{res[2]}, {samples} samples per pixel. "
                f"Rough estimate on a high-end graphics card: about {fmt_time(sec_per_frame)} per frame, "
                f"{fmt_time(total)} in total.")
        warn = self._photo_resolution_warning(res[2])
        if warn:
            text += "\n⚠ " + warn
        self.estimate_label.setText(text)

    def _photo_resolution_warning(self, out_h: int) -> str:
        """Tell the user when their photo is too small to stay sharp at the chosen size and framing."""
        src = self.spec.polaroid.photo
        try:
            from PIL import Image
            from ..polaroid.photos import PHOTO_DIR, REAL_PHOTOS
            if src.startswith("builtin:"):
                key = src.split(":", 1)[1]
                if key not in REAL_PHOTOS:
                    return ""
                path = PHOTO_DIR / REAL_PHOTOS[key]
            else:
                path = Path(src)
            if not path.exists():
                return f"The photo {path.name} can't be found."
            with Image.open(path) as im:
                ph = min(im.size)
        except Exception:
            return ""
        film = catalog.FILM_TYPES.get(self.spec.polaroid.film, catalog.FILM_TYPES["600"])
        fill = shotlist.max_fill(self.spec)
        need = int(out_h * fill * film.image_mm[1] / film.card_mm[1] * self.spec.polaroid.photo_zoom)
        if ph < need * 0.5:
            return (f"Your photo is {ph} px on its short side; this framing at this resolution needs about "
                    f"{need} px to look sharp. It will look soft, like an enlarged print.")
        return ""

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
            left_over = [i for i in self.rq.items if i.state in ("waiting", "stopped")]
            if left_over and not self.rq.active:
                self.blender_label.setText(self.blender_label.text() + f"   ·   {len(left_over)} shot(s) from last "
                                           "time are in the render queue: press Start queue to carry on.")
            self.rq.pump()
            self._schedule_draft()
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

    def build_previews(self):
        """Render the hover preview clip of every camera move on this PC's graphics card (once)."""
        from .. import previews
        if not self._need_blender() or self._preview_build_running:
            return
        missing = previews.missing_moves()
        moves = missing or list(catalog.MOVES)
        msg = (f"Render {len(moves)} preview clips (5 s, 480p, 256 samples each) on your graphics card? "
               "This runs in the background; on a fast card expect roughly an hour.")
        if QMessageBox.question(self, "Build shot previews", msg) != QMessageBox.Yes:
            return
        self._preview_build_running = True
        blender = self.blender

        def work():
            def prog(move, i, n, p):
                name = catalog.option_name(catalog.MOVES, move)
                self.bridge.preview_progress.emit(
                    f"Building shot previews: {name} ({i + 1}/{n}), frame {p.done}/{p.total or '?'}")
            done = previews.build(blender, moves, on_progress=prog)
            self.bridge.previews_done.emit(done)
        threading.Thread(target=work, daemon=True).start()

    def _previews_done(self, done: list):
        self._preview_build_running = False
        self.preview_popup.forget()
        self.blender_label.setText(f"Shot previews ready ({len(done)} built). Hover over a camera move to play one.")

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
        from ..paths import default_output_dir
        return self.spec.output.output_dir or str(default_output_dir())

    def queue_render(self):
        if not self._need_blender():
            return
        item = self.rq.add(self.spec)
        when = "now" if self.rq.active and self.rq.running() is item else (
            "when the shots ahead of it finish" if self.rq.active else "when you press Start queue")
        self.blender_label.setText(f"“{item.title}” added to the render queue. It renders {when}.")

    # ------------------------------------------------------------------ real output while rendering
    def _queue_frame(self, item, path: str):
        """A frame of a queued render has finished: show the real output."""
        if self.output_viewer.item is None or (self.queue_panel.selected() is None and item.state == "running"):
            first = self.output_viewer.item is not item
            self.output_viewer.show_item(item)
            if first:
                self.view_tabs.setCurrentWidget(self.output_viewer)
        self.output_viewer.frame_arrived(item, path)

    def _queue_progress(self, item):
        if self.output_viewer.item is None and item.state == "running":
            self.output_viewer.show_item(item)
        self.output_viewer.update_progress(item)

    def _queue_selected(self, item):
        if item is not None:
            self.output_viewer.show_item(item)
            self.view_tabs.setCurrentWidget(self.output_viewer)

    def _regrade(self, src):
        if not src.job_path:
            return
        if not src.spec.output.keep_frames:
            QMessageBox.information(self, "Regrade", "That render didn't keep its HDR frames, so it can't be regraded.")
            return
        spec = src.spec.copy()
        spec.look = self.spec.copy().look
        self.rq.add(spec, "regrade", src.job_path)

    def _queue_finished(self):
        self.blender_label.setText("Render queue finished.")
        kind = self.queue_panel.when_done.currentData()
        if kind not in ("sleep", "shutdown") or sys.platform != "win32":
            return
        what = "go to sleep" if kind == "sleep" else "shut down"
        box = QMessageBox(QMessageBox.Information, "Render queue finished",
                          f"Every shot has rendered. The PC will {what} in 60 seconds.", QMessageBox.Cancel, self)
        left = {"s": 60}

        def tick():
            left["s"] -= 1
            box.setText(f"Every shot has rendered. The PC will {what} in {left['s']} seconds.")
            if left["s"] <= 0:
                timer.stop()
                box.done(QMessageBox.Ok)
        timer = QTimer(box)
        timer.timeout.connect(tick)
        timer.start(1000)
        if box.exec() == QMessageBox.Ok:
            power_action(kind)

    def _load_spec(self, spec: ShotSpec):
        self.spec = spec
        self._load_into_widgets()
        self._schedule_polaroid_preview()
        self._schedule_draft()

    # ------------------------------------------------------------------ draft preview
    # ------------------------------------------------------------------ 3D camera path
    def _schedule_path(self, delay_ms: int = 1500):
        """Rebuild the 3D path after edits, but only while its tab is showing (else just remember it's stale)."""
        if not hasattr(self, "path_panel"):
            return
        self._path_stale = True
        if self.view_tabs.currentWidget() is self.path_panel and self.path_panel.auto.isChecked():
            self._path_timer.start(delay_ms)

    def start_path(self, manual: bool = False):
        if not (self.blender and os.path.exists(self.blender)):
            if manual:
                self._need_blender()
            else:
                self.path_panel.status.setText("The 3D path needs Blender. Use the Blender menu to download or find it.")
            return
        if self.path_job is not None:
            self.path_job.cancel()
        self._path_ticket += 1
        ticket = self._path_ticket
        s = self.spec.copy()
        s.output.resolution = "p360"
        s.output.fps = min(24.0, float(s.output.fps))
        s.output.name = "camera_path"
        s.output.output_dir = str(app_data_dir() / "paths")
        import shutil
        shutil.rmtree(app_data_dir() / "paths", ignore_errors=True)
        job = RenderJob(s, self.blender, "path")
        self.path_job = job
        self._path_stale = False
        self.path_panel.status.setText("Building the set and the camera path…")

        def done(ok, msg, t=ticket):
            if t != self._path_ticket:
                return
            self.path_job = None
            if ok:
                self.path_panel.load(msg)
                self.path_panel.view.highlight = getattr(self, "sel_shot", -1) if self._is_list() else -1
            else:
                self.path_panel.status.setText("Couldn't build the camera path: " + msg)
        job.finished.connect(done)
        th = JobThread(job)
        self.threads[id(job)] = th
        th.start()

    def _schedule_draft(self):
        self._schedule_path()
        if getattr(self, "_loading", False) or not hasattr(self, "draft_player"):
            return
        if self.draft_player.auto.isChecked():
            self._draft_timer.start(2500)

    def draft_spec(self) -> ShotSpec:
        s = self.spec.copy()
        s.output.engine = self.draft_player.engine.currentData() or "eevee"
        s.output.resolution = "p360"
        s.output.quality = "draft"
        s.output.custom_samples = 16 if s.output.engine == "cycles" else 24
        s.output.fps = 12.0
        s.output.codec = "png_seq"
        s.output.keep_frames = False
        s.output.name = "draft"
        s.output.output_dir = str(app_data_dir() / "drafts")
        return s

    def start_draft(self, manual: bool = False):
        if not (self.blender and os.path.exists(self.blender)):
            if manual:
                self._need_blender()
            else:
                self.draft_player.set_status("Drafts need Blender. Use the Blender menu to download or find it.")
            return
        if not manual and self.rq.running() is not None:
            self.draft_player.set_status("Auto drafts wait while the queue is rendering (they'd share the "
                                         "graphics card). Press Make draft to render one anyway.")
            return
        if self.draft_job is not None:
            self.draft_job.cancel()
        self._draft_ticket += 1
        ticket = self._draft_ticket
        spec = self.draft_spec()
        self._clean_old_drafts()
        job = RenderJob(spec, self.blender, "draft")
        self.draft_job = job
        self.draft_player.begin(estimate(spec)[2], spec.output.fps)

        def upd(p, t=ticket):
            if t != self._draft_ticket:
                return
            if p.total:
                self.draft_player.set_status(f"Draft: {p.done}/{p.total} frames" if p.done < p.total else "")
            elif p.message:
                self.draft_player.set_status(p.message)

        def frame(path, t=ticket):
            if t == self._draft_ticket:
                self.draft_player.add_frame(path)

        def done(ok, msg, t=ticket):
            if t != self._draft_ticket:
                return
            self.draft_job = None
            self.draft_player.finish(ok, "" if ok else ("Draft failed: " + msg))
        job.updated.connect(upd)
        job.frame_ready.connect(frame)
        job.finished.connect(done)
        th = JobThread(job)
        self.threads[id(job)] = th
        th.start()

    def _clean_old_drafts(self):
        import shutil
        root = app_data_dir() / "drafts"
        if not root.is_dir():
            return
        for d in root.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

    # ------------------------------------------------------------------ files and presets
    def new_shot(self):
        self.spec = ShotSpec()
        self.spec.output.output_dir = self.settings.value("output_dir", "") or ""
        self.current_file = None
        self._load_into_widgets()
        self._schedule_polaroid_preview()
        self._schedule_draft()

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
            self._schedule_draft()

    def save_shot(self, save_as=False):
        path = self.current_file
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save shot", f"{self.spec.output.name}.rsm.json",
                                                  "Shot files (*.rsm.json)")
        if path:
            self.spec.save(path)
            self.current_file = path

    def export_pack(self):
        """One file with everything the shot needs, for the render server on another machine."""
        from ..pack import EXT, export_pack
        path, _ = QFileDialog.getSaveFileName(self, "Export for render server", f"{self.spec.output.name}{EXT}",
                                              f"Render packs (*{EXT})")
        if not path:
            return
        try:
            out = export_pack(self.spec, path)
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't export", str(exc))
            return
        self.blender_label.setText(f"Saved {out.name}. Copy it into the render server's watch folder, or drag "
                                   "it onto the server window.")

    def apply_preset(self, name: str):
        p = PRESETS.get(name)
        if not p:
            return
        self.spec.scene.mood = "natural"   # a look without a mood goes back to daylight
        self.spec.camera.shots = []
        for section, values in p.items():
            obj = getattr(self.spec, section)
            for k, v in values.items():
                setattr(obj, k, v)
        if self.spec.camera.move == "macro_cut":
            shotlist.set_shots(self.spec, shotlist.shots_of(self.spec))
        self.sel_shot = 0
        self._load_into_widgets()
        self._schedule_draft()
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

    def about(self):
        QMessageBox.about(self, "RealisticShotMaker",
                          f"<b>RealisticShotMaker {__version__}</b><br>Cinematic documentary insert shots, path "
                          "traced with Blender Cycles.<br><br>Handwriting fonts: SIL Open Font License. "
                          "Sample photos: CC0.")

    def wait_for_threads(self, ms: int = 8000):
        """Give background work (renders being stopped, drafts, previews) a moment to wind down."""
        threads = (list(self.threads.values()) + [i.thread for i in self.rq.items if i.thread is not None]
                   + list(getattr(self, "_preview_threads", [])))
        for th in threads:
            try:
                if th.isRunning():
                    th.wait(ms)
            except RuntimeError:
                pass

    def closeEvent(self, ev):
        r = self.rq.running()
        if r is not None and QMessageBox.question(
                self, "Render running",
                "A shot is still rendering. Stop it and quit? Its finished frames are kept, and the queue "
                "carries on from there next time.") != QMessageBox.Yes:
            ev.ignore()
            return
        if self.draft_job is not None:
            self.draft_job.cancel()
        self.rq.shutdown()
        ev.accept()
