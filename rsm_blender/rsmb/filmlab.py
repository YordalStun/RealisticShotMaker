"""Film lab: turns linear HDR renders into finished, graded frames.

Pure numpy so it can run inside Blender or in the app (for regrading
without re-rendering). Every effect models something real cameras and film
stocks do. Input: float32 (H, W, 3) scene-linear. Output: float32 display
values 0..1 (sRGB encoded).
"""
from __future__ import annotations

import math
import struct
import zlib

import numpy as np

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _box(a, r, axis):
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float32)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def _resize_nn(a, h, w):
    """Bilinear resize via numpy (works for 2D/3D)."""
    H, W = a.shape[:2]
    ys = (np.arange(h) + 0.5) * H / h - 0.5
    xs = (np.arange(w) + 0.5) * W / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, W - 1)
    y1 = np.clip(y0 + 1, 0, H - 1)
    x1 = np.clip(x0 + 1, 0, W - 1)
    fy = np.clip(ys - y0, 0, 1).astype(np.float32)
    fx = np.clip(xs - x0, 0, 1).astype(np.float32)
    if a.ndim == 3:
        fy = fy[:, None, None]
        fx = fx[None, :, None]
    else:
        fy = fy[:, None]
        fx = fx[None, :]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return (top * (1 - fy) + bot * fy).astype(np.float32)


def blur(a, sigma):
    """Gaussian-ish blur. Large sigmas run on a downsampled copy (fast on 8K frames)."""
    if sigma < 0.4:
        return a
    H, W = a.shape[:2]
    if sigma > 6:
        f = sigma / 3.0
        h, w = max(2, int(H / f)), max(2, int(W / f))
        small = _resize_nn(a, h, w)
        small = blur(small, 3.0)
        return _resize_nn(small, H, W)
    r = max(1, int(round(math.sqrt(sigma * sigma + 0.25) - 0.5)))
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box(_box(out, r, 0), r, 1)
    return out


def blur_h(a, sigma):
    """Horizontal-only blur (anamorphic streaks)."""
    H, W = a.shape[:2]
    f = max(1.0, sigma / 6.0)
    w = max(4, int(W / f))
    small = _resize_nn(a, H, w)
    r = max(1, int(6))
    for _ in range(3):
        small = _box(small, r, 1)
    return _resize_nn(small, H, W)


def luminance(c):
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


class Noise1D:
    def __init__(self, seed):
        r = np.random.default_rng(seed)
        self.g = r.uniform(-1, 1, 1024)

    def __call__(self, t):
        i = math.floor(t)
        f = t - i
        g0, g1 = self.g[i % 1024], self.g[(i + 1) % 1024]
        u = f * f * f * (f * (f * 6 - 15) + 10)
        return 2.0 * ((1 - u) * g0 * f + u * g1 * (f - 1))


# ---------------------------------------------------------------------------
# AgX tone mapping (Troy Sobotka's AgX, minimal fit)
# ---------------------------------------------------------------------------

_AGX = np.array([[0.842479062253094, 0.0423282422610123, 0.0423756549057051],
                 [0.0784335999999992, 0.878468636469772, 0.0784336],
                 [0.0792237451477643, 0.0791661274605434, 0.879142973793104]], np.float32)
_AGX_INV = np.array([[1.19687900512017, -0.0528968517574562, -0.0529716355144438],
                     [-0.0980208811401368, 1.15190312990417, -0.0980434501171241],
                     [-0.0990297440797205, -0.0989611768448433, 1.15107367264116]], np.float32)
_MIN_EV, _MAX_EV = -12.47393, 4.026069


def agx(lin: np.ndarray, punch: float = 1.0) -> np.ndarray:
    v = lin.reshape(-1, 3) @ _AGX
    v = np.clip(np.log2(np.maximum(v, 1e-10)), _MIN_EV, _MAX_EV)
    v = (v - _MIN_EV) / (_MAX_EV - _MIN_EV)
    x2 = v * v
    x4 = x2 * x2
    v = 15.5 * x4 * x2 - 40.14 * x4 * v + 31.96 * x4 - 6.868 * x2 * v + 0.4298 * x2 + 0.1191 * v - 0.00232
    if punch != 1.0:
        l = (v @ np.array([0.2126, 0.7152, 0.0722], np.float32))[:, None]
        v = l + (v - l) * punch
    v = v @ _AGX_INV
    return np.clip(v, 0, 1).reshape(lin.shape)


