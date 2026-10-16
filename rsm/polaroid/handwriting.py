"""Handwritten captions: glyph-by-glyph jitter, pen-specific ink behaviour."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .imaging import blur, fbm, smoothstep

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

HANDS = {
    # id: (display name, file)
    "caveat": ("Neat", "Caveat.ttf"),
    "indie": ("Rounded", "IndieFlower.ttf"),
    "shadows": ("Casual", "ShadowsIntoLight.ttf"),
    "gochi": ("Bold", "GochiHand.ttf"),
    "reenie": ("Scrawled", "ReenieBeanie.ttf"),
    "nothing": ("Thin and loopy", "NothingYouCouldDo.ttf"),
}


def _font(hand: str, size: int) -> ImageFont.FreeTypeFont:
    name = HANDS.get(hand, HANDS["caveat"])[1]
    path = FONT_DIR / name
    try:
        f = ImageFont.truetype(str(path), size)
        if hand == "caveat":
            try:
                f.set_variation_by_axes([550])
            except Exception:
                pass
        return f
    except OSError:
        return ImageFont.load_default(size)


def render_caption(text: str, hand: str, pen: str, box_w: int, box_h: int, px_per_mm: float,
                   r: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Render text inside a box. Returns (ink coverage 0..1, ink 'wetness' for roughness)."""
    if not text.strip() or pen == "none":
        z = np.zeros((box_h, box_w), np.float32)
        return z, z
    ss = 3
    W, H = box_w * ss, box_h * ss
    size = int(box_h * ss * 0.62)
    font = _font(hand, size)
    # shrink to fit width
    for _ in range(12):
        tw = font.getlength(text)
        if tw <= W * 0.86:
            break
        size = int(size * 0.9)
        font = _font(hand, size)
    tw = font.getlength(text)
    canvas = Image.new("L", (W, H), 0)
    x = (W - tw) / 2 + (r.random() - 0.5) * W * 0.06
    base = H * 0.5 + (r.random() - 0.5) * H * 0.08
    slope = (r.random() - 0.5) * 0.06  # people rarely write perfectly level
    for ch in text:
        adv = font.getlength(ch)
        if ch.strip():
            gw = int(adv + size)
            g = Image.new("L", (gw, int(size * 1.6)), 0)
            ImageDraw.Draw(g).text((size * 0.3, size * 0.15), ch, font=font, fill=255)
            g = g.rotate((r.random() - 0.5) * 7 + slope * -40, resample=Image.BICUBIC, expand=False)
            sc = 1 + (r.random() - 0.5) * 0.08
            if abs(sc - 1) > 0.01:
                g = g.resize((max(1, int(g.width * sc)), max(1, int(g.height * sc))), Image.BICUBIC)
            yy = base - size * 0.95 + (r.random() - 0.5) * size * 0.06 + (x - W / 2) * slope
            canvas.paste(255, (int(x - size * 0.3), int(yy)), g)
        x += adv * (1 + (r.random() - 0.5) * 0.05)
    ink = np.asarray(canvas.resize((box_w, box_h), Image.BOX), np.float32) / 255.0

    stroke_px = max(0.6, px_per_mm * 0.05)
    if pen == "marker":
        # felt tips bleed into the paper and pool at stroke ends
        wet = blur(ink, stroke_px * 0.6)
        ink = np.clip(ink * 0.85 + wet * 0.45, 0, 1)
        edge = np.clip(ink - blur(ink, stroke_px), 0, 1)
        ink = np.clip(ink + edge * 0.3, 0, 1) * (0.88 + 0.12 * fbm(box_w, box_h, px_per_mm * 2, r, 3))
        gloss = ink * 0.3
    elif pen == "ballpoint":
        # thinner line, with skipping where the ball dries
        thin = smoothstep(0.55, 0.85, blur(ink, stroke_px * 0.4))
        skip = smoothstep(0.15, 0.4, fbm(box_w, box_h, px_per_mm * 1.2, r, 4))
        ink = thin * (0.55 + 0.45 * skip)
        gloss = ink * 0.5
    else:  # pencil
        thin = smoothstep(0.45, 0.85, blur(ink, stroke_px * 0.3))
        tooth = smoothstep(0.25, 0.75, r.random((box_h, box_w)).astype(np.float32))
        ink = thin * (0.35 + 0.45 * tooth)
        gloss = thin * 0.8  # graphite is shiny
    return np.clip(ink, 0, 1), np.clip(gloss, 0, 1)
