"""Built-in sample photos and loading of the user's own photo.

The built-in scenes are painted procedurally so the program ships without any
third-party imagery. They are meant to read as soft snapshots once the instant
film look is applied; users are expected to load their own pictures.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .imaging import Canvas, blur, fbm, hex_to_rgb, lerp, rng, smoothstep, coords, value_noise


def load_user_photo(path: str | Path, w: int, h: int, zoom: float = 1.0, ox: float = 0.0,
                    oy: float = 0.0) -> np.ndarray:
    """Load, orient and crop a photo to exactly w×h (cover fit). Returns sRGB float RGB."""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGB")
    iw, ih = im.size
    scale = max(w / iw, h / ih) * max(1.0, zoom)
    cw, ch = w / scale, h / scale  # crop size in source pixels
    cx = iw / 2 + ox * (iw - cw) / 2
    cy = ih / 2 + oy * (ih - ch) / 2
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    im = im.resize((w, h), Image.LANCZOS, box=box)
    return np.asarray(im, dtype=np.float32) / 255.0


def _grad(h: int, w: int, stops: list[tuple[float, str]], axis: int = 0) -> np.ndarray:
    t = np.linspace(0, 1, h if axis == 0 else w, dtype=np.float32)
    cols = np.zeros((len(t), 3), np.float32)
    pos = [s[0] for s in stops]
    rgb = np.stack([hex_to_rgb(s[1]) for s in stops])
    for c in range(3):
        cols[:, c] = np.interp(t, pos, rgb[:, c])
    if axis == 0:
        return np.broadcast_to(cols[:, None, :], (h, w, 3)).copy()
    return np.broadcast_to(cols[None, :, :], (h, w, 3)).copy()


def _paint(base: np.ndarray, mask: np.ndarray, color) -> np.ndarray:
    col = color if isinstance(color, np.ndarray) else hex_to_rgb(color)
    m = mask[..., None]
    return base * (1 - m) + col * m


def _figure(cv: Canvas, x, feet, height, r_body=0.13):
    """Rough standing person silhouette drawn into a canvas (head, torso, legs, arms)."""
    hh = height
    head = hh * 0.075
    cv.ellipse(x, feet - hh + head, head * 0.92, head)
    cv.polygon([(x - hh * r_body, feet - hh * 0.82), (x + hh * r_body, feet - hh * 0.82),
                (x + hh * r_body * 0.85, feet - hh * 0.47), (x - hh * r_body * 0.85, feet - hh * 0.47)])
    cv.line([(x - hh * 0.05, feet - hh * 0.5), (x - hh * 0.06, feet)], hh * 0.075)
    cv.line([(x + hh * 0.05, feet - hh * 0.5), (x + hh * 0.06, feet)], hh * 0.075)
    cv.line([(x - hh * r_body, feet - hh * 0.8), (x - hh * 0.2, feet - hh * 0.5)], hh * 0.05)
    cv.line([(x + hh * r_body, feet - hh * 0.8), (x + hh * 0.19, feet - hh * 0.52)], hh * 0.05)


def _person_layers(w, h, x, feet, height, top, bottom, skin, hair, seed):
    """Returns list of (mask, colour) for a person so clothing and skin get their own colours."""
    def cv():
        return Canvas(w, h, 2)
    hh = height
    skin_cv, top_cv, bot_cv, hair_cv = cv(), cv(), cv(), cv()
    _figure(skin_cv, x, feet, hh)
    top_cv.polygon([(x - hh * 0.135, feet - hh * 0.83), (x + hh * 0.135, feet - hh * 0.83),
                    (x + hh * 0.115, feet - hh * 0.5), (x - hh * 0.115, feet - hh * 0.5)])
    bot_cv.polygon([(x - hh * 0.12, feet - hh * 0.52), (x + hh * 0.12, feet - hh * 0.52),
                    (x + hh * 0.12, feet - hh * 0.36), (x - hh * 0.12, feet - hh * 0.36)])
    head = hh * 0.075
    hair_cv.ellipse(x, feet - hh + head * 0.75, head * 1.0, head * 0.8)
    return [(skin_cv.array(), skin), (top_cv.array(), top), (bot_cv.array(), bottom), (hair_cv.array(), hair)]


def beach(w: int, h: int, seed: int) -> np.ndarray:
    r = rng(seed)
    img = _grad(h, w, [(0, "#7aaecd"), (0.32, "#a9c9da"), (0.5, "#efe0c8"), (0.51, "#4b7f91"),
                       (0.6, "#6c9ea6"), (0.63, "#d9e2d8"), (0.66, "#d7c29c"), (1.0, "#c3a173")])
    x, y = coords(w, h)
    # clouds
    cl = fbm(w, h, w / 3, r, 6, stretch=(3.0, 1.0))
    cmask = smoothstep(0.55, 0.85, cl) * smoothstep(0.5, 0.15, y / h)
    img = _paint(img, cmask * 0.75, "#f6f2ea")
    # sun haze
    d = np.sqrt((x - w * 0.78) ** 2 + (y - h * 0.3) ** 2) / w
    img += (np.exp(-d * 5.0) * 0.35)[..., None] * hex_to_rgb("#fff1d6")
    # waves: stretched noise in sea band
    sea = (y > h * 0.5) & (y < h * 0.64)
    wv = fbm(w, h, w / 10, r, 5, stretch=(8.0, 1.0))
    img += (sea * (wv - 0.5) * 0.12)[..., None]
    foam = smoothstep(0.012, 0.0, np.abs(y / h - (0.628 + 0.006 * np.sin(x / w * 25)))) * 0.7
    img = _paint(img, foam, "#f4f3ee")
    # wet sand sheen and sand texture
    wet = smoothstep(0.66, 0.63, y / h) * (y > h * 0.63)
    img = _paint(img, wet * 0.45, "#a99a82")
    sand = fbm(w, h, max(2, w / 200), r, 3)
    img += ((y > h * 0.63) * (sand - 0.5) * 0.06)[..., None]
    # towel and bucket
    tw = Canvas(w, h, 2)
    tw.polygon([(w * 0.06, h * 0.84), (w * 0.3, h * 0.82), (w * 0.31, h * 0.9), (w * 0.07, h * 0.92)])
    tmask = tw.array()
    stripes = (np.sin(x / w * 70) > 0.2).astype(np.float32)
    img = _paint(img, tmask, "#e7e1d3")
    img = _paint(img, tmask * stripes, "#b8443a")
    bk = Canvas(w, h, 2)
    bk.polygon([(w * 0.77, h * 0.855), (w * 0.81, h * 0.855), (w * 0.805, h * 0.895), (w * 0.775, h * 0.895)])
    img = _paint(img, bk.array(), "#d84c32")
    # family
    people = [(0.4, 0.885, 0.44, "#c25a3d", "#2c4a6c", "#c99677", "#3a2a1f"),
              (0.53, 0.89, 0.40, "#ece2c9", "#7b6b44", "#d8a888", "#7b5a36"),
              (0.645, 0.9, 0.25, "#e7b23c", "#3e6f8f", "#e0b493", "#a77c4b")]
    for i, (px, pf, ph, top, bot, skin, hair) in enumerate(people):
        for mask, col in _person_layers(w, h, w * px, h * pf, h * ph, top, bot, skin, hair, seed + i):
            img = _paint(img, blur(mask, w * 0.0015), col)
        shadow = Canvas(w, h, 2)
        shadow.ellipse(w * px + w * 0.03, h * pf, w * 0.05, h * 0.008)
        img *= 1 - blur(shadow.array(), w * 0.004)[..., None] * 0.3
    return np.clip(img, 0, 1)


def garden(w: int, h: int, seed: int) -> np.ndarray:
    r = rng(seed)
    x, y = coords(w, h)
    img = _grad(h, w, [(0, "#9cc3dc"), (0.35, "#d9e6ea"), (0.36, "#3f5a2e"), (0.58, "#4f7134"),
                       (0.6, "#6f9a45"), (1.0, "#4f7a32")])
    trees = fbm(w, h, w / 6, r, 6)
    line = 0.36 - (trees - 0.5) * 0.22
    canopy = smoothstep(line + 0.01, line - 0.01, y / h) * smoothstep(0.1, 0.3, y / h)
    leaf = fbm(w, h, w / 60, r, 4)
    tree_col = lerp(hex_to_rgb("#2f4a24"), hex_to_rgb("#6f9447"), leaf[..., None])
    img = img * (1 - canopy[..., None]) + tree_col * canopy[..., None]
    grass = fbm(w, h, w / 120, r, 4, stretch=(1.0, 4.0))
    img += ((y > h * 0.6) * (grass - 0.5) * 0.18)[..., None] * np.array([0.6, 1.0, 0.4], np.float32)
    # fence
    fence = ((np.sin(x / w * 90) > -0.6) & (y > h * 0.48) & (y < h * 0.62)).astype(np.float32)
    fence = blur(fence, 1.0)
    img = _paint(img, fence * 0.92, "#b49a74")
    # child and dog
    for mask, col in _person_layers(w, h, w * 0.42, h * 0.9, h * 0.34, "#d84b4b", "#2d4f7a", "#e0b493",
                                    "#d9b26b", seed):
        img = _paint(img, blur(mask, w * 0.0015), col)
    dog = Canvas(w, h, 2)
    dog.ellipse(w * 0.62, h * 0.86, w * 0.075, h * 0.035)
    dog.ellipse(w * 0.69, h * 0.82, w * 0.03, h * 0.03)
    for lx in (0.57, 0.6, 0.64, 0.67):
        dog.line([(w * lx, h * 0.87), (w * lx, h * 0.91)], w * 0.012)
    img = _paint(img, blur(dog.array(), 1.2), "#7a5232")
    sun = np.exp(-np.sqrt((x - w * 0.2) ** 2 + (y - h * 0.05) ** 2) / w * 3.0) * 0.25
    return np.clip(img + sun[..., None] * hex_to_rgb("#fff3d0"), 0, 1)


def sunset(w: int, h: int, seed: int) -> np.ndarray:
    r = rng(seed)
    x, y = coords(w, h)
    img = _grad(h, w, [(0, "#3e4d7a"), (0.3, "#b0688a"), (0.52, "#f19a52"), (0.66, "#fbd38a"),
                       (0.67, "#3a2c22"), (1.0, "#21170f")])
    d = np.sqrt((x - w * 0.36) ** 2 + (y - h * 0.62) ** 2) / w
    img += (smoothstep(0.065, 0.055, d) * 0.6 + np.exp(-d * 6) * 0.45)[..., None] * hex_to_rgb("#ffe6b0")
    cl = fbm(w, h, w / 3, r, 5, stretch=(5.0, 1.0))
    img = _paint(img, smoothstep(0.6, 0.85, cl) * smoothstep(0.55, 0.1, y / h) * 0.55, "#c46f6a")
    # tree silhouette
    tree = Canvas(w, h, 2)
    tree.line([(w * 0.7, h * 0.67), (w * 0.705, h * 0.42)], w * 0.018)
    crown = fbm(w, h, w / 14, r, 5)
    d2 = np.sqrt(((x - w * 0.7) / 1.2) ** 2 + (y - h * 0.38) ** 2) / w
    crown_mask = smoothstep(0.17, 0.13, d2 + (crown - 0.5) * 0.08)
    sil = np.maximum(tree.array(), crown_mask)
    grass = fbm(w, h, w / 40, r, 4)
    sil = np.maximum(sil, smoothstep(0.66 - (grass - 0.5) * 0.04, 0.68, y / h))
    return np.clip(_paint(img, sil, "#1c140e"), 0, 1)


def birthday(w: int, h: int, seed: int) -> np.ndarray:
    r = rng(seed)
    x, y = coords(w, h)
    img = _grad(h, w, [(0, "#2a1d16"), (0.6, "#3b2a1e"), (1, "#5a3f2a")])
    # bokeh fairy lights in background
    for _ in range(40):
        cx, cy, rad = r.random() * w, r.random() * h * 0.5, w * (0.015 + r.random() * 0.03)
        m = smoothstep(rad, rad * 0.8, np.sqrt((x - cx) ** 2 + (y - cy) ** 2))
        img += m[..., None] * hex_to_rgb("#f0a850") * (0.25 + r.random() * 0.35)
    # cake
    cake = Canvas(w, h, 2)
    cake.polygon([(w * 0.25, h * 0.62), (w * 0.75, h * 0.62), (w * 0.75, h * 0.86), (w * 0.25, h * 0.86)])
    cake.ellipse(w * 0.5, h * 0.62, w * 0.25, h * 0.05)
    cmask = cake.array()
    img = _paint(img, cmask, "#f3e6d6")
    icing = Canvas(w, h, 2)
    icing.ellipse(w * 0.5, h * 0.62, w * 0.25, h * 0.05)
    img = _paint(img, icing.array(), "#f8c4cf")
    plate = Canvas(w, h, 2)
    plate.ellipse(w * 0.5, h * 0.87, w * 0.33, h * 0.04)
    img = _paint(img, plate.array() * (1 - cmask), "#d6d6d0")
    # candles + flames + glow
    glow = np.zeros((h, w), np.float32)
    for i in range(6):
        cx = w * (0.33 + i * 0.068)
        cy = h * (0.6 + 0.012 * math.sin(i * 1.7))
        c = Canvas(w, h, 2)
        c.line([(cx, cy), (cx, cy - h * 0.09)], w * 0.012)
        img = _paint(img, c.array(), ["#7fb6e0", "#f2d36b", "#e88aa6"][i % 3])
        f = Canvas(w, h, 2)
        f.ellipse(cx, cy - h * 0.115, w * 0.007, h * 0.018)
        fm = f.array()
        img = _paint(img, fm, "#fff4c8")
        glow += np.exp(-np.sqrt((x - cx) ** 2 + (y - (cy - h * 0.11)) ** 2) / (w * 0.06))
    img += (glow * 0.18)[..., None] * hex_to_rgb("#ffb560")
    return np.clip(img, 0, 1)


def snow(w: int, h: int, seed: int) -> np.ndarray:
    r = rng(seed)
    x, y = coords(w, h)
    img = _grad(h, w, [(0, "#c9ced3"), (0.55, "#e2e3e2"), (0.56, "#d8dbde"), (1, "#f2f3f4")])
    houses = Canvas(w, h, 2)
    roofs = Canvas(w, h, 2)
    wins = Canvas(w, h, 2)
    xs = 0.0
    while xs < 1.0:
        hw = 0.12 + r.random() * 0.12
        top = 0.33 + r.random() * 0.1
        houses.polygon([(w * xs, h * 0.6), (w * (xs + hw), h * 0.6), (w * (xs + hw), h * top), (w * xs, h * top)])
        roofs.polygon([(w * (xs - 0.01), h * top), (w * (xs + hw / 2), h * (top - 0.08)),
                       (w * (xs + hw + 0.01), h * top)])
        for k in range(2):
            wx = xs + hw * (0.25 + 0.4 * k)
            wins.polygon([(w * wx, h * (top + 0.07)), (w * (wx + 0.03), h * (top + 0.07)),
                          (w * (wx + 0.03), h * (top + 0.12)), (w * wx, h * (top + 0.12))])
        xs += hw + 0.01
    img = _paint(img, houses.array(), "#6f5a4c")
    img = _paint(img, roofs.array(), "#eef0f2")
    img = _paint(img, wins.array(), "#f0c070")
    flakes = (r.random((h, w)) > 0.9975).astype(np.float32)
    img = _paint(img, np.clip(blur(flakes, w * 0.0018) * 6, 0, 1), "#ffffff")
    ground = fbm(w, h, w / 20, r, 3)
    img -= ((y > h * 0.6) * (ground - 0.5) * 0.06)[..., None]
    return np.clip(img, 0, 1)


def lake(w: int, h: int, seed: int) -> np.ndarray:
    r = rng(seed)
    x, y = coords(w, h)
    img = _grad(h, w, [(0, "#6f9ccc"), (0.42, "#dbe6ee")])
    for i, (base, amp, col) in enumerate([(0.42, 0.12, "#7c8ea6"), (0.48, 0.08, "#5a6d5a")]):
        n = fbm(w, 1, w / 4, r, 6)[0]
        ridge = h * (base - n * amp)
        img = _paint(img, (y > ridge[None, :]).astype(np.float32) * (y < h * 0.55), col)
    water = (y >= h * 0.55)
    refl = img[np.clip((h * 1.1 - y).astype(int), 0, h - 1), x.astype(int)]
    ripple = fbm(w, h, w / 30, r, 3, stretch=(10.0, 1.0))
    img = np.where(water[..., None], refl * 0.75 + hex_to_rgb("#3f5f6f") * 0.2 + (ripple[..., None] - 0.5) * 0.08, img)
    return np.clip(img, 0, 1)


BUILTIN = {"beach": beach, "garden": garden, "sunset": sunset, "birthday": birthday, "snow": snow, "lake": lake}

# real photographs shipped with the app (CC0, see assets/photos/LICENSE.txt)
PHOTO_DIR = Path(__file__).resolve().parent.parent / "assets" / "photos"
REAL_PHOTOS = {"cat": "cat.png", "coffee": "coffee.png"}


def get_photo(source: str, w: int, h: int, zoom=1.0, ox=0.0, oy=0.0, seed: int = 1) -> np.ndarray:
    """Return the photo for a polaroid as sRGB float RGB at w×h."""
    if source.startswith("builtin:") and source.split(":", 1)[1] in REAL_PHOTOS:
        return load_user_photo(PHOTO_DIR / REAL_PHOTOS[source.split(":", 1)[1]], w, h, zoom, ox, oy)
    if source.startswith("builtin:"):
        key = source.split(":", 1)[1]
        fn = BUILTIN.get(key, beach)
        # paint at a moderate size; film softness hides the upscale
        pw = min(w, 1400)
        ph = max(1, int(round(pw * h / w)))
        img = fn(pw, ph, seed)
        if zoom > 1.0:
            cw, ch = int(pw / zoom), int(ph / zoom)
            x0 = int((pw - cw) / 2 * (1 + ox))
            y0 = int((ph - ch) / 2 * (1 + oy))
            img = img[y0:y0 + ch, x0:x0 + cw]
        if img.shape[:2] != (h, w):
            from .imaging import resize
            img = resize(img, w, h)
        return np.clip(img, 0, 1)
    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"Photo not found: {source}")
    return load_user_photo(p, w, h, zoom, ox, oy)