# ---------------------------------------------------------------------------
# Grades (display space)
# ---------------------------------------------------------------------------

GRADES = {
    "natural": dict(slope=(1, 1, 1), offset=(0, 0, 0), power=(1, 1, 1), sat=1.0, shadow=(0, 0, 0),
                    high=(0, 0, 0), contrast=1.0, punch=1.05),
    "warm_nostalgia": dict(slope=(1.05, 1.0, 0.9), offset=(0.012, 0.006, -0.004), power=(0.98, 1.0, 1.04),
                           sat=0.88, shadow=(0.01, 0.0, -0.012), high=(0.02, 0.008, -0.025), contrast=0.95,
                           punch=1.05),
    "golden_memory": dict(slope=(1.1, 1.0, 0.82), offset=(0.02, 0.01, -0.006), power=(0.96, 1.0, 1.08), sat=0.95,
                          shadow=(0.015, 0.004, -0.01), high=(0.035, 0.015, -0.035), contrast=0.97, punch=1.1),
    "faded_film": dict(slope=(1.0, 1.0, 0.97), offset=(0.05, 0.05, 0.045), power=(1.05, 1.02, 1.0), sat=0.72,
                       shadow=(-0.01, 0.012, 0.016), high=(0.02, 0.01, -0.01), contrast=0.85, punch=1.0),
    "cool_morning": dict(slope=(0.95, 1.0, 1.06), offset=(0.0, 0.004, 0.012), power=(1.02, 1.0, 0.97), sat=0.9,
                         shadow=(-0.01, 0.0, 0.015), high=(0.01, 0.01, 0.0), contrast=1.0, punch=1.0),
    "bleach_bypass": dict(slope=(1.0, 1.0, 1.0), offset=(0, 0, 0), power=(1.1, 1.1, 1.1), sat=0.45,
                          shadow=(0, 0, 0.005), high=(0, 0, 0), contrast=1.25, punch=1.0),
    "black_white": dict(slope=(1, 1, 1), offset=(0.01, 0.01, 0.01), power=(1, 1, 1), sat=0.0,
                        shadow=(0, 0, 0), high=(0.012, 0.006, -0.006), contrast=1.1, punch=1.0, bw=True),
}


def grade(img: np.ndarray, name: str) -> np.ndarray:
    g = GRADES.get(name, GRADES["natural"])
    v = img
    if g.get("bw"):
        # panchromatic film with a light yellow filter
        l = v[..., 0] * 0.36 + v[..., 1] * 0.54 + v[..., 2] * 0.1
        v = np.repeat(l[..., None], 3, axis=-1)
    v = np.clip(v * np.array(g["slope"], np.float32) + np.array(g["offset"], np.float32), 0, None)
    v = np.power(v, np.array(g["power"], np.float32))
    if g["contrast"] != 1.0:
        v = 0.5 + (v - 0.5) * g["contrast"]
    l = luminance(v)[..., None]
    v = l + (v - l) * g["sat"]
    sh = np.clip(1 - l * 2.2, 0, 1)
    hi = np.clip((l - 0.55) * 2.2, 0, 1)
    v = v + sh * np.array(g["shadow"], np.float32) + hi * np.array(g["high"], np.float32)
    return np.clip(v, 0, 1)


# ---------------------------------------------------------------------------
# Lens dirt texture (generated once per job)
# ---------------------------------------------------------------------------

