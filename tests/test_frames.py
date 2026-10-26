import json

from rsm.job import build_job
from rsm.polaroid.card import generate, layout_for, preview_image
from rsm.spec import PolaroidSpec, ShotSpec


def test_instant_layout_unchanged_by_default():
    p = PolaroidSpec()
    assert p.print_type == "instant" and not p.fit_photo_aspect
    lay = layout_for(p)
    assert lay.frame is None
    assert tuple(lay.card_mm) == (88.0, 107.0)


def test_fit_keeps_borders_and_area():
    a = layout_for(PolaroidSpec())
    b = layout_for(PolaroidSpec(photo="builtin:beach", fit_photo_aspect=True))   # 3:2 picture
    aw, ah = a.image_mm
    bw, bh = b.image_mm
    assert abs(bw / bh - 1.5) < 0.01
    assert abs(bw * bh - aw * ah) / (aw * ah) < 0.02
    assert abs((b.card_mm[0] - bw) - (a.card_mm[0] - aw)) < 0.01      # side borders kept


def test_framed_layout_and_meta(tmp_path):
    p = PolaroidSpec(photo="builtin:beach", print_type="framed", frame_style="oak", frame_size="6x4", frame_mat=True)
    lay = layout_for(p)
    fr = lay.frame
    assert fr["style"] == "oak" and fr["mat"]
    assert fr["outer_mm"][0] > fr["inner_mm"][0] > fr["window_mm"][0]
    maps = generate(p, 3.0)
    m = maps.meta
    assert m["kind"] == "framed" and m["card_mm"] == list(fr["outer_mm"])
    assert m["thickness_mm"] == fr["depth_mm"] and m["curl"] == 0
    im = preview_image(p, 400)
    assert abs(im.size[0] / im.size[1] - fr["outer_mm"][0] / fr["outer_mm"][1]) < 0.02


def test_the_set_decides_prints_or_frames(tmp_path):
    s = ShotSpec()
    s.scene.location = "study_desk"
    s.polaroid.print_type = "framed"
    job = json.load(open(build_job(s, tmp_path / "a", preview=True)))
    assert not job["polaroid"].get("frame")          # a print set: it's a print
    s.scene.location = "hallway_frames"
    s.scene.placement = "wall"
    s.polaroid.print_type = "instant"
    job = json.load(open(build_job(s, tmp_path / "b", preview=True)))
    assert job["polaroid"].get("frame")               # a frame set: framed, and so are the others on the wall
    assert len(job["extra_prints"]) == 9 and all(m.get("frame") for m in job["extra_prints"])
    styles = {m["frame"]["style"] for m in job["extra_prints"]}
    assert len(styles) > 2


def test_frame_orientation():
    p = PolaroidSpec(photo="builtin:beach", print_type="framed", frame_orientation="portrait")
    w, h = layout_for(p).card_mm
    assert h > w


def test_gui_print_type_follows_set():
    from PySide6.QtWidgets import QApplication
    from rsm.gui.fields import SECTIONS
    from rsm.gui.main_window import MainWindow
    import shiboken6
    app = QApplication.instance() or QApplication([])  # noqa: F841
    w = MainWindow()
    f = {fl.path: fl for sec in SECTIONS.values() for fl in sec}
    w._changed(f["scene.location"], "sideboard_frames")
    assert w.spec.polaroid.print_type == "framed" and w.spec.camera.move == "frame_rack"
    w._changed(f["polaroid.print_type"], "instant")
    assert not __import__("rsm.catalog", fromlist=["x"]).LOCATIONS[w.spec.scene.location].frames
    assert w.spec.camera.move not in ("frame_track", "frame_rack", "frame_reflection", "frame_tilt")
    w.wait_for_threads()
    w.close()
    shiboken6.delete(w)
