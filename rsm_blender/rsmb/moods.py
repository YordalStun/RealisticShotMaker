"""Lighting moods: darker, edgier setups that work in any set.

Each mood is built from real lights placed around the photo, so the ray tracer does the work: hard shadows
from a single key, venetian-blind stripes, a torch beam searching through the haze, a bare bulb swinging on
its cord, TV flicker, neon, police lights, lightning.

`prepare()` runs before the set is lit (it can force night, turn practical lamps off, ask for haze);
`apply()` runs once the set and camera exist and adds the mood's own lights.
"""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import materials as M
from .util import link, mesh_object
from .world import kelvin_rgb

# id: settings used before the set is built
#   night     force a night sky (no daylight)
#   lamps     what happens to the set's own lights: keep | dim | off
#   haze      minimum haze so beams are visible
MOODS = {
    "natural": dict(night=False, lamps="keep", haze=0.0),
    "low_key": dict(night=True, lamps="dim", haze=0.15),
    "noir_blinds": dict(night=True, lamps="dim", haze=0.3),
    "bare_bulb": dict(night=True, lamps="off", haze=0.2),
    "torch": dict(night=True, lamps="off", haze=0.45),
    "candle": dict(night=True, lamps="off", haze=0.05),
    "tv_glow": dict(night=True, lamps="off", haze=0.15),
    "neon": dict(night=True, lamps="dim", haze=0.35),
    "police": dict(night=True, lamps="dim", haze=0.3),
    "lightning": dict(night=True, lamps="off", haze=0.25),
    "moonlight": dict(night=True, lamps="off", haze=0.3),
    "red_room": dict(night=True, lamps="off", haze=0.1),
}


