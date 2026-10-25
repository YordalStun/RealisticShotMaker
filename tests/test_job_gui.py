import json

from rsm.job import build_job
from rsm.spec import ShotSpec


def test_build_job(tmp_path):
    s = ShotSpec()
    s.output.resolution = "preview"
    s.scene.placement = "pile"
    path = build_job(s, tmp_path, preview=True)
    job = json.loads(path.read_text())
    assert job["resolved"]["width"] == 960
    assert job["resolved"]["frame_end"] == round(s.camera.duration * s.output.fps)
    assert len(job["extra_prints"]) == 8
    assert job["lens"]["blades"] >= 3
    for p in job["frame_photos"]:
        assert p.endswith(".png")


def test_job_paths_are_absolute_even_for_a_relative_output_folder(tmp_path, monkeypatch):
    import os
    monkeypatch.chdir(tmp_path)
    s = ShotSpec()
    s.output.resolution = "p360"
    path = build_job(s, "relative_out", preview=True)
    job = json.loads(path.read_text())
    assert path.is_absolute()
    for key in ("root", "work", "exr", "frames"):
        assert os.path.isabs(job["paths"][key])
    assert os.path.isabs(job["polaroid"]["files"]["color"])


def test_gui_starts():
    from PySide6.QtWidgets import QApplication
    from rsm.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.apply_preset("Attic discovery")
    assert w.spec.scene.location == "attic_trunk"
    w.close()
    w.wait_for_threads()
    _dispose(app, w)


def _dispose(app, *objs):
    """Delete Qt objects while the application still exists (tearing them down at interpreter exit crashes)."""
    import shiboken6
    for o in objs:
        if shiboken6.isValid(o):
            shiboken6.delete(o)
    app.processEvents()
