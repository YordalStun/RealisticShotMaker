import numpy as np

from rsm import catalog
from rsmb import filmlab, lens


def test_filmlab_outputs_display_range(tmp_path):
    rng = np.random.default_rng(0)
    lin = (rng.random((90, 160, 3)) * 4).astype(np.float32)
    for grade in filmlab.GRADES:
        lab = filmlab.FilmLab(dict(grade=grade, grain=0.5, halation=0.5, bloom=0.5, gate_weave=0.5, flicker=0.5,
                                   streak=0.5, lens_dirt=0.5, vignette=0.5, letterbox="2.39"), 90, 160)
        out = lab.process(lin, 3)
        assert out.shape == lin.shape
        assert out.min() >= 0 and out.max() <= 1
    filmlab.write_png16(str(tmp_path / "a.png"), out)
    from PIL import Image
    assert Image.open(tmp_path / "a.png").size == (160, 90)


def test_auto_exposure_is_fixed_per_shot():
    lab = filmlab.FilmLab(dict(grade="natural"), 40, 60)
    dark = np.full((40, 60, 3), 0.01, np.float32)
    a = lab.process(dark, 0)
    b = lab.process(dark * 4, 1)
    assert b.mean() > a.mean()  # gain was not re-metered on the brighter frame


def test_lens_shader_generation():
    import dataclasses
    for l in catalog.LENSES.values():
        src = lens.build_osl(dataclasses.asdict(l), 50.0)
        assert "shader rsm_lens" in src
        assert "$" not in src
