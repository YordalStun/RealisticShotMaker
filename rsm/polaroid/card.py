"""Assembles a complete instant print: frame paper, developed photo, caption and
all wear and damage, as physically based texture maps.

Outputs (all the same size, card coordinates, origin top-left):
  color   sRGB albedo + alpha (card outline, wear chips, pin hole)
  rough   roughness 0..1
  height  height map 0..1 (16-bit), 0.5 = card surface
  back    back-side albedo + alpha (same UV layout as the front)
and a metadata dict used by Blender to bend, curl and fold the card mesh.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import catalog
from ..spec import PolaroidSpec
from . import film as filmmod
from .handwriting import render_caption
from .imaging import (Canvas, bezier, blur, coords, fbm, hex_to_rgb, lerp, rng, rounded_rect_sdf, save_gray,
                      save_rgb, smoothstep, value_noise)
from .photos import get_photo


@dataclass
class PolaroidMaps:
    color: np.ndarray
    alpha: np.ndarray
    rough: np.ndarray
    height: np.ndarray
    back: np.ndarray
    back_alpha: np.ndarray
    meta: dict

    def save(self, out_dir: str | Path, prefix: str = "polaroid") -> dict:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        files = {
            "color": out / f"{prefix}_color.png",
            "rough": out / f"{prefix}_rough.png",
            "height": out / f"{prefix}_height.png",
            "back": out / f"{prefix}_back.png",
        }
        save_rgb(files["color"], self.color, self.alpha)
        save_gray(files["rough"], self.rough)
        save_gray(files["height"], self.height, sixteen=True)
        save_rgb(files["back"], self.back, self.back_alpha)
        meta = dict(self.meta)
        meta["files"] = {k: str(v) for k, v in files.items()}
        (out / f"{prefix}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta


def _seg_dist(x, y, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy + 1e-9
    t = np.clip(((x - x0) * dx + (y - y0) * dy) / L2, 0, 1)
    px, py = x0 + t * dx, y0 + t * dy
    return np.sqrt((x - px) ** 2 + (y - py) ** 2)


def _signed_line(x, y, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) + 1e-9
    return ((x - x0) * dy - (y - y0) * dx) / L


def generate(p: PolaroidSpec, px_per_mm: float = 12.0) -> PolaroidMaps:
    ft = catalog.FILM_TYPES.get(p.film, catalog.FILM_TYPES["600"])
    ppm = float(px_per_mm)
    cw_mm, ch_mm = ft.card_mm
    W, H = int(round(cw_mm * ppm)), int(round(ch_mm * ppm))
    ix0, iy0 = ft.image_origin_mm[0] * ppm, ft.image_origin_mm[1] * ppm
    iw, ih = ft.image_mm[0] * ppm, ft.image_mm[1] * ppm
    r = rng(p.seed)
    x, y = coords(W, H)
    age = float(np.clip(p.age_years / 50.0, 0, 1))
    mm = ppm  # readability: N * mm = N millimetres in pixels

    # ------------------------------------------------------------------ masks
    img_sdf = rounded_rect_sdf(W, H, ix0, iy0, ix0 + iw, iy0 + ih, 0.25 * mm)
    img_mask = np.clip(0.5 - img_sdf, 0, 1)
    frame_mask = 1 - img_mask
    edge_dist = -rounded_rect_sdf(W, H, 0, 0, W, H, 0.8 * mm)  # distance inside the card, px
    edge_prox = smoothstep(6 * mm, 0, edge_dist)

    # ------------------------------------------------------------------ frame paper
    frame_hex = catalog.FRAME_COLORS.get(p.frame_color, catalog.FRAME_COLORS["classic"])[1]
    base = hex_to_rgb(frame_hex)
    dark_frame = float(base.mean()) < 0.35
    paper_noise = fbm(W, H, 0.7 * mm, r, 3) - 0.5
    fibres = fbm(W, H, 2.5 * mm, r, 4, stretch=(1.0, 5.0)) - 0.5
    color = np.broadcast_to(base, (H, W, 3)).astype(np.float32).copy()
    color *= (1 + paper_noise * 0.025 + fibres * 0.02)[..., None]
    blotch = fbm(W, H, 18 * mm, r, 4)
    ymask = np.clip(p.yellowing * (0.5 + 0.55 * edge_prox + 0.6 * (blotch - 0.5)), 0, 1)
    if dark_frame:
        color = lerp(color, color * 1.25 + np.array([0.05, 0.045, 0.035], np.float32), ymask[..., None] * 0.6)
    else:
        aged = color * np.array([0.99, 0.93, 0.74], np.float32)
        color = lerp(color, aged, ymask[..., None])

    # ------------------------------------------------------------------ photo
    pw, ph = int(math.ceil(iw)) + 2, int(math.ceil(ih)) + 2
    photo = get_photo(p.photo, pw, ph, p.photo_zoom, p.photo_offset_x, p.photo_offset_y, seed=p.seed)
    photo = filmmod.develop(photo, p.film, ft.chemistry, ppm, age_years=p.age_years, fade=p.fade,
                            color_cast=p.color_cast, sun_damage=p.sun_damage, chemical_edge=p.chemical_edge,
                            seed=p.seed, r=r)
    full_photo = np.zeros((H, W, 3), np.float32)
    px0, py0 = int(math.floor(ix0)) - 1, int(math.floor(iy0)) - 1
    full_photo[py0:py0 + ph, px0:px0 + pw] = photo[: H - py0, : W - px0]
    # the frame casts a soft inner shadow onto the recessed picture
    inner = blur(frame_mask, 0.18 * mm) * img_mask
    full_photo *= (1 - inner * 0.45)[..., None]
    color = lerp(color, full_photo, img_mask[..., None])

    # ------------------------------------------------------------------ caption
    ink_gloss = np.zeros((H, W), np.float32)
    if p.caption.strip() and p.caption_pen != "none":
        bx0 = int(5 * mm)
        by0 = int(iy0 + ih + 2.0 * mm)
        bw = W - 2 * bx0
        bh = int(H - by0 - 2.5 * mm)
        if bh > 4 * mm:
            bh = int(min(bh, 13 * mm))
            ink, gl = render_caption(p.caption, p.caption_hand, p.caption_pen, bw, bh, ppm, r)
            ink_col = hex_to_rgb(p.caption_color)
            if p.caption_pen == "pencil":
                ink_col = np.array([0.33, 0.33, 0.35], np.float32)
            ink_col = lerp(ink_col, ink_col * 0.7 + 0.3 * np.array([0.6, 0.55, 0.5], np.float32), age * 0.6)
            region = color[by0:by0 + bh, bx0:bx0 + bw]
            density = 0.95 if p.caption_pen == "marker" else 0.85
            color[by0:by0 + bh, bx0:bx0 + bw] = lerp(region, region * ink_col / max(1e-3, float(base.max())),
                                                     (ink * density)[..., None]) if not dark_frame else \
                lerp(region, np.array([0.92, 0.9, 0.85], np.float32), (ink * density)[..., None])
            ink_gloss[by0:by0 + bh, bx0:bx0 + bw] = gl

    # ------------------------------------------------------------------ roughness + height bases
    gloss = float(np.clip(p.gloss, 0, 1))
    rough = np.where(img_mask > 0.5, lerp(0.34, 0.05, gloss), 0.58).astype(np.float32)
    rough = lerp(0.58, lerp(0.34, 0.05, gloss), img_mask)
    rough += (fbm(W, H, 6 * mm, r, 4) - 0.5) * 0.05
    rough -= ink_gloss * 0.25
    height = 0.5 + paper_noise * 0.02 * frame_mask
    height -= blur(img_mask, 0.12 * mm) * 0.06           # picture sits behind the frame
    bottom = smoothstep(iy0 + ih + 1 * mm, iy0 + ih + 6 * mm, y) * smoothstep(H - 1 * mm, H - 5 * mm, y)
    height += bottom * smoothstep(0, 10 * mm, np.minimum(x, W - x)) * 0.05  # reagent trap bulge

    # ------------------------------------------------------------------ handling grime
    grime_amt = 0.25 * age + 0.5 * p.corner_wear + 0.2 * p.fingerprints
    if grime_amt > 0.01:
        dirt = fbm(W, H, 4 * mm, r, 5)
        zones = np.clip(edge_prox * 0.8 + smoothstep(H * 0.75, H, y) * 0.5, 0, 1)
        g = np.clip(zones * smoothstep(0.35, 0.85, dirt) * grime_amt, 0, 1)
        dirt_col = np.array([0.55, 0.5, 0.42], np.float32)
        color = lerp(color, color * dirt_col, g[..., None] * 0.55)
        rough += g * 0.1

    # ------------------------------------------------------------------ scratches
    if p.scratches > 0.01:
        deep_cv, micro_cv = Canvas(W, H, 2), Canvas(W, H, 2)
        n_deep = int(round(p.scratches * 40))
        n_micro = int(round(p.scratches * 500))
        family_angle = r.random() * math.pi
        for i in range(n_deep + n_micro):
            deep = i < n_deep
            length = (r.uniform(4, 40) if deep else r.uniform(0.8, 8)) * mm
            ang = family_angle + r.normal(0, 0.35) if r.random() < 0.6 else r.random() * math.pi
            sx, sy = r.random() * W, r.random() * H
            ex, ey = sx + math.cos(ang) * length, sy + math.sin(ang) * length
            bend = r.normal(0, 0.12) * length
            cx = (sx + ex) / 2 - math.sin(ang) * bend
            cy = (sy + ey) / 2 + math.cos(ang) * bend
            pts = bezier((sx, sy), (cx, cy), (ex, ey), 20)
            width = (r.uniform(0.05, 0.14) if deep else r.uniform(0.015, 0.04)) * mm
            val = int(r.uniform(140, 255))
            (deep_cv if deep else micro_cv).line(pts, max(0.5, width), val)
        deep = deep_cv.array()
        micro = micro_cv.array()
        # a scratch through the emulsion shows lighter; on the frame it's subtle
        color = lerp(color, np.array([0.9, 0.88, 0.84], np.float32),
                     (deep * (0.45 * img_mask + 0.12 * frame_mask))[..., None])
        color = lerp(color, color * 1.06 + 0.02, (micro * 0.4 * img_mask)[..., None])
        rough += deep * 0.45 + micro * 0.28
        height -= blur(deep, 0.4) * 0.12 + micro * 0.02

    # ------------------------------------------------------------------ fingerprints
    n_prints = int(round(p.fingerprints * 6))
    oil = np.zeros((H, W), np.float32)
    for _ in range(n_prints):
        ax, ay = r.uniform(6, 8) * mm, r.uniform(8, 10.5) * mm
        # prints gather near the edges where the photo is held
        side = r.integers(0, 4)
        cx = [r.uniform(0, W), r.uniform(0, W), r.uniform(-2, 8) * mm, W - r.uniform(-2, 8) * mm][side]
        cy = [H - r.uniform(-2, 12) * mm, r.uniform(-2, 10) * mm, r.uniform(0, H), r.uniform(0, H)][side]
        rot = r.random() * math.pi
        x0, x1 = int(max(0, cx - ay * 1.3)), int(min(W, cx + ay * 1.3))
        y0, y1 = int(max(0, cy - ay * 1.3)), int(min(H, cy + ay * 1.3))
        if x1 <= x0 or y1 <= y0:
            continue
        lx, ly = x[y0:y1, x0:x1] - cx, y[y0:y1, x0:x1] - cy
        u = lx * math.cos(rot) + ly * math.sin(rot)
        v = -lx * math.sin(rot) + ly * math.cos(rot)
        re = np.sqrt((u / ax) ** 2 + (v / ay) ** 2)
        lw_, lh_ = x1 - x0, y1 - y0
        warp = fbm(lw_, lh_, 3 * mm, r, 3) - 0.5
        period = 0.47 * mm
        ridges = 0.5 + 0.5 * np.sin(2 * math.pi * (re * ax / period) + warp * 6.0 + np.arctan2(v, u) * 0.6)
        ridges = smoothstep(0.35, 0.75, ridges)
        cover = smoothstep(1.0, 0.55, re) * smoothstep(0.25, 0.6, fbm(lw_, lh_, 5 * mm, r, 3))
        oil[y0:y1, x0:x1] = np.maximum(oil[y0:y1, x0:x1], ridges * cover * r.uniform(0.5, 1.0))
    if n_prints:
        rough += oil * (0.3 * img_mask + 0.12 * frame_mask)
        color = lerp(color, color * 1.03 + 0.01, (oil * 0.25)[..., None])

    # ------------------------------------------------------------------ stains
    n_stains = int(math.ceil(p.stains * 3)) if p.stains > 0.02 else 0
    for i in range(n_stains):
        cx, cy = r.uniform(0.1, 0.9) * W, r.uniform(0.1, 0.9) * H
        R = r.uniform(7, 22) * mm
        dx, dy = x - cx, y - cy
        rad = np.sqrt(dx * dx + dy * dy)
        theta = np.arctan2(dy, dx)
        wob = value_noise(64, 1, 6, r)[0]
        idx = ((theta + math.pi) / (2 * math.pi) * 63).astype(int)
        Rt = R * (1 + (wob[idx] - 0.5) * 0.35 + (fbm(W, H, 3 * mm, r, 3) - 0.5) * 0.08)
        if i % 2 == 0:  # coffee ring
            width_var = 0.35 + 0.5 * fbm(W, H, 2 * mm, r, 3)
            ring = np.exp(-((rad - Rt) / (width_var * mm)) ** 2) * (0.55 + 0.45 * fbm(W, H, 4 * mm, r, 3))
            inside = smoothstep(Rt, Rt - 3 * mm, rad) * 0.18
            s = p.stains
            stain_col = np.array([0.80, 0.63, 0.42], np.float32)
            color = lerp(color, color * stain_col, ((ring * 0.6 + inside) * s)[..., None])
            rough += ring * 0.15 * s
        else:  # dried water mark: tide line, washed emulsion, cockled surface
            m = smoothstep(Rt, Rt - 1.5 * mm, rad)
            tide = np.exp(-((rad - Rt) / ((0.25 + 0.45 * fbm(W, H, 2 * mm, r, 3)) * mm)) ** 2) * (0.4 + 0.6 * fbm(W, H, 5 * mm, r, 3))
            s = p.stains
            washed = lerp(color, color * 0.75 + np.array([0.18, 0.22, 0.2], np.float32), 0.6)
            color = lerp(color, washed, (m * img_mask * 0.55 * s)[..., None])
            color = lerp(color, color * np.array([0.82, 0.76, 0.66], np.float32), (tide * 0.45 * s)[..., None])
            cockle = (fbm(W, H, 1.5 * mm, r, 3) - 0.5) * m
            height += cockle * 0.08 * s
            rough += m * 0.18 * s * img_mask

    # ------------------------------------------------------------------ creases
    creases_meta = []
    n_creases = int(math.ceil(p.creases * 3)) if p.creases > 0.05 else 0
    for i in range(n_creases):
        if r.random() < 0.55:  # corner crease
            corner = r.integers(0, 4)
            cxp, cyp = [(0, 0), (W, 0), (0, H), (W, H)][corner]
            a1 = r.uniform(10, 35) * mm
            a2 = r.uniform(10, 35) * mm
            sx_, sy_ = (cxp + (a1 if cxp == 0 else -a1), cyp)
            ex_, ey_ = (cxp, cyp + (a2 if cyp == 0 else -a2))
        else:  # fold across the card
            if r.random() < 0.5:
                sx_, sy_, ex_, ey_ = 0, r.uniform(0.2, 0.8) * H, W, r.uniform(0.2, 0.8) * H
            else:
                sx_, sy_, ex_, ey_ = r.uniform(0.2, 0.8) * W, 0, r.uniform(0.2, 0.8) * W, H
        sign = 1 if r.random() < 0.5 else -1
        depth = p.creases * r.uniform(0.6, 1.0)
        d = _seg_dist(x, y, sx_, sy_, ex_, ey_)
        breaks = smoothstep(0.3, 0.55, fbm(W, H, 1.2 * mm, r, 3))
        core = np.exp(-(d / (0.07 * mm)) ** 2) * breaks
        crack_n = fbm(W, H, 0.25 * mm, r, 2)
        cracks = smoothstep(0.78, 0.9, crack_n) * np.exp(-(d / (0.6 * mm)) ** 2)
        white = np.clip(core + cracks * 0.8, 0, 1) * depth
        color = lerp(color, np.array([0.93, 0.92, 0.89], np.float32), (white * (0.85 * img_mask + 0.35 * frame_mask))[..., None])
        height += sign * (np.exp(-(d / (0.25 * mm)) ** 2) * 0.16 + np.exp(-(d / (2.2 * mm)) ** 2) * 0.06) * depth
        rough += white * 0.35
        creases_meta.append(dict(p0=[sx_ / ppm, sy_ / ppm], p1=[ex_ / ppm, ey_ / ppm], sign=sign,
                                 depth=float(depth)))

    # ------------------------------------------------------------------ dog-ear fold line
    dog = None
    if p.dog_ear > 0.03:
        corner = ["tl", "tr", "bl", "br"][int(r.integers(0, 4))]
        size = (6 + 14 * p.dog_ear) * mm
        cxp = 0 if corner[1] == "l" else W
        cyp = 0 if corner[0] == "t" else H
        sx_, sy_ = cxp + (size if cxp == 0 else -size), cyp
        ex_, ey_ = cxp, cyp + (size if cyp == 0 else -size)
        d = _seg_dist(x, y, sx_, sy_, ex_, ey_)
        fold = np.exp(-(d / (0.12 * mm)) ** 2)
        color = lerp(color, np.array([0.93, 0.92, 0.89], np.float32), (fold * 0.7)[..., None])
        height += np.exp(-(d / (0.35 * mm)) ** 2) * 0.12
        rough += fold * 0.3
        dog = dict(corner=corner, size_mm=size / ppm, angle_deg=float(25 + 120 * p.dog_ear))

    # ------------------------------------------------------------------ dust and lint
    if p.dust > 0.01:
        speck_cv, lint_cv = Canvas(W, H, 2), Canvas(W, H, 2)
        area = (cw_mm * ch_mm) / (88 * 107)
        for _ in range(int(p.dust * 380 * area)):
            rr_ = r.uniform(0.02, 0.09) * mm
            speck_cv.ellipse(r.random() * W, r.random() * H, rr_ * r.uniform(0.6, 1.4), rr_, int(r.uniform(90, 255)))
        for _ in range(int(p.dust * 28 * area)):
            sx_, sy_ = r.random() * W, r.random() * H
            ln = r.uniform(0.6, 3.5) * mm
            ang = r.random() * 2 * math.pi
            c1 = (sx_ + math.cos(ang + r.normal(0, 1)) * ln * 0.6, sy_ + math.sin(ang + r.normal(0, 1)) * ln * 0.6)
            e1 = (sx_ + math.cos(ang) * ln, sy_ + math.sin(ang) * ln)
            lint_cv.line(bezier((sx_, sy_), c1, e1, 16), max(0.5, 0.025 * mm), int(r.uniform(120, 230)))
        specks, lint = speck_cv.array(), lint_cv.array()
        color = lerp(color, color * 0.45, (specks * 0.8)[..., None])
        color = lerp(color, np.array([0.85, 0.84, 0.82], np.float32), (lint * 0.75)[..., None])
        height += blur(specks + lint, 0.5) * 0.08
        rough += (specks + lint) * 0.4

    # ------------------------------------------------------------------ tape
    tape_rect = None
    if p.tape:
        tw_, th_ = r.uniform(24, 32) * mm, r.uniform(12, 16) * mm
        tcx = W / 2 + r.uniform(-12, 12) * mm
        tang = math.radians(r.uniform(-9, 9))
        lx, ly = x - tcx, y - 0
        u = lx * math.cos(tang) + ly * math.sin(tang)
        v = -lx * math.sin(tang) + ly * math.cos(tang)
        jag = (value_noise(W, H, 0.4 * mm, r) - 0.5) * 1.2 * mm
        tmask = smoothstep(tw_ / 2 + jag, tw_ / 2 - 0.2 * mm + jag, np.abs(u)) * smoothstep(th_ / 2, th_ / 2 - 0.15 * mm, np.abs(v))
        tape_col = lerp(np.array([0.99, 0.97, 0.9], np.float32), np.array([0.95, 0.82, 0.5], np.float32), age)
        color = lerp(color, color * tape_col, (tmask * 0.85)[..., None])
        edge = np.clip(tmask - blur(tmask, 0.3 * mm), 0, 1)
        color = lerp(color, color * 0.7, (edge * 0.8)[..., None])
        rough = lerp(rough, np.full_like(rough, 0.12), tmask)
        height += tmask * 0.05 + edge * 0.06
        tape_rect = dict(center_mm=[tcx / ppm, 0.0], size_mm=[tw_ / ppm, th_ / ppm], angle_deg=math.degrees(tang))

    # ------------------------------------------------------------------ card outline: corner wear, chips, pin hole
    wear = float(np.clip(p.corner_wear, 0, 1))
    radius = (0.9 + 2.6 * wear) * mm
    sdf = rounded_rect_sdf(W, H, 0, 0, W, H, radius)
    frayed = sdf + (fbm(W, H, 1.6 * mm, r, 3) - 0.5) * (0.08 + 0.35 * wear) * mm
    alpha = np.clip(0.5 - frayed, 0, 1)
    edge_band = smoothstep(0.7 * mm * (0.3 + wear), 0, -frayed) * alpha
    edge_col = np.array([0.93, 0.91, 0.87], np.float32) if dark_frame else np.array([0.80, 0.77, 0.70], np.float32)
    color = lerp(color, edge_col, (edge_band * (0.35 + 0.5 * wear))[..., None])
    rough += edge_band * 0.25
    pin = None
    if p.pin_hole:
        pcx, pcy = W / 2 + r.uniform(-6, 6) * mm, r.uniform(3, 4.5) * mm
        pr = 0.45 * mm
        d = np.sqrt((x - pcx) ** 2 + (y - pcy) ** 2)
        hole = smoothstep(pr * 0.9, pr * 1.1, d)
        alpha *= hole
        rim = np.exp(-((d - pr * 1.3) / (0.25 * mm)) ** 2)
        color = lerp(color, color * 0.75, (rim * 0.6)[..., None])
        height += rim * 0.1
        pin = [pcx / ppm, pcy / ppm]

    # ------------------------------------------------------------------ back side
    back_base = np.array([0.075, 0.073, 0.072], np.float32)
    back = np.broadcast_to(back_base, (H, W, 3)).astype(np.float32).copy()
    back *= (1 + (fbm(W, H, 1.5 * mm, r, 4) - 0.5) * 0.25)[..., None]
    scuff_cv = Canvas(W, H, 1)
    for _ in range(int(20 + 60 * (p.scratches + age))):
        sx_, sy_ = r.random() * W, r.random() * H
        ang = r.random() * math.pi
        ln = r.uniform(1, 12) * mm
        scuff_cv.line([(sx_, sy_), (sx_ + math.cos(ang) * ln, sy_ + math.sin(ang) * ln)], max(1, 0.05 * mm),
                      int(r.uniform(40, 160)))
    back = lerp(back, np.array([0.25, 0.24, 0.23], np.float32), (scuff_cv.array() * 0.6)[..., None])
    back = lerp(back, back * 1.6 + 0.04, (edge_prox * 0.3 * (age + wear) / 2)[..., None])
    back_alpha = alpha.copy()  # same UVs as the front: the solidified card shares them

    meta = dict(
        film=p.film,
        card_mm=[cw_mm, ch_mm],
        image_rect_mm=[ft.image_origin_mm[0], ft.image_origin_mm[1], ft.image_mm[0], ft.image_mm[1]],
        px_per_mm=ppm,
        size_px=[W, H],
        creases=creases_meta,
        dog_ear=dog,
        curl=float(p.curl),
        tape=tape_rect,
        pin_hole=pin,
        gloss=gloss,
        thickness_mm=1.0 if ft.chemistry == "integral" else 0.8,
    )
    return PolaroidMaps(np.clip(color, 0, 1), alpha, np.clip(rough, 0.02, 1), np.clip(height, 0, 1), back,
                        back_alpha, meta)


def preview_image(p: PolaroidSpec, height_px: int = 640):
    """Quick composited preview (PIL RGBA image) for the GUI."""
    from PIL import Image
    ft = catalog.FILM_TYPES.get(p.film, catalog.FILM_TYPES["600"])
    ppm = max(1.5, height_px / ft.card_mm[1])
    maps = generate(p, ppm)
    rgb = (np.clip(maps.color, 0, 1) * 255).astype(np.uint8)
    a = (np.clip(maps.alpha, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, a]), "RGBA")


def px_per_mm_for(output_height_px: int, frame_fill: float, card_h_mm: float, cap: float = 40.0) -> float:
    """Texture density so the print stays sharper than the output pixels at the chosen framing."""
    need = output_height_px * frame_fill / card_h_mm * 1.4
    return float(np.clip(need, 8.0, cap))
