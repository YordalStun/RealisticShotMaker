"""Instant-film chemistry: turns a clean photo into a developed, aged instant print.

Everything works in sRGB-encoded floats (0..1) like the print itself.
"""
from __future__ import annotations

import numpy as np

from .imaging import blur, coords, fbm, lerp, luminance, saturate, smoothstep, value_noise

# Per-film response: toe lift, contrast, shadow tint, highlight tint, saturation, softness (mm)
FILM_RESPONSE = {
    "600": dict(lift=0.035, contrast=1.08, shadow=(0.96, 1.0, 1.06), high=(1.03, 1.0, 0.95), sat=0.92,
                soft_mm=0.035),
    "sx70": dict(lift=0.06, contrast=0.9, shadow=(1.02, 0.97, 1.03), high=(1.05, 1.0, 0.9), sat=1.0,
                 soft_mm=0.05),
    "spectra": dict(lift=0.04, contrast=1.04, shadow=(0.97, 1.0, 1.05), high=(1.03, 1.0, 0.95), sat=0.95,
                    soft_mm=0.035),
    "go": dict(lift=0.04, contrast=1.05, shadow=(0.97, 1.0, 1.04), high=(1.02, 1.0, 0.96), sat=0.95,
               soft_mm=0.04),
    "instax": dict(lift=0.02, contrast=1.12, shadow=(0.97, 0.99, 1.07), high=(1.0, 1.0, 0.99), sat=1.08,
                   soft_mm=0.03),
}

FADE_TINT = {
    "warm": np.array([0.96, 0.84, 0.66], np.float32),
    "magenta": np.array([0.93, 0.76, 0.84], np.float32),
    "cyan": np.array([0.70, 0.87, 0.90], np.float32),
    "green": np.array([0.80, 0.88, 0.70], np.float32),
    "none": np.array([0.86, 0.86, 0.86], np.float32),
}

DYE_SHIFT = {
    "warm": np.array([1.05, 0.97, 0.80], np.float32),
    "magenta": np.array([1.07, 0.84, 1.0], np.float32),
    "cyan": np.array([0.80, 1.0, 1.05], np.float32),
    "green": np.array([0.88, 1.03, 0.84], np.float32),
    "none": np.array([1.0, 1.0, 1.0], np.float32),
}


def _tone(x: np.ndarray, lift: float, contrast: float) -> np.ndarray:
    """Filmic S-curve with lifted blacks and soft shoulder."""
    x = np.clip(x, 0, 1)
    c = 0.5 + (x - 0.5) * contrast
    s = c * c * (3 - 2 * np.clip(c, 0, 1))
    y = lerp(c, s, 0.55)
    return lift + (1 - lift - 0.02) * np.clip(y, 0, 1)


def develop(photo: np.ndarray, film: str, chemistry: str, px_per_mm: float, *, age_years: float, fade: float,
            color_cast: str, sun_damage: float, chemical_edge: float, seed: int,
            r: np.random.Generator) -> np.ndarray:
    key = "instax" if chemistry == "instax" else film
    resp = FILM_RESPONSE.get(key, FILM_RESPONSE["600"])
    h, w = photo.shape[:2]
    img = photo.astype(np.float32).copy()

    # optical softness of the instant camera lens + film
    img = blur(img, resp["soft_mm"] * px_per_mm)

    # tone + split tint
    img = _tone(img, resp["lift"], resp["contrast"])
    l = luminance(img)[..., None]
    tint = lerp(np.array(resp["shadow"], np.float32), np.array(resp["high"], np.float32), l)
    img = saturate(img * tint, resp["sat"])

    # halation: bright areas bleed a warm glow into the emulsion
    bright = np.clip(luminance(img) - 0.72, 0, 1)[..., None]
    img += blur(bright, 0.6 * px_per_mm) * np.array([0.35, 0.18, 0.08], np.float32)

    # lens vignette of a cheap plastic lens
    x, y = coords(w, h)
    nx, ny = (x / w - 0.5) * 2, (y / h - 0.5) * 2
    rr = nx * nx + ny * ny
    img *= (1 - 0.16 * rr ** 1.3)[..., None]

    # uneven development: faint roller streaks (vertical) and density mottling
    streak = value_noise(w, 1, max(2.0, w / 60), r)[0]
    mott = fbm(w, h, w / 5, r, 4)
    img *= (1 + (streak[None, :] - 0.5) * 0.035 + (mott - 0.5) * 0.04)[..., None]

    # ageing
    a = float(np.clip(age_years / 50.0, 0, 1))
    f = float(np.clip(fade * 0.8 + a * 0.3, 0, 1))
    cast = color_cast if color_cast in FADE_TINT else "none"
    dye = lerp(np.ones(3, np.float32), DYE_SHIFT[cast], np.clip(a * 0.7 + fade * 0.5, 0, 1))
    img = img * dye
    img = saturate(img, 1 - f * 0.45)
    mean = float(img.mean())
    img = lerp(img, np.full(3, mean, np.float32), f * 0.35)
    img = img * (1 - f * 0.28) + FADE_TINT[cast] * (f * 0.28)
    # fading is never perfectly even
    patch = fbm(w, h, w / 2.5, r, 4)
    img = lerp(img, img * 0.9 + FADE_TINT[cast] * 0.1, (patch * f * 0.6)[..., None])

    # sun damage: one side bleached towards cyan-white
    if sun_damage > 0:
        ang = r.random() * 2 * np.pi
        g = (np.cos(ang) * nx + np.sin(ang) * ny) * 0.5 + 0.5
        g = smoothstep(0.15, 1.0, g + (fbm(w, h, w / 3, r, 4) - 0.5) * 0.4)
        bleach = (g * sun_damage)[..., None]
        washed = saturate(img, 0.35) * 0.6 + np.array([0.62, 0.78, 0.82], np.float32) * 0.45
        img = lerp(img, washed, bleach * 0.85)

    # developer reagent artefacts along the image edge
    if chemical_edge > 0:
        d_edge = np.minimum.reduce([x, y, w - x, h - y]) / max(w, h)
        n = fbm(w, h, w / 25, r, 5)
        reach = 0.004 + 0.03 * chemical_edge
        # the pod spreads from the bottom of the print, so the bottom edge is worst
        reach_map = reach * (0.6 + 1.2 * (y / h) ** 3)
        m = smoothstep(reach_map * (0.4 + 0.9 * n), 0.0, d_edge)
        reagent = lerp(np.array([0.93, 0.80, 0.55], np.float32), np.array([0.98, 0.95, 0.88], np.float32),
                       fbm(w, h, w / 40, r, 3)[..., None])
        img = lerp(img, reagent, (m * 0.85)[..., None])
        # tiny undeveloped bubbles
        bub = (r.random((h, w)) > 0.99985 - 0.0002 * chemical_edge).astype(np.float32)
        bub = np.clip(blur(bub, 0.08 * px_per_mm) * 30, 0, 1) * smoothstep(0.12, 0.0, d_edge)
        img = lerp(img, np.full(3, 0.95, np.float32), bub[..., None] * 0.7)

    # emulsion grain
    grain_sigma = 0.012 + 0.02 * a
    gr = r.normal(0, 1, (h, w)).astype(np.float32)
    gr = blur(gr, max(0.4, 0.008 * px_per_mm))
    img += (gr * grain_sigma)[..., None]
    return np.clip(img, 0, 1)
