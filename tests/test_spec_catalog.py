import json

from rsm import catalog
from rsm.spec import ShotSpec


def test_roundtrip(tmp_path):
    s = ShotSpec()
    s.polaroid.caption = "Hello"
    s.camera.move = "rack_in"
    s.output.fps = 25.0
    p = tmp_path / "a.rsm.json"
    s.save(p)
    t = ShotSpec.load(p)
    assert t.to_dict() == s.to_dict()


def test_unknown_and_missing_keys_are_tolerated():
    s = ShotSpec.from_dict({"polaroid": {"caption": "x", "not_a_field": 1}, "camera": {"fstop": "2.8"}})
    assert s.polaroid.caption == "x"
    assert s.camera.fstop == 2.8
    assert s.scene.location == "study_desk"


def test_defaults_reference_real_catalog_entries():
    s = ShotSpec()
    assert s.polaroid.film in catalog.FILM_TYPES
    assert s.polaroid.condition in catalog.CONDITIONS
    assert s.scene.location in catalog.LOCATIONS
    assert s.camera.move in catalog.MOVES
    assert s.camera.lens in catalog.LENSES
    assert s.camera.body in catalog.BODIES
    assert s.look.grade in catalog.GRADES
    assert s.output.resolution in catalog.RESOLUTIONS
    assert s.output.quality in catalog.QUALITY
    assert s.output.codec in catalog.CODECS


def test_conditions_only_set_known_fields():
    s = ShotSpec()
    for cond in catalog.CONDITIONS.values():
        for k in cond:
            if k != "name":
                assert hasattr(s.polaroid, k), k


def test_every_location_has_a_module():
    import importlib.util
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for loc in catalog.LOCATIONS:
        assert os.path.exists(os.path.join(here, "rsm_blender", "rsmb", "locations", f"{loc}.py")), loc


def test_film_grades_match_catalog():
    from rsmb import filmlab
    for g in catalog.GRADES:
        assert g in filmlab.GRADES


def test_portable_mode_keeps_everything_beside_the_program(tmp_path, monkeypatch):
    from rsm import paths
    monkeypatch.setattr(paths, "install_dir", lambda: tmp_path)
    assert not paths.is_portable()
    (tmp_path / "portable.txt").write_text("portable")
    assert paths.is_portable()
    assert paths.app_data_dir() == tmp_path / "data"
    assert paths.default_output_dir() == tmp_path / "Renders"
    assert paths.bundled_blender() is None
    (tmp_path / "blender").mkdir()
    (tmp_path / "blender" / "blender.exe").write_text("")
    assert paths.bundled_blender() == tmp_path / "blender" / "blender.exe"
