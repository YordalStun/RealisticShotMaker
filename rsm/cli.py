"""Command line:

    python -m rsm render shot.rsm.json [--blender PATH]      full render + encode
    python -m rsm still shot.rsm.json --at 0.5 [--blender PATH]
    python -m rsm job shot.rsm.json                           only build the job folder
    python -m rsm regrade path/to/job.json                    re-run the film lab on kept HDR frames
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .blender_locator import find_blender
from .job import build_job
from .runner import Progress, RenderProcess, encode
from .spec import ShotSpec


def _print(p: Progress):
    eta = f" ETA {int(p.eta // 60)}m{int(p.eta % 60):02d}s" if p.eta else ""
    sys.stdout.write(f"\r[{p.stage}] {p.done}/{p.total} {p.message}{eta}      ")
    sys.stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rsm")
    ap.add_argument("command", choices=["render", "still", "job", "regrade", "previews"])
    ap.add_argument("file", nargs="?", default="")
    ap.add_argument("--moves", default=None, help="previews: comma-separated moves (default: all missing)")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--dest", default=None, help="previews: folder to store them in")
    ap.add_argument("--blender", default=None)
    ap.add_argument("--at", type=float, default=0.5)
    ap.add_argument("--out", default=None, help="folder for the job (default: the spec's output folder)")
    a = ap.parse_args(argv)

    blender = a.blender or find_blender()[0]
    if a.command == "previews":
        from . import previews
        if not blender:
            print("Blender 4.5+ not found. Pass --blender PATH.")
            return 2
        moves = a.moves.split(",") if a.moves else previews.missing_moves()
        kw = {k: v for k, v in dict(seconds=a.seconds, fps=a.fps, samples=a.samples).items() if v is not None}
        done = previews.build(blender, moves, Path(a.dest) if a.dest else None,
                              on_progress=lambda m, i, n, p: _print(p), **kw)
        print("\nBuilt previews:", ", ".join(done) or "none")
        return 0 if len(done) == len(moves) else 1
    if a.command == "regrade":
        job = Path(a.file)
    else:
        spec = ShotSpec.load(a.file)
        job = build_job(spec, a.out, preview=a.command == "still", progress=lambda m: print(m))
        print("Job:", job)
        if a.command == "job":
            return 0
    if not blender:
        print("Blender 4.5+ not found. Pass --blender PATH.")
        return 2
    extra = []
    if a.command == "still":
        extra = ["--still", str(a.at), "--still-out", str(job.parent / "work" / "preview")]
    if a.command == "regrade":
        extra = ["--regrade"]
    proc = RenderProcess(blender, job, _print, extra).start()
    code = proc.wait()
    print()
    if code != 0:
        print("Render failed:", proc.progress.message)
        print("\n".join(proc.progress.log[-40:]))
        return code
    if a.command in ("render", "regrade"):
        out = encode(job, on_line=None)
        print("Video:", out)
    else:
        print("Preview:", proc.progress.last_frame_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
