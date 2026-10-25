"""Turns a ShotSpec into a render job: textures on disk + a fully resolved JSON
file the Blender side can execute without knowing about presets."""
from __future__ import annotations

import dataclasses
import json
import math
import random
import time
from pathlib import Path

import numpy as np

from . import __version__, catalog, shotlist
from .polaroid import generate, px_per_mm_for
from .polaroid.film import develop
from .polaroid.imaging import rng as np_rng, save_rgb
from .polaroid.photos import BUILTIN, get_photo
from .polaroid.card import layout_for
from .spec import PolaroidSpec, ShotSpec

NO_FRAMES = ("investigation_board", "photo_line", "photo_album")

BLENDER_DIR = Path(__file__).resolve().parent.parent / "rsm_blender"


def resolve(spec: ShotSpec) -> dict:
    out = spec.output
    name, w, h = catalog.RESOLUTIONS.get(out.resolution, catalog.RESOLUTIONS["uhd4k"])
    q = catalog.QUALITY.get(out.quality, catalog.QUALITY["high"])
    fps = float(out.fps)
    n_frames = max(1, int(round(spec.camera.duration * fps)))
    samples = out.custom_samples if out.custom_samples > 0 else q.samples
    return dict(width=w, height=h, fps=fps, frame_start=1, frame_end=n_frames, samples=samples,
                noise_threshold=q.noise_threshold, max_bounces=q.max_bounces,
                volume_step_rate=max(0.25, q.volume_step * 20), volumetrics=True, quality=q.id,
                engine="eevee" if out.engine == "eevee" else "cycles")


def sensor_for(spec: ShotSpec) -> tuple[float, float]:
    body = catalog.BODIES.get(spec.camera.body, catalog.BODIES["film_35"])
    key = body.sensor if spec.camera.sensor == "auto" else spec.camera.sensor
    _, sw, sh = catalog.SENSORS.get(key, catalog.SENSORS["super35"])
    return sw, sh


def film_params(spec: ShotSpec) -> dict:
    body = catalog.BODIES.get(spec.camera.body, catalog.BODIES["film_35"])
    lens = catalog.LENSES.get(spec.camera.lens, catalog.LENSES["vintage_prime"])
    lk = spec.look

    def pick(v, default):
        return default if v is None or v < 0 else v
    character = max(0.0, lk.lens_character)
    # how bright the subject should sit: night stays dark and moody, daylight is brighter
    key = {"morning": 0.17, "midday": 0.18, "golden": 0.15, "evening": 0.1, "night": 0.065}.get(
        spec.scene.time_of_day, 0.15)
    mood = catalog.MOODS.get(spec.scene.mood)
    meter = {}
    vignette = lk.vignette
    if mood is not None and mood.dark:
        meter = dict(meter="highlights", key_hi=mood.key, low_key=mood.low_key)
        vignette = max(vignette, 0.55)
    return dict(
        key=key,
        **meter,
        exposure=lk.exposure,
        grade=lk.grade,
        grain=pick(lk.grain, body.grain),
        digital_noise=body.digital_noise,
        gate_weave=pick(lk.gate_weave, body.gate_weave),
        flicker=pick(lk.flicker, body.flicker),
        halation=pick(lk.halation, body.halation),
        bloom=lk.bloom,
        flare=lens.flare * character,
        streak=lens.streak * character,
        lens_dirt=lk.lens_dirt,
        vignette=vignette,
        letterbox=lk.letterbox,
    )


def _variant(base: PolaroidSpec, r: random.Random, photo: str | None = None) -> PolaroidSpec:
    p = dataclasses.replace(base)
    p.photo = photo or "builtin:" + r.choice(list(BUILTIN))
    p.caption = r.choice(["", "", "Mum & Dad", "1986", "Easter", "Grandma", "Me!", "Holiday", "Sunday"])
    p.caption_hand = r.choice(["caveat", "indie", "shadows", "reenie"])
    p.seed = r.randint(1, 10_000_000)
    p.age_years = max(0.0, base.age_years + r.uniform(-8, 8))
    p.scratches = min(1.0, max(0.0, base.scratches + r.uniform(-0.15, 0.2)))
    p.curl = min(1.0, max(0.0, base.curl + r.uniform(-0.1, 0.2)))
    p.dog_ear = 0.0 if r.random() < 0.7 else r.uniform(0.2, 0.6)
    p.creases = 0.0 if r.random() < 0.7 else r.uniform(0.1, 0.5)
    p.tape = False
    p.print_type = "instant"     # the other photos lying about are prints, whatever the hero is in
    p.fit_photo_aspect = False
    p.pin_hole = r.random() < 0.08
    p.film = base.film if r.random() < 0.7 else r.choice(["600", "sx70", "instax_mini", "spectra"])
    return p


