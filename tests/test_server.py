import os
import zipfile

from PIL import Image

from rsm.pack import export_pack, import_pack
from rsm.spec import ShotSpec


def _shot_with_photo(tmp_path):
    photo = tmp_path / "my photo.jpg"
    Image.new("RGB", (40, 30), (200, 100, 50)).save(photo)
    s = ShotSpec()
    s.output.name = "nan_kitchen"
    s.polaroid.photo = str(photo)
    s.output.output_dir = str(tmp_path / "somewhere on my pc")
    return s


def test_pack_carries_settings_and_photo(tmp_path):
    s = _shot_with_photo(tmp_path)
    s.scene.mood = "noir_blinds"
    pack = export_pack(s, tmp_path / "shot")
    assert pack.suffix == ".rsmpack"
    names = zipfile.ZipFile(pack).namelist()
    assert "shot.rsm.json" in names and any(n.startswith("media/") for n in names)
    os.remove(s.polaroid.photo)                       # the server machine doesn't have the original
    got = import_pack(pack, tmp_path / "server" / "p1")
    assert got.scene.mood == "noir_blinds" and got.output.name == "nan_kitchen"
    assert os.path.exists(got.polaroid.photo) and "server" in got.polaroid.photo
    assert got.output.output_dir == ""                # the server chooses where renders go


def test_pack_rejects_paths_escaping_the_folder(tmp_path):
    bad = tmp_path / "bad.rsmpack"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("pack.json", "{}")
        z.writestr("../../evil.txt", "x")
    try:
        import_pack(bad, tmp_path / "dest")
        raise AssertionError("should have refused")
    except ValueError:
        pass
    assert not (tmp_path / "evil.txt").exists()


def test_server_picks_up_dropped_packs(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    import shiboken6
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("RSM_BLENDER", str(tmp_path / "no-blender.exe"))
    from rsm.gui import server_window
    monkeypatch.setattr(server_window, "find_blender", lambda: (None, None))
    w = server_window.ServerWindow()
    w.watch = tmp_path / "drop"
    w.watch.mkdir()
    export_pack(_shot_with_photo(tmp_path), w.watch / "a")
    w.scan_watch()          # first sight: still maybe copying
    assert not w.rq.items
    w.scan_watch()          # size unchanged: take it
    assert [i.spec.output.name for i in w.rq.items] == ["nan_kitchen"]
    assert (w.watch / "Queued" / "a.rsmpack").exists()
    assert w.rq.items[0].spec.output.output_dir == str(w.out_root)
    w.rq.shutdown()
    shiboken6.delete(w)
    app.processEvents()
