from rsm import shotlist
from rsm.spec import ShotSpec


def test_single_shot_and_legacy_close_up_cut():
    s = ShotSpec()
    assert [x["move"] for x in shotlist.resolve(s)] == [s.camera.move]
    s.camera.move = "macro_cut"
    s.camera.cut_at = 0.4
    r = shotlist.resolve(s)
    assert [x["move"] for x in r] == ["macro_drift", "push_in"]
    assert abs(r[1]["t0"] - 0.4) < 1e-6 and r[0]["fill"] == s.camera.macro_fill


def test_split_edit_remove_keeps_total_length():
    s = ShotSpec()
    s.camera.duration = 9.0
    shots = shotlist.split(shotlist.shots_of(s), 0, 1 / 3)
    shots = shotlist.split(shots, 1, 0.5)
    shots[1]["focal_mm"] = 35.0
    shotlist.set_shots(s, shots)
    assert len(s.camera.shots) == 3 and abs(s.camera.duration - 9.0) < 1e-6
    r = shotlist.resolve(s)
    assert [round(x["t0"], 3) for x in r] == [0.0, 0.333, 0.667] and r[1]["focal_mm"] == 35.0
    shotlist.set_shots(s, shotlist.remove(shotlist.shots_of(s), 2))
    assert len(s.camera.shots) == 2 and abs(s.camera.duration - 9.0) < 1e-6
    shotlist.set_shots(s, shotlist.remove(shotlist.shots_of(s), 1))
    assert s.camera.shots == [] and abs(s.camera.duration - 9.0) < 1e-6


def test_shot_list_survives_save_and_load(tmp_path):
    s = ShotSpec()
    shots = shotlist.split(shotlist.shots_of(s), 0)
    shots[0]["move"] = "macro_drift"
    shotlist.set_shots(s, shots)
    s.save(tmp_path / "a.rsm.json")
    t = ShotSpec.load(tmp_path / "a.rsm.json")
    assert [x["move"] for x in shotlist.resolve(t)] == ["macro_drift", s.camera.shots[1]["move"]]


def test_gui_edits_each_shot_separately():
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from rsm.gui.fields import SECTIONS
    from rsm.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.apply_preset("Memory close-up cut")
    shots = shotlist.shots_of(w.spec)
    assert [s["move"] for s in shots] == ["macro_drift", "push_in"]
    field = {f.path: f for fs in SECTIONS.values() for f in fs}
    w._shot_selected(1)
    w._changed(field["camera.focal_mm"], 35.0)
    w._changed(field["camera.move"], "slide_right")
    shots = shotlist.shots_of(w.spec)
    assert shots[1]["focal_mm"] == 35.0 and shots[1]["move"] == "slide_right"
    assert shots[0]["focal_mm"] != 35.0 and shots[0]["move"] == "macro_drift"   # the other side untouched
    w._shot_cut()                                                              # a third shot
    assert len(shotlist.shots_of(w.spec)) == 3 and w.sel_shot == 2
    w._shot_remove()
    assert len(shotlist.shots_of(w.spec)) == 2
    w.close()
    w.wait_for_threads()
    shiboken6.delete(w.preview_popup)
    shiboken6.delete(w)
    app.processEvents()


def test_path_view_draws_a_shot_list(tmp_path):
    """The 3D view can draw a multi-shot path without errors, from outside and through the camera."""
    import json
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from rsm.gui.path_view import PathPanel
    app = QApplication.instance() or QApplication([])
    box = [[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    frames = [{"p": [0.5 + 0.01 * i, -1.5, 1.0], "f": [0, 1, -0.2], "u": [0, 0, 1], "fov": 0.5, "fd": 1.2,
               "shot": 0 if i < 5 else 1} for i in range(10)]
    data = {"version": 1, "fps": 24, "aspect": 1.78, "frames": frames,
            "shots": [{"move": "macro_drift", "t0": 0, "t1": 0.5}, {"move": "push_in", "t0": 0.5, "t1": 1}],
            "boxes": [{"name": "Desk", "c": box, "col": [0.5, 0.4, 0.3], "room": False},
                      {"name": "Floor", "c": [[x * 4 - 2, y * 4 - 2, z * 0.05 - 0.05] for x, y, z in box],
                       "col": [0.4, 0.4, 0.4], "room": True}],
            "prints": [{"quad": [[0.4, 0.4, 1.0], [0.5, 0.4, 1.0], [0.5, 0.4, 1.1], [0.4, 0.4, 1.1]], "hero": True,
                        "image": ""}]}
    f = tmp_path / "path.json"
    f.write_text(json.dumps(data))
    w = PathPanel()
    w.resize(640, 400)
    w.load(str(f))
    assert "2 shots" in w.status.text() and "1 cut" in w.status.text()
    w.show_shot(1)
    assert w.view.frame == 5
    w.grab()
    w.through.setChecked(True)
    w.grab()
    shiboken6.delete(w)
    app.processEvents()
