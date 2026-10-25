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


def test_job_frames_where_they_make_sense(tmp_path):
    s = ShotSpec()
    s.scene.location = "study_desk"
    s.polaroid.print_type = "framed"
    job = json.load(open(build_job(s, tmp_path / "a", preview=True)))
    assert job["polaroid"].get("frame")
    s.scene.location = "investigation_board"
    s.scene.placement = "pinned"
    job = json.load(open(build_job(s, tmp_path / "b", preview=True)))
    assert not job["polaroid"].get("frame")      # stuck on the board: it's a print