def lens_dirt(h, w, seed=11):
    r = np.random.default_rng(seed)
    small_h, small_w = max(8, h // 8), max(8, w // 8)
    base = np.zeros((small_h, small_w), np.float32)
    yy, xx = np.mgrid[0:small_h, 0:small_w].astype(np.float32)
    for _ in range(140):
        cx, cy = r.uniform(0, small_w), r.uniform(0, small_h)
        rad = r.uniform(1.5, 9) * small_w / 480
        a = r.uniform(0.2, 1.0)
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        ring = np.exp(-((d - rad) / (rad * 0.25 + 0.5)) ** 2) * 0.6 + np.exp(-(d / rad) ** 2) * 0.5
        base += ring * a
    for _ in range(8):  # greasy smears
        cx, cy = r.uniform(0, small_w), r.uniform(0, small_h)
        sx, sy = r.uniform(10, 50) * small_w / 480, r.uniform(3, 12) * small_w / 480
        ang = r.uniform(0, math.pi)
        u = (xx - cx) * math.cos(ang) + (yy - cy) * math.sin(ang)
        v = -(xx - cx) * math.sin(ang) + (yy - cy) * math.cos(ang)
        base += np.exp(-(u / sx) ** 2 - (v / sy) ** 2) * r.uniform(0.3, 0.8)
    base = blur(base, 1.2)
    base /= max(1e-6, base.max())
    return _resize_nn(base, h, w)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

class FilmLab:
    def __init__(self, params: dict, height: int, width: int, seed: int = 1):
        self.p = params
        self.h, self.w = height, width
        self.seed = seed
        self.weave = (Noise1D(seed + 1), Noise1D(seed + 2), Noise1D(seed + 3))
        self.flick = Noise1D(seed + 4)
        self.dirt = lens_dirt(height, width, seed + 5) if params.get("lens_dirt", 0) > 0.001 else None
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        nx = (xx / width - 0.5) * 2
        ny = (yy / height - 0.5) * 2 * (height / width) * 1.6
        self.r2 = nx * nx + ny * ny
        self.auto_gain = params.get("auto_gain")  # fixed per shot once measured, so it never pumps

    def meter(self, lin: np.ndarray) -> float:
        """Centre-weighted exposure meter: place the subject area around the requested key value."""
        H, W = lin.shape[:2]
        y0, y1, x0, x1 = int(H * 0.25), int(H * 0.75), int(W * 0.3), int(W * 0.7)
        centre = luminance(lin[y0:y1, x0:x1])
        whole = luminance(lin[::4, ::4])
        logavg_c = float(np.exp(np.mean(np.log(np.maximum(centre, 1e-5)))))
        logavg_w = float(np.exp(np.mean(np.log(np.maximum(whole, 1e-5)))))
        key = logavg_c * 0.7 + logavg_w * 0.3
        target = float(self.p.get("key", 0.16))
        return float(np.clip(target / max(key, 1e-6), 1 / 64, 256))

    # ---- per-frame helpers ----------------------------------------------
    def _shift(self, img, dx, dy):
        ix, iy = int(math.floor(dx)), int(math.floor(dy))
        fx, fy = dx - ix, dy - iy
        a = np.roll(np.roll(img, iy, 0), ix, 1)
        b = np.roll(a, 1, 1)
        c = np.roll(a, 1, 0)
        d = np.roll(b, 1, 0)
        return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy

    def process(self, lin: np.ndarray, frame_index: int, fps: float = 24.0) -> np.ndarray:
        p = self.p
        H, W = lin.shape[:2]
        t = frame_index / max(1.0, fps)
        scale = H / 2160.0
        if p.get("auto_exposure", True) and self.auto_gain is None:
            self.auto_gain = self.meter(lin)
        gain = self.auto_gain if (p.get("auto_exposure", True) and self.auto_gain) else 1.0
        img = lin.astype(np.float32) * (gain * 2.0 ** p.get("exposure", 0.0))

        # flicker: film camera shutter/lamp variation
        fl = p.get("flicker", 0.0)
        if fl > 0:
            img *= 1.0 + fl * (0.025 * self.flick(t * 5.0) + 0.01 * math.sin(t * 2 * math.pi * 1.7))

        # gate weave: film moving in the gate
        gw = p.get("gate_weave", 0.0)
        if gw > 0:
            dx = gw * 1.6 * scale * self.weave[0].__call__(t * 1.3)
            dy = gw * 2.4 * scale * self.weave[1].__call__(t * 1.1) + gw * 0.6 * scale * self.weave[2](t * 7.0)
            img = self._shift(img, dx, dy)

        lum = luminance(img)
        # halation: light scattering back from the film base, red-orange around highlights
        hal = p.get("halation", 0.0)
        if hal > 0:
            bright = np.clip(lum - 1.2, 0, 40)[..., None]
            img = img + blur(bright, 9 * scale) * np.array([0.9, 0.22, 0.05], np.float32) * (0.35 * hal) \
                + blur(bright, 3 * scale) * np.array([0.6, 0.12, 0.02], np.float32) * (0.25 * hal)

        # veiling glare and bloom (diffusion filter / lens flare)
        bl = p.get("bloom", 0.0) + p.get("flare", 0.0) * 0.5
        bright_all = np.clip(img - 0.9, 0, 60)
        if bl > 0:
            glow = blur(bright_all, 18 * scale) * 0.55 + blur(bright_all, 60 * scale) * 0.45
            img = img + glow * (0.18 * bl)
            # veiling glare lifts the blacks a touch
            img = img + float(np.mean(img)) * 0.012 * bl

        # anamorphic streaks
        st = p.get("streak", 0.0)
        if st > 0:
            hot = np.clip(img - 2.0, 0, 80)
            streak = blur_h(hot, 260 * scale)
            img = img + streak * np.array([0.35, 0.55, 1.0], np.float32) * (0.5 * st)

        # lens dirt lights up where bright light hits the front element
        if self.dirt is not None:
            light = blur(bright_all, 80 * scale).mean(axis=-1, keepdims=True)
            img = img + self.dirt[..., None] * light * (0.6 * p.get("lens_dirt", 0.0))

        # tone map + grade
        out = agx(img, GRADES.get(p.get("grade", "natural"), {}).get("punch", 1.0))
        out = grade(out, p.get("grade", "natural"))

        # extra vignette
        vg = p.get("vignette", 0.0)
        if vg > 0:
            out = out * (1 - vg * 0.35 * np.clip(self.r2, 0, 2.5) ** 1.1)[..., None]

        # grain / sensor noise
        gr = p.get("grain", 0.0)
        if gr > 0:
            rng = np.random.default_rng(self.seed * 100003 + frame_index)
            l = luminance(out)
            if p.get("digital_noise", False):
                n_l = rng.standard_normal((H, W), dtype=np.float32)
                n_c = rng.standard_normal((H, W, 3), dtype=np.float32)
                n_l = blur(n_l, 0.5 * scale)
                n_c = blur(n_c, 1.2 * scale)
                amp = gr * 0.03 * (0.4 + 1.2 * (1 - l) ** 2)
                out = out + (n_l * amp)[..., None] + n_c * (amp * 0.5)[..., None]
            else:
                # film grain: clumped silver/dye grains, strongest in the mid-tones
                g1 = blur(rng.standard_normal((H, W), dtype=np.float32), 0.7 * scale + 0.3)
                g2 = blur(rng.standard_normal((H, W), dtype=np.float32), 1.8 * scale + 0.4)
                g = g1 * 0.7 + g2 * 0.6
                ch = blur(rng.standard_normal((H, W, 3), dtype=np.float32), 1.0 * scale + 0.3) * 0.25
                amp = gr * 0.055 * (0.25 + 4.0 * l * (1 - l))
                out = out + (g * amp)[..., None] + ch * amp[..., None]

        # letterbox
        lb = p.get("letterbox", "none")
        if lb in ("1.85", "2.39"):
            ratio = float(lb)
            bar = int(round((H - W / ratio) / 2))
            if bar > 0:
                out[:bar] = 0
                out[H - bar:] = 0
        return np.clip(out, 0, 1)


# ---------------------------------------------------------------------------
# 16-bit PNG writer (no colour management surprises)
# ---------------------------------------------------------------------------

def write_png16(path: str, img: np.ndarray, level: int = 1):
    h, w = img.shape[:2]
    data = (np.clip(img, 0, 1) * 65535.0 + 0.5).astype(">u2")
    raw = np.empty((h, 1 + w * 6), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = data.reshape(h, w * 3).view(np.uint8)
    comp = zlib.compress(raw.tobytes(), level)

    def chunk(tag, payload):
        c = struct.pack(">I", len(payload)) + tag + payload
        return c + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", comp))
        fh.write(chunk(b"IEND", b""))


def write_png8(path: str, img: np.ndarray):
    h, w = img.shape[:2]
    data = (np.clip(img, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    raw = np.empty((h, 1 + w * 3), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = data.reshape(h, w * 3)
    comp = zlib.compress(raw.tobytes(), 6)

    def chunk(tag, payload):
        c = struct.pack(">I", len(payload)) + tag + payload
        return c + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", comp))
        fh.write(chunk(b"IEND", b""))
