import numpy as np
import pytest

from rsm import catalog
from rsm.polaroid import generate, preview_image
from rsm.spec import PolaroidSpec


@pytest.mark.parametrize("film", list(catalog.FILM_TYPES))
def test_every_film_generates(film):
    p = PolaroidSpec(film=film)
    m = generate(p, 4.0)
    w_mm, h_mm = catalog.FILM_TYPES[film].card_mm
    assert m.color.shape[:2] == (round(h_mm * 4), round(w_mm * 4))
    assert m.color.min() >= 0 and m.color.max() <= 1
    assert m.alpha.max() == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("cond", list(catalog.CONDITIONS))
def test_every_condition_generates(cond, tmp_path):
    p = PolaroidSpec(photo="builtin:cat")
    for k, v in catalog.CONDITIONS[cond].items():
        if k != "name":
            setattr(p, k, v)
    meta = generate(p, 5.0).save(tmp_path, cond)
    for f in meta["files"].values():
        assert (tmp_path / f.split("/")[-1].split("\\")[-1]).exists()


def test_damage_changes_the_print():
    clean = generate(PolaroidSpec(scratches=0, dust=0, fingerprints=0, seed=3), 5.0)
    worn = generate(PolaroidSpec(scratches=1, dust=1, fingerprints=1, seed=3), 5.0)
    assert np.abs(clean.rough - worn.rough).mean() > 0.005


def test_pin_hole_and_creases_reported():
    m = generate(PolaroidSpec(pin_hole=True, creases=0.8, dog_ear=0.5, seed=9), 5.0)
    assert m.meta["pin_hole"] is not None
    assert m.meta["creases"]
    assert m.meta["dog_ear"]["corner"] in ("tl", "tr", "bl", "br")


def test_preview_image_is_rgba():
    im = preview_image(PolaroidSpec(), 200)
    assert im.mode == "RGBA"
    assert im.size[1] == pytest.approx(200, abs=3)


def test_user_photo(tmp_path):
    from PIL import Image
    path = tmp_path / "me.jpg"
    Image.new("RGB", (640, 480), (200, 30, 30)).save(path)
    m = generate(PolaroidSpec(photo=str(path), fade=0, age_years=0, color_cast="none", chemical_edge=0), 5.0)
    h, w = m.color.shape[:2]
    centre = m.color[h // 3, w // 2]
    assert centre[0] > centre[2]  # still red
