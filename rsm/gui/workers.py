"""Background work for the GUI: polaroid previews, preview frames and full renders."""
from __future__ import annotations

import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage

from ..job import build_job
from ..runner import Progress, RenderProcess, encode
from ..spec import ShotSpec


def pil_to_qimage(im) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    q = QImage(data, im.width, im.height, QImage.Format_RGBA8888)
    return q.copy()


class PolaroidPreview(QThread):
    ready = Signal(QImage, int)

    def __init__(self, spec: ShotSpec, ticket: int, height: int = 520):
        super().__init__()
        self.spec = spec.copy()
        self.ticket = ticket
        self.height = height

    def run(self):
        from ..polaroid import preview_image
        try:
            im = preview_image(self.spec.polaroid, self.height)
            self.ready.emit(pil_to_qimage(im), self.ticket)
        except Exception:
            traceback.print_exc()


class RenderJob(QObject):
    """One queued job. mode: 'still' (preview frame) or 'video'."""
    updated = Signal(object)       # Progress
    finished = Signal(bool, str)   # ok, message / output path
    frame_ready = Signal(str)      # path of the newest finished frame

    def __init__(self, spec: ShotSpec, blender: str, mode: str = "video", still_at: float = 0.5,
                 job_path: Path | None = None):
        super().__init__()
        self.spec = spec.copy()
        self.blender = blender
        self.mode = mode
        self.still_at = still_at
        self.job_path = job_path
        self.proc: RenderProcess | None = None
        self.cancelled = False
        self.output = ""
        self.progress = Progress()

    def run(self):
        try:
            if self.job_path is None:
                self.progress.stage = "preparing"
                self.progress.message = "Preparing textures…"
                self.updated.emit(self.progress)

                def note(msg):
                    self.progress.message = msg
                    self.updated.emit(self.progress)
                self.job_path = build_job(self.spec, preview=self.mode == "still", progress=note)
            if self.cancelled:
                self.finished.emit(False, "Cancelled")
                return
            extra = []
            if self.mode == "still":
                out = str(Path(self.job_path).parent / "work" / "preview")
                extra = ["--still", f"{self.still_at:.4f}", "--still-out", out]
            last_frame = {"p": ""}

            def on_update(p: Progress):
                self.progress = p
                self.updated.emit(p)
                if p.last_frame_path and p.last_frame_path != last_frame["p"]:
                    last_frame["p"] = p.last_frame_path
                    self.frame_ready.emit(p.last_frame_path)
            self.proc = RenderProcess(self.blender, Path(self.job_path), on_update, extra).start()
            code = self.proc.wait()
            if self.cancelled:
                self.finished.emit(False, "Cancelled. Finished frames are kept; start it again to resume.")
                return
            if code != 0 or self.proc.progress.stage == "error":
                self.finished.emit(False, self.proc.progress.message or "Render failed")
                return
            if self.mode == "still":
                self.output = self.proc.progress.last_frame_path
                self.finished.emit(True, self.output)
                return
            self.progress.stage = "encoding"
            self.progress.message = "Encoding video…"
            self.updated.emit(self.progress)
            out = encode(Path(self.job_path))
            self.output = str(out)
            self.finished.emit(True, self.output)
        except Exception as exc:
            traceback.print_exc()
            self.finished.emit(False, str(exc))

    def cancel(self):
        self.cancelled = True
        if self.proc:
            self.proc.cancel()


class JobThread(QThread):
    def __init__(self, job: RenderJob):
        super().__init__()
        self.job = job

    def run(self):
        self.job.run()
