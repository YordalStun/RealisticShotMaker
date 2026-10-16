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


def test_gui_starts():
    from PySide6.QtWidgets import QApplication
    from rsm.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.apply_preset("Attic discovery")
    assert w.spec.scene.location == "attic_trunk"
    w.close()
