"""Rough render-time guesses, so the editor and the queue can say how long things will take."""
from __future__ import annotations

from . import catalog
from .spec import ShotSpec


def estimate(spec: ShotSpec) -> tuple[float, float, int]:
    """(seconds per frame, total seconds, frames) on an RTX 4080/5080 class card for these interior sets.
    Only a guide: real times depend on the set, the lighting and the card."""
    res = catalog.RESOLUTIONS.get(spec.output.resolution, catalog.RESOLUTIONS["uhd4k"])
    q = catalog.QUALITY.get(spec.output.quality, catalog.QUALITY["high"])
    frames = max(1, int(round(spec.camera.duration * spec.output.fps)))
    samples = spec.output.custom_samples or q.samples
    mpix = res[1] * res[2] / 1e6
    per_frame = mpix * samples / 1024 * 9.0 * (1.6 if spec.scene.light_shafts > 0.05 else 1.0)
    per_frame += 1.5  # scene update, denoise and film lab per frame
    return per_frame, per_frame * frames + 20.0, frames
