"""Small numpy/Pillow image toolkit: noise, blur, masks and drawing helpers.

Arrays are float32, shape (H, W) or (H, W, C), values usually 0..1.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed & 0xFFFFFFFF)


def resize(a: np.ndarray, w: int, h: int, resample=Image.BICUBIC) -> np.ndarray:
    """Resize a float array (2D or 3D)."""
    if a.ndim == 3:
        return np.stack([resize(a[..., c], w, h, resample) for c in range(a.shape[2])], axis=-1)
    im = Image.fromarray(np.ascontiguousarray(a, dtype=np.float32), mode="F")
    return np.asarray(im.resize((max(1, w), max(1, h)), resample), dtype=np.float32)


def value_noise(w: int, h: int, cell: float, r: np.random.Generator) -> np.ndarray:
    """Smooth random field with features about `cell` pixels across. Range ~0..1."""
    cell = max(1.0, cell)
    gw, gh = int(math.ceil(w / cell)) + 3, int(math.ceil(h / cell)) + 3
    grid = r.random((gh, gw), dtype=np.float32)
    big = resize(grid, int(gw * cell), int(gh * cell))
    ox, oy = int(cell), int(cell)
    out = big[oy:oy + h, ox:ox + w]
    if out.shape != (h, w):  # rounding guard
        out = resize(out, w, h)
    return out


def fbm(w: int, h: int, cell: float, r: np.random.Generator, octaves: int = 5, gain: float = 0.5,
        stretch: tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
    """Fractal noise normalised to 0..1. `stretch` elongates features along x / y."""
    total = np.zeros((h, w), np.float32)
    amp, norm = 1.0, 0.0
    c = cell
    for _ in range(octaves):
        if c < 1.0:
            break
        sx, sy = stretch
        n = value_noise(max(1, int(w / sx)), max(1, int(h / sy)), c, r)
        if (sx, sy) != (1.0, 1.0):
            n = resize(n, w, h)
        total += n * amp
        norm += amp
        amp *= gain
        c /= 2.0
    total /= max(norm, 1e-6)
    lo, hi = float(total.min()), float(total.max())
    return (total - lo) / max(hi - lo, 1e-6)


def _box(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Approximate gaussian blur (three box passes). Large blurs run on a smaller copy."""
    if sigma < 0.35:
        return a
    h, w = a.shape[:2]
    if sigma > 24:
        f = sigma / 12.0
        small = resize(a, max(2, int(w / f)), max(2, int(h / f)), Image.BILINEAR)
        small = blur(small, 12.0)
        return resize(small, w, h, Image.BILINEAR)
    r = max(1, int(round(math.sqrt(sigma * sigma + 0.25) - 0.5)))
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box(_box(out, r, 0), r, 1)
    return out


def smoothstep(e0, e1, x):
    d = e1 - e0
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    t = np.clip((x - e0) / d, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def coords(w: int, h: int):
    """Pixel-centre coordinate grids (x, y)."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x + 0.5, y + 0.5


def rounded_rect_sdf(w: int, h: int, x0, y0, x1, y1, radius) -> np.ndarray:
    """Signed distance in pixels to a rounded rectangle (negative inside)."""
    x, y = coords(w, h)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2 - radius, (y1 - y0) / 2 - radius
    qx = np.abs(x - cx) - hx
    qy = np.abs(y - cy) - hy
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    inside = np.minimum(np.maximum(qx, qy), 0)
    return outside + inside - radius


class Canvas:
    """Supersampled grayscale drawing surface for crisp anti-aliased strokes."""

    def __init__(self, w: int, h: int, ss: int = 2):
        self.w, self.h, self.ss = w, h, ss
        self.img = Image.new("L", (w * ss, h * ss), 0)
        self.draw = ImageDraw.Draw(self.img)

    def line(self, pts, width: float, value: int = 255):
        s = self.ss
        self.draw.line([(x * s, y * s) for x, y in pts], fill=value, width=max(1, int(round(width * s))),
                       joint="curve")

    def ellipse(self, cx, cy, rx, ry, value: int = 255):
        s = self.ss
        self.draw.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s], fill=value)

    def polygon(self, pts, value: int = 255):
        s = self.ss
        self.draw.polygon([(x * s, y * s) for x, y in pts], fill=value)

    def array(self) -> np.ndarray:
        im = self.img.resize((self.w, self.h), Image.BOX) if self.ss > 1 else self.img
        return np.asarray(im, dtype=np.float32) / 255.0


def bezier(p0, p1, p2, n: int = 24):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        pts.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return pts


def hex_to_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def srgb_to_linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055).astype(np.float32)


def luminance(c: np.ndarray) -> np.ndarray:
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def saturate(c: np.ndarray, amount: float) -> np.ndarray:
    l = luminance(c)[..., None]
    return l + (c - l) * amount


def to_u8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def to_u16(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0, 1) * 65535.0 + 0.5).astype(np.uint16)


def save_rgb(path, rgb: np.ndarray, alpha: np.ndarray | None = None):
    if alpha is not None:
        arr = np.concatenate([to_u8(rgb), to_u8(alpha)[..., None]], axis=-1)
        Image.fromarray(arr, "RGBA").save(path, compress_level=1)
    else:
        Image.fromarray(to_u8(rgb), "RGB").save(path, compress_level=1)


def save_gray(path, a: np.ndarray, sixteen: bool = False):
    if sixteen:
        Image.fromarray(to_u16(a)).save(path, compress_level=1)  # uint16 -> 16-bit greyscale PNG
    else:
        Image.fromarray(to_u8(a), "L").save(path, compress_level=1)