def _frame_photo(path: Path, kind: str, seed: int, w: int = 900, h: int = 1200):
    r = np_rng(seed)
    photo = get_photo(f"builtin:{kind}", w, h, seed=seed)
    img = develop(photo, "600", "integral", 8.0, age_years=40, fade=0.5, color_cast="warm", sun_damage=0.0,
                  chemical_edge=0.0, seed=seed, r=r)
    # mount like a lab print: thin white border
    b = int(w * 0.04)
    out = np.ones((h + 2 * b, w + 2 * b, 3), np.float32) * np.array([0.93, 0.9, 0.84], np.float32)
    out[b:b + h, b:b + w] = img
    save_rgb(path, out)
    return str(path)


def build_job(spec: ShotSpec, work_root: str | Path | None = None, preview: bool = False,
              progress=lambda msg: None) -> Path:
    """Generate textures and write job.json. Returns the job file path."""
    out = spec.output
    from .paths import default_output_dir
    # absolute: Blender runs in its own working folder, so relative paths in the job would point nowhere
    root = Path(work_root or out.output_dir or default_output_dir()).expanduser().resolve()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    job_dir = root / f"{out.name or 'shot'}_{stamp}"
    work = job_dir / "work"
    for d in (work, job_dir / "exr", job_dir / "frames"):
        d.mkdir(parents=True, exist_ok=True)

    resolved = resolve(spec)
    framing_name, fill = catalog.FRAMINGS.get(spec.camera.framing, catalog.FRAMINGS["close"])
    film = catalog.FILM_TYPES.get(spec.polaroid.film, catalog.FILM_TYPES["600"])
    shots = shotlist.resolve(spec)
    tex_fill = max(fill, max(s["fill"] for s in shots))
    cap = 40.0
    if tex_fill > 1.0:
        # a close-up fills the screen with a small part of the print: it needs a lot more texture detail
        cap = 56.0
    if spec.scene.location in NO_FRAMES and spec.polaroid.print_type == "framed":
        # pegged on a line, stuck on the board, slipped into an album: those are prints, not framed photos
        spec = dataclasses.replace(spec, polaroid=dataclasses.replace(spec.polaroid, print_type="instant"))
    lay = layout_for(spec.polaroid)
    card_h = lay.frame["outer_mm"][1] if lay.frame else lay.card_mm[1]
    ppm = px_per_mm_for(resolved["height"], tex_fill, card_h, cap=24.0 if preview else cap)
    # keep a big framed print's texture to a sensible size (about 40 megapixels)
    ppm = min(ppm, math.sqrt(40e6 / (lay.card_mm[0] * lay.card_mm[1])))

    progress("Developing the instant print…")
    hero = generate(spec.polaroid, ppm).save(work, "hero")

    r = random.Random(spec.scene.seed * 7919 + spec.polaroid.seed)
    extras = []
    n_extra = 0
    if spec.scene.extra_photos:
        n_extra = 3
    if spec.scene.placement == "pile":
        n_extra += 5
    if spec.scene.location == "investigation_board":
        n_extra = 7  # the board is covered in other photos
    n_extra = {"photo_line": 11, "photo_spread": 12, "photo_album": 10}.get(spec.scene.location, n_extra)
    for i in range(n_extra):
        progress(f"Making other photos ({i + 1}/{n_extra})…")
        v = _variant(spec.polaroid, r)
        extras.append(generate(v, min(10.0, ppm * 0.5)).save(work, f"extra{i}"))

    progress("Printing framed photos…")
    frame_photos = [
        _frame_photo(work / "frame0.png", "garden", r.randint(1, 99999)),
        _frame_photo(work / "frame1.png", "beach", r.randint(1, 99999), 800, 1000),
    ]

    sw, sh = sensor_for(spec)
    job = dict(
        version=1,
        app_version=__version__,
        spec=spec.to_dict(),
        resolved=resolved,
        framing_fill=fill,
        sensor_mm=[sw, sh],
        lens=dataclasses.asdict(catalog.LENSES.get(spec.camera.lens, catalog.LENSES["vintage_prime"])),
        body=dataclasses.asdict(catalog.BODIES.get(spec.camera.body, catalog.BODIES["film_35"])),
        filmlab=film_params(spec),
        polaroid=hero,
        extra_prints=extras,
        frame_photos=frame_photos,
        location_options=catalog.location_options(spec.scene.location, spec.scene.options),
        shots=shots,
        paths=dict(root=str(job_dir), work=str(work), exr=str(job_dir / "exr"), frames=str(job_dir / "frames"),
                   fonts=str(Path(__file__).resolve().parent / "assets" / "fonts")),
        created=stamp,
    )
    path = job_dir / "job.json"
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    spec.save(job_dir / "shot.rsm.json")
    return path
