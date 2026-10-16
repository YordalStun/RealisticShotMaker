import json

from rsm.estimate import estimate
from rsm.job import resolve
from rsm.spec import ShotSpec


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_queue_survives_restart(tmp_path):
    _app()
    from rsm.gui.render_queue import RenderQueue, STOPPED, WAITING
    store = tmp_path / "queue.json"
    q = RenderQueue(lambda: "", store)          # no Blender: nothing starts
    a = ShotSpec()
    a.output.name = "first"
    b = ShotSpec()
    b.output.name = "second"
    ia, ib = q.add(a), q.add(b)
    assert [i.state for i in q.items] == [WAITING, WAITING]
    q.move(ib, -1)
    assert [i.spec.output.name for i in q.items] == ["second", "first"]
    # pretend the first was rendering when the program closed
    ib.state = "running"
    ib.job_path = str(tmp_path / "second" / "job.json")
    ib.done_frames = 30
    q.save()
    q2 = RenderQueue(lambda: "", store)
    assert [i.spec.output.name for i in q2.items] == ["second", "first"]
    assert q2.items[0].state == STOPPED and q2.items[0].done_frames == 30
    assert q2.items[0].job_path.endswith("job.json")
    assert not q2.active                        # left-over work waits for the user to press Start
    q2.resume(q2.items[0])
    assert q2.items[0].state == WAITING
    assert json.loads(store.read_text())["items"][0]["state"] == WAITING


def test_estimate_and_draft_engine():
    s = ShotSpec()
    per, total, frames = estimate(s)
    assert frames == round(s.camera.duration * s.output.fps)
    assert total > per * frames
    s.output.engine = "eevee"
    s.output.resolution = "p360"
    r = resolve(s)
    assert r["engine"] == "eevee" and r["width"] == 640


def test_draft_player_frames(tmp_path):
    _app()
    from PIL import Image
    from rsm.gui.draft_player import DraftPlayer
    p = DraftPlayer()
    p.begin(4, 12)
    for i in (1, 2):
        f = tmp_path / f"frame_{i:05d}.png"
        Image.new("RGB", (64, 36), (i * 40, 0, 0)).save(f)
        p.add_frame(str(f))
    assert p.order == [1, 2]
    p.finish(True)
    assert not p.rendering
