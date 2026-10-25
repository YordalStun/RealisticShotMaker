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
