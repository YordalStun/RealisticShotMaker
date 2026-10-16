"""Shot-type preview clips: short 480p loops of every camera move, path traced at high quality.

They are shown when hovering over a camera move in the app. A few ship with the program
(rsm/assets/previews); the full library is built once on the user's own graphics card and
stored in the app data folder.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

from PIL import Image

from . import catalog
from .blender_locator import app_data_dir
from .job import build_job
from .runner import RenderProcess
from .spec import ShotSpec

BUNDLED = Path(__file__).resolve().parent / "assets" / "previews"
PREVIEW_W, PREVIEW_H = 854, 480
PREVIEW_SECONDS = 5.0
PREVIEW_FPS = 24.0
PREVIEW_SAMPLES = 256        # high-quality ray tracing; the denoiser cleans up the rest


def user_dir() -> Path:
    d = app_data_dir() / "previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def preview_spec(move: str, seconds: float = PREVIEW_SECONDS, fps: float = PREVIEW_FPS,
                 samples: int = PREVIEW_SAMPLES) -> ShotSpec:
    """The same set and print for every move, so the clips compare like for like."""
    s = ShotSpec()
    s.scene.location = "study_desk"
    s.scene.time_of_day = "golden"
    s.scene.light_shafts = 0.35
    s.polaroid.photo = "builtin:cat"
    s.polaroid.caption = "Chelsea, 2004"
    s.camera.move = move
    s.camera.duration = seconds
    if move == "macro_cut":
        s.camera.cut_at = 0.45
    if move == "top_down":
        s.scene.placement = "flat"
    s.output.resolution = "p480"
    s.output.fps = fps
    s.output.custom_samples = samples
    s.output.quality = "high"
    s.output.codec = "png_seq"
    s.output.name = f"preview_{move}"
    s.output.keep_frames = False
    return s


def frames_for(move: str) -> list[Path]:
    """Preview frames for a move: the user's own library first, then the ones shipped with the app."""
    for root in (user_dir(), BUNDLED):
        d = root / move
        if d.is_dir():
            frames = sorted(d.glob("*.jpg"))
            if frames:
                return frames
    return []


def missing_moves() -> list[str]:
    return [m for m in catalog.MOVES if not frames_for(m)]


def store_frames(job_path: Path, move: str, dest_root: Path) -> Path:
    """Convert a finished job's developed frames into the compact preview format."""
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    src = Path(job["paths"]["frames"])
    dest = dest_root / move
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for i, f in enumerate(sorted(src.glob("frame_*.png"))):
        im = Image.open(f).convert("RGB").resize((PREVIEW_W, PREVIEW_H), Image.LANCZOS)
        im.save(dest / f"{i:03d}.jpg", quality=88, optimize=True)
    (dest / "info.json").write_text(json.dumps({"move": move, "fps": job["resolved"]["fps"],
                                                 "samples": job["resolved"]["samples"]}), encoding="utf-8")
    return dest


def _unfinished_job(work: Path, spec: ShotSpec) -> Path | None:
    """A preview job for the same move and settings that was stopped part way: carry on with it so the
    frames already rendered aren't thrown away."""
    from . import __version__
    want = json.loads(json.dumps(spec.to_dict()))
    for jp in sorted(work.glob(f"{spec.output.name}_*/job.json"), reverse=True):
        try:
            job = json.loads(jp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("spec") == want and job.get("app_version") == __version__:
            return jp
        shutil.rmtree(jp.parent, ignore_errors=True)  # different settings or an older version: start again
    return None


def build(blender: str, moves: list[str] | None = None, dest_root: Path | None = None,
          on_progress: Callable[[str, int, int, object], None] | None = None,
          seconds: float = PREVIEW_SECONDS, fps: float = PREVIEW_FPS, samples: int = PREVIEW_SAMPLES,
          should_stop: Callable[[], bool] = lambda: False) -> list[str]:
    """Render preview clips one move at a time. Returns the moves that finished."""
    moves = moves or list(catalog.MOVES)
    dest_root = dest_root or user_dir()
    work = app_data_dir() / "preview_jobs"
    done = []
    for i, move in enumerate(moves):
        if should_stop():
            break
        spec = preview_spec(move, seconds, fps, samples)
        job = _unfinished_job(work, spec) or build_job(spec, work, preview=False)
        proc = RenderProcess(blender, job,
                             lambda p, m=move, i=i: on_progress and on_progress(m, i, len(moves), p)).start()
        if proc.wait() != 0:
            if on_progress:
                on_progress(move, i, len(moves), proc.progress)
            continue
        store_frames(job, move, dest_root)
        shutil.rmtree(Path(job).parent, ignore_errors=True)
        done.append(move)
    return done