def settings(mood: str) -> dict:
    return MOODS.get(mood, MOODS["natural"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class Rig:
    """Where things are: the photo, which way the camera looks, the room, the frame range."""

    def __init__(self, anchors, room_min, room_max, fps, f0, f1, seed, sun_window=None, camera=None):
        self.S = Vector(anchors.subject)
        v = Vector(anchors.view_dir)
        self.toward_cam = Vector((v.x, v.y, 0)).normalized() if v.xy.length > 1e-6 else Vector((0, -1, 0))
        self.right = self.toward_cam.cross(Vector((0, 0, 1))).normalized() * -1   # camera's right
        self.n = Vector(anchors.card_normal)
        self.room_min, self.room_max = Vector(room_min), Vector(room_max)
        self.fps, self.f0, self.f1 = fps, f0, f1
        self.rng = random.Random(seed * 31 + 7)
        self.sun_window = sun_window
        self.camera = camera
        self.col = bpy.data.collections.get("RSM_Set") or bpy.context.scene.collection

    def around(self, azimuth_deg: float, elevation_deg: float, dist: float) -> Vector:
        """A point `dist` from the photo: azimuth 0 = from the camera side, +90 = camera's right."""
        a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
        d = (self.toward_cam * math.cos(a) + self.right * math.sin(a)) * math.cos(e) + Vector((0, 0, math.sin(e)))
        return self.inside(self.S + d * dist)

    def inside(self, p: Vector, margin=0.12) -> Vector:
        return Vector(tuple(min(max(p[i], self.room_min[i] + margin), self.room_max[i] - margin) for i in range(3)))

    def window_point(self, out: float = 1.2) -> Vector | None:
        """Just outside the sunlit window, if the set has one."""
        w = self.sun_window
        if not w:
            return None
        c = Vector(w["centre"])
        # outward normal: from the room centre through the window plane
        mid = (self.room_min + self.room_max) / 2
        d = c - mid
        d.z = 0
        if abs(d.x) > abs(d.y):
            nrm = Vector((math.copysign(1, d.x), 0, 0))
        else:
            nrm = Vector((0, math.copysign(1, d.y), 0))
        return c + nrm * out

    def frames(self):
        return range(self.f0, self.f1 + 1)

    def t(self, f: int) -> float:
        return (f - self.f0) / self.fps


def _light(name, kind, energy, color, at: Vector, aim: Vector | None = None, size=0.1, size_y=None, spot=None,
           blend=0.2, col=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.shape = "RECTANGLE" if size_y else "SQUARE"
        ld.size = size
        if size_y:
            ld.size_y = size_y
    elif kind in ("POINT", "SPOT"):
        ld.shadow_soft_size = size
    elif kind == "SUN":
        ld.angle = size
    if kind == "SPOT":
        ld.spot_size = math.radians(spot or 30)
        ld.spot_blend = blend
    o = bpy.data.objects.new(name, ld)
    link(o, col)
    o.location = at
    if aim is not None:
        o.rotation_euler = (aim - at).to_track_quat("-Z", "Y").to_euler()
    return o


def _key_energy(o, f, energy, color=None):
    o.data.energy = energy
    o.data.keyframe_insert("energy", frame=f)
    if color is not None:
        o.data.color = color
        o.data.keyframe_insert("color", frame=f)


def _constant(o):
    from .camera_rig import _fcurves
    ad = o.data.animation_data
    if ad and ad.action:
        for fc in _fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def _hide_from_camera(o):
    for attr in ("visible_camera", "visible_glossy"):
        try:
            setattr(o, attr, False)
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# moods
# ---------------------------------------------------------------------------

def _low_key(r: Rig):
    """One hard, high side light. Everything it doesn't touch falls away to black."""
    key = _light("MoodKey", "SPOT", 70, kelvin_rgb(3400), r.around(62, 48, 1.7), r.S, size=0.015, spot=24,
                 blend=0.25, col=r.col)
    # the faintest cold kick from behind so edges separate from the dark
    _light("MoodKick", "AREA", 6, kelvin_rgb(7500), r.around(165, 30, 1.4), r.S, size=0.4, col=r.col)
    return [key]


def _blinds(r: Rig):
    """Hard light through venetian blinds: stripes across the photo and the table."""
    src = r.around(55, 34, 2.3)
    spot = _light("MoodBlindsKey", "SPOT", 140, kelvin_rgb(4200), src, r.S, size=0.004, spot=30, blend=0.05,
                  col=r.col)
    # real slats between the light and the photo: they cast the stripes, the camera never sees them
    to_s = (r.S - src).normalized()
    centre = src + to_s * 0.55
    up = Vector((0, 0, 1))
    side = to_s.cross(up).normalized()
    slat_up = side.cross(to_s).normalized()
    bm = bmesh.new()
    n_slats, pitch, depth, width = 22, 0.028, 0.02, 0.7
    for k in range(n_slats):
        off = (k - n_slats / 2) * pitch
        c = centre + slat_up * off
        rot = Matrix((side, to_s, slat_up)).transposed()
        tilt = Matrix.Rotation(math.radians(28), 3, side)
        verts = []
        for dx, dy, dz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1),
                           (-1, 1, 1)):
            local = Vector((dx * width / 2, dy * depth / 2, dz * 0.0008))
            verts.append(bm.verts.new(c + tilt @ (rot @ local)))
        for f in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            bm.faces.new([verts[i] for i in f])
    slats = mesh_object("MoodBlindSlats", bm, r.col, mat=M.metal("BlindSlat", "#cfcbc2", 0.5, 0.2, 0.0))
    _hide_from_camera(slats)
    # dim cold ambience so the shadow stripes aren't pure black
    _light("MoodBlindsFill", "AREA", 5, kelvin_rgb(8000), r.around(-70, 40, 2.0), r.S, size=1.2, col=r.col)
    return [spot]


def _bare_bulb(r: Rig):
    """A bare bulb on a flex above the photo, swinging slowly: the shadows sway with it."""
    ceiling = r.room_max.z - 0.02
    pivot = r.inside(r.S + r.toward_cam * 0.22 + r.right * 0.08, 0.2)
    pivot.z = ceiling
    drop = min(ceiling - r.S.z - 0.55, 1.6)
    root = bpy.data.objects.new("MoodBulbPivot", None)
    link(root, r.col)
    root.location = pivot
    bulb_mat = M.frosted_bulb("MoodBulbGlass", 2500.0, 60.0)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=0.03)
    for v in bm.verts:
        if v.co.z > 0:
            v.co.z *= 1.5
    bulb = mesh_object("MoodBulb", bm, r.col, smooth=True, mat=bulb_mat)
    bulb.location = (0, 0, -drop)
    bulb.parent = root
    from .util import cylinder
    holder = cylinder("MoodBulbHolder", 0.017, 0.045, (0, 0, -drop + 0.035), M.plastic("Bakelite", "#1a1614", 0.3),
                      r.col, 24)
    holder.parent = root
    cu = bpy.data.curves.new("MoodFlex", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(1)
    sp.points[0].co = (0, 0, 0, 1)
    sp.points[1].co = (0, 0, -drop + 0.08, 1)
    cu.bevel_depth = 0.0025
    flex = bpy.data.objects.new("MoodFlex", cu)
    link(flex, r.col)
    flex.data.materials.append(M.plastic("Flex", "#141210", 0.5))
    flex.parent = root
    light = _light("MoodBulbLight", "POINT", 45, kelvin_rgb(2500), Vector((0, 0, -drop)), size=0.03, col=r.col)
    light.parent = root
    # swing: a pendulum slowly losing energy, a little elliptical
    period = 2 * math.pi * math.sqrt(drop / 9.81)
    amp = math.radians(9)
    for f in r.frames():
        t = r.t(f)
        a = amp * math.exp(-t / 25.0)
        root.rotation_euler = (a * math.sin(2 * math.pi * t / period),
                               a * 0.35 * math.sin(2 * math.pi * t / period + 1.1), 0)
        root.keyframe_insert("rotation_euler", frame=f)
    return [light]


def _torch(r: Rig):
    """Someone beside the camera searching with a torch: the beam sweeps through the haze and finds the photo."""
    target = bpy.data.objects.new("MoodTorchTarget", None)
    link(target, r.col)
    at = r.S + r.toward_cam * 1.2 + r.right * 0.35 + Vector((0, 0, 0.25))
    spot = _light("MoodTorch", "SPOT", 38, kelvin_rgb(5200), at, size=0.012, spot=17, blend=0.55, col=r.col)
    if r.camera is not None:
        # held just beside the lens and a little below it, following the camera
        scene = bpy.context.scene
        keep = scene.frame_current
        for f in r.frames():
            scene.frame_set(f)
            m = r.camera.matrix_world
            spot.location = m @ Vector((0.28, -0.12, 0.05))
            spot.keyframe_insert("location", frame=f)
        scene.frame_set(keep)
    c = spot.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    search = [r.S + r.right * -0.55 + Vector((0, 0, 0.12)), r.S + r.right * -0.2 + r.toward_cam * -0.35,
              r.S + r.right * 0.4 + Vector((0, 0, -0.05)), r.S + r.right * 0.12, r.S]
    total = r.f1 - r.f0
    settle = r.f0 + int(total * 0.45)
    for f in r.frames():
        u = (f - r.f0) / max(1, settle - r.f0)
        if f < settle:
            seg = min(len(search) - 2, int(u * (len(search) - 1)))
            k = u * (len(search) - 1) - seg
            k = k * k * (3 - 2 * k)
            p = search[seg].lerp(search[seg + 1], k)
        else:
            p = r.S.copy()
        # hand shake: small, a bit faster than breathing
        t = r.t(f)
        p += r.right * (0.008 * math.sin(t * 7.1) + 0.004 * math.sin(t * 13.3)) + Vector((0, 0, 0.006 * math.sin(t * 5.3)))
        target.location = p
        target.keyframe_insert("location", frame=f)
    # cheap torch: the odd flicker as the contact wobbles
    for f in r.frames():
        e = 38.0 * (0.55 if r.rng.random() < 0.03 else 1.0)
        _key_energy(spot, f, e)
    _constant(spot)
    _light("MoodTorchSpill", "AREA", 2, kelvin_rgb(6500), r.around(0, 60, 2.0), r.S, size=1.5, col=r.col)
    return [spot]


def _candle(r: Rig):
    """Only a candle just out of shot: warm, low, alive."""
    at = r.around(48, 12, 0.32)
    at.z = max(at.z, r.S.z + 0.05)
    lt = _light("MoodCandle", "POINT", 4.5, kelvin_rgb(1850), at, size=0.012, col=r.col)
    rng = r.rng
    level = 1.0
    for f in r.frames():
        level += (1.0 - level) * 0.35 + rng.gauss(0, 0.07)
        if rng.random() < 0.02:
            level *= 0.7   # a draught
        _key_energy(lt, f, 4.5 * max(0.4, level))
        lt.location = at + Vector((rng.gauss(0, 0.002), rng.gauss(0, 0.002), rng.gauss(0, 0.002)))
        lt.keyframe_insert("location", frame=f)
    return [lt]


def _tv(r: Rig):
    """A television in a dark room: cold, shifting light that jumps with every cut on screen."""
    at = r.around(-58, 5, 1.6)
    lt = _light("MoodTV", "AREA", 30, kelvin_rgb(8500), at, r.S, size=0.55, size_y=0.33, col=r.col)
    rng = r.rng
    f = r.f0
    while f <= r.f1:
        shot_len = rng.randint(int(r.fps * 0.4), int(r.fps * 2.5))     # a 'cut' on the TV
        base = rng.uniform(0.35, 1.0)
        tint = rng.choice([kelvin_rgb(9000), kelvin_rgb(7000), (0.75, 0.85, 1.0), (0.9, 0.95, 1.0), (0.7, 1.0, 0.9)])
        for k in range(shot_len):
            if f > r.f1:
                break
            e = 30 * base * (1 + rng.gauss(0, 0.06))
            _key_energy(lt, f, e, tint)
            f += 1
    _constant(lt)
    return [lt]


def _neon(r: Rig):
    """A neon sign outside: magenta from one side, cyan rim from behind, the sign buzzing."""
    mag = _light("MoodNeonMagenta", "AREA", 70, (1.0, 0.12, 0.55), r.around(75, 22, 1.5), r.S, size=0.9, size_y=0.08,
                 col=r.col)
    cyan = _light("MoodNeonCyan", "AREA", 45, (0.1, 0.75, 1.0), r.around(-150, 35, 1.4), r.S, size=0.6, size_y=0.08,
                  col=r.col)
    rng = r.rng
    for f in r.frames():
        drop = rng.random() < 0.035
        _key_energy(mag, f, 70 * (0.15 if drop else 1.0 + rng.gauss(0, 0.02)))
    _constant(mag)
    return [mag, cyan]


def _police(r: Rig):
    """Red and blue lights flashing outside the window."""
    w = r.window_point(1.5)
    base = w if w is not None else r.around(-80, 15, 2.5)
    red = _light("MoodPoliceRed", "AREA", 0, (1.0, 0.04, 0.02), base + r.right * 0.4, r.S, size=0.5, col=r.col)
    blue = _light("MoodPoliceBlue", "AREA", 0, (0.05, 0.2, 1.0), base - r.right * 0.4, r.S, size=0.5, col=r.col)
    # light bar pattern: red double flash, blue double flash, ~1.6 cycles a second
    cycle = 0.62
    for f in r.frames():
        ph = (r.t(f) % cycle) / cycle
        on_r = ph < 0.1 or 0.16 < ph < 0.26
        on_b = 0.5 < ph < 0.6 or 0.66 < ph < 0.76
        _key_energy(red, f, 260 if on_r else 8)
        _key_energy(blue, f, 320 if on_b else 10)
    _constant(red)
    _constant(blue)
    _light("MoodPoliceAmbient", "AREA", 4, kelvin_rgb(7000), r.around(0, 50, 2.0), r.S, size=1.5, col=r.col)
    return [red, blue]


def _lightning(r: Rig):
    """A storm: almost dark, then the room flashes white for a moment, twice."""
    w = r.window_point(3.0)
    src = w + Vector((0, 0, 1.2)) if w is not None else r.around(-70, 45, 3.0)
    flash = _light("MoodLightning", "AREA", 0, kelvin_rgb(9500), src, r.S, size=2.5, col=r.col)
    _light("MoodStormAmbient", "AREA", 5, kelvin_rgb(9000), r.around(-40, 40, 2.0), r.S, size=1.5, col=r.col)
    n = r.f1 - r.f0 + 1
    starts = sorted({r.f0 + int(n * x) for x in (r.rng.uniform(0.2, 0.35), r.rng.uniform(0.6, 0.8))})
    pattern = [1.0, 0.25, 0.9, 0.5, 0.15, 0.05]     # strike, flicker, return stroke, fade
    for f in r.frames():
        e = 0.0
        for s in starts:
            k = f - s
            if 0 <= k < len(pattern):
                e = max(e, 900 * pattern[k])
        _key_energy(flash, f, e)
    _constant(flash)
    return [flash]


def _moonlight(r: Rig):
    """Cold, hard moonlight through the window, nothing else."""
    if r.sun_window:
        from .locations.common import aim_sun_through
        az, el = aim_sun_through(r.sun_window, r.S, 24.0)
        a, e = math.radians(az), math.radians(el)
        d_from = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    else:
        d_from = (r.toward_cam * -0.4 + r.right * 0.8 + Vector((0, 0, 0.6))).normalized()
    sun = _light("MoodMoon", "SUN", 0.9, kelvin_rgb(7800), r.S + d_from * 5, r.S, size=math.radians(0.6), col=r.col)
    sun.data.energy = 0.9
    return [sun]


def _red_room(r: Rig):
    """A darkroom safelight: deep red, one source, everything else gone."""
    lt = _light("MoodSafelight", "AREA", 24, (1.0, 0.05, 0.015), r.around(40, 55, 1.1), r.S, size=0.22, col=r.col)
    return [lt]


BUILDERS = {"low_key": _low_key, "noir_blinds": _blinds, "bare_bulb": _bare_bulb, "torch": _torch,
            "candle": _candle, "tv_glow": _tv, "neon": _neon, "police": _police, "lightning": _lightning,
            "moonlight": _moonlight, "red_room": _red_room}


def apply(mood: str, rig: Rig, existing_lights: list):
    """Turn the set's own lights down as the mood asks, then add the mood's lights."""
    if mood not in BUILDERS:
        return []
    lamps = settings(mood)["lamps"]
    scale = {"keep": 1.0, "dim": 0.12, "off": 0.0}[lamps]
    if scale < 1.0:
        for ob in existing_lights:
            if ob.type != "LIGHT" or getattr(ob.data.cycles, "is_portal", False):
                continue
            if ob.data.animation_data and ob.data.animation_data.action:
                from .camera_rig import _fcurves
                for fc in _fcurves(ob.data.animation_data.action):
                    if fc.data_path == "energy":
                        for kp in fc.keyframe_points:
                            kp.co.y *= scale
                            kp.handle_left.y *= scale
                            kp.handle_right.y *= scale
            ob.data.energy *= scale
            if scale == 0.0:
                ob.hide_render = True
    return BUILDERS[mood](rig)
