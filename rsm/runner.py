"""Runs Blender for a job, parses its progress and encodes the result with ffmpeg."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import catalog
from .job import BLENDER_DIR
from .spec import ShotSpec

ENTRY = BLENDER_DIR / "entry.py"


@dataclass
class Progress:
    stage: str = "starting"
    frame: int = 0
    done: int = 0
    total: int = 0
    last_frame_seconds: float = 0.0
    elapsed: float = 0.0
    eta: float | None = None
    message: str = ""
    device: str = ""
    last_frame_path: str = ""
    last_thumb_path: str = ""      # small preview copy of the newest finished frame (quick for the app to show)
    sample: int = 0                # progress inside the frame being rendered
    samples: int = 0
    log: list = field(default_factory=list)

    @property
    def fraction(self) -> float:
        return self.done / self.total if self.total else 0.0


def blender_command(blender: str | os.PathLike, job_path: Path, extra: list[str] | None = None) -> list[str]:
    """Build the command line. `blender` may be a Blender executable, or a Python interpreter that
    has the bpy module (developer mode, detected by name)."""
    b = str(blender)
    args = ["--job", str(job_path)] + (extra or [])
    name = os.path.basename(b).lower()
    if name.startswith("python"):
        shim = Path(__file__).resolve().parent.parent / "tools" / "bpy_shim.py"
        return [b, str(shim), "--"] + args
    return [b, "-b", "--factory-startup", "-noaudio", "-P", str(ENTRY), "--"] + args


class RenderProcess:
    """Runs a Blender job in the background. Call start(), then poll .progress or pass a callback."""

    def __init__(self, blender: str, job_path: Path, on_update: Callable[[Progress], None] | None = None,
                 extra_args: list[str] | None = None):
        self.cmd = blender_command(blender, job_path, extra_args)
        self.job_path = Path(job_path)
        self.progress = Progress()
        self.on_update = on_update
        self.proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self.returncode: int | None = None
        self._started = 0.0
        self._frame_times: list[float] = []

    def start(self):
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        self._started = time.time()
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        return self

    def _emit(self):
        if self.on_update:
            try:
                self.on_update(self.progress)
            except Exception:
                pass

    def _read(self):
        p = self.progress
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.rstrip()
            if not line.startswith("RSM "):
                if "Sample" in line and "Fra:" in line:
                    # Blender's own progress: "Fra:12 ... | Sample 64/512"
                    try:
                        frag = line.split("Sample", 1)[1].strip().split()[0]
                        a, b = frag.split("/")
                        p.sample, p.samples = int(a), int(b)
                        p.message = f"Frame {p.done + 1} of {p.total}: sample {a} of {b}" if p.total else \
                            f"Frame {p.frame}: sample {a} of {b}"
                        self._emit()
                    except (IndexError, ValueError):
                        pass
                else:
                    p.log.append(line)
                    p.log = p.log[-300:]
                continue
            try:
                ev = json.loads(line[4:])
            except json.JSONDecodeError:
                continue
            kind = ev.get("kind")
            p.elapsed = time.time() - self._started
            if kind == "device":
                p.device = ev.get("device", "")
                p.message = f"Rendering on {p.device}"
            elif kind == "scene_built":
                p.stage = "rendering"
                p.message = "Scene built"
            elif kind == "frame_start":
                p.sample, p.samples = 0, 0
                p.frame = ev["frame"]
                p.total = ev["total"]
                p.message = f"Rendering frame {ev['index'] + 1} of {ev['total']}"
            elif kind == "frame_rendered":
                p.last_frame_seconds = ev.get("seconds", 0.0)
                self._frame_times.append(p.last_frame_seconds)
            elif kind in ("frame_done", "frame_skip"):
                p.done = ev["index"] + 1
                p.total = ev["total"]
                if ev.get("path"):
                    p.last_frame_path = ev["path"]
                if ev.get("thumb"):
                    p.last_thumb_path = ev["thumb"]
                recent = self._frame_times[-8:]
                if recent:
                    avg = sum(recent) / len(recent)
                    p.eta = avg * (p.total - p.done)
            elif kind == "frame_developed":
                p.stage = "developing"
                p.done = ev["index"] + 1
                p.total = ev["total"]
                p.last_frame_path = ev.get("path", "")
                p.message = f"Developing frame {p.done} of {p.total}"
            elif kind == "done":
                p.stage = "rendered"
                p.message = "Frames developed"
            elif kind == "still_done":
                p.stage = "done"
                p.last_frame_path = ev["path"]
                p.message = "Preview ready"
            elif kind == "render_done":
                p.stage = "rendered"
                p.message = "All frames rendered"
            elif kind == "error":
                p.stage = "error"
                p.message = ev.get("message", "Unknown error")
                p.log.append(ev.get("trace", ""))
            elif kind == "warning":
                p.log.append("WARNING " + ev.get("message", ""))
            self._emit()
        self.returncode = self.proc.wait()
        if self.returncode != 0 and p.stage != "error":
            p.stage = "error"
            p.message = "Blender stopped unexpectedly. See the log for details."
        self._emit()

    def wait(self) -> int:
        if self._thread:
            self._thread.join()
        return self.returncode if self.returncode is not None else -1

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.progress.stage = "cancelled"
        self.progress.message = "Cancelled. Finished frames are kept, so the render can be resumed."
        self._emit()


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def encode(job_path: Path, ffmpeg: str | None = None, on_line: Callable[[str], None] | None = None) -> Path | None:
    """Encode the developed PNG frames of a job into the chosen video format."""
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    spec = ShotSpec.from_dict(job["spec"])
    codec = catalog.CODECS.get(spec.output.codec, catalog.CODECS["h265_10"])
    frames_dir = Path(job["paths"]["frames"])
    root = Path(job["paths"]["root"])
    if codec.sequence:
        if codec.id == "exr_seq":
            return Path(job["paths"]["exr"])
        return frames_dir
    ffmpeg = ffmpeg or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found. Install it or put ffmpeg.exe next to the program.")
    fps = job["resolved"]["fps"]
    fps_str = {23.976: "24000/1001", 29.97: "30000/1001"}.get(round(fps, 3), str(fps))
    out = root / f"{spec.output.name or 'shot'}.{codec.container}"
    cmd = [ffmpeg, "-y", "-hide_banner", "-framerate", fps_str, "-start_number", str(job["resolved"]["frame_start"]),
           "-i", str(frames_dir / "frame_%05d.png"), *codec.ffmpeg_args,
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-r", fps_str, str(out)]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    assert proc.stdout
    for line in proc.stdout:
        if on_line:
            on_line(line.rstrip())
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the video. See the log.")
    if not spec.output.keep_frames:
        shutil.rmtree(Path(job["paths"]["exr"]), ignore_errors=True)
    return out
