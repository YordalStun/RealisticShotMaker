"""Camera placement, premade moves and the imperfections of real camera operation.

Every move is evaluated per frame (and the F-curves are left smooth), so the
camera path is exact and motion blur / rolling shutter see the true motion.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import bpy
from mathutils import Matrix, Quaternion, Vector

from .util import look_at_matrix


# ---------------------------------------------------------------------------
# Smooth noise
# ---------------------------------------------------------------------------

class Noise1D:
    """Deterministic 1D gradient noise, roughly -1..1."""

    def __init__(self, seed: int):
        r = random.Random(seed)
        self.g = [r.uniform(-1, 1) for _ in range(512)]

    def __call__(self, t: float) -> float:
        i = math.floor(t)
        f = t - i
        g0 = self.g[i % 512]
        g1 = self.g[(i + 1) % 512]
        u = f * f * f * (f * (f * 6 - 15) + 10)
        return 2.0 * ((1 - u) * g0 * f + u * g1 * (f - 1))

    def fbm(self, t: float, octaves=4, lacunarity=2.03, gain=0.5) -> float:
        s, a, freq = 0.0, 1.0, 1.0
        for k in range(octaves):
            s += a * self(t * freq + k * 17.31)
            a *= gain
            freq *= lacunarity
        return s


class Shake:
    """Layered camera shake: breathing, body sway and fine muscle jitter."""

    def __init__(self, seed: int):
        self.n = [Noise1D(seed * 31 + i) for i in range(12)]

    def sample(self, t: float, handheld: float, wobble: float):
        """Return (position offset [m], (pitch, yaw, roll) [rad])."""
        n = self.n
        pos = Vector((0.0, 0.0, 0.0))
        rot = [0.0, 0.0, 0.0]
        if handheld > 0:
            breathe = math.sin(t * 2 * math.pi * 0.23 + 1.3)  # ~14 breaths/min
            pos += Vector((n[0].fbm(t * 0.6, 3) * 0.004, n[1].fbm(t * 0.5, 3) * 0.003,
                           n[2].fbm(t * 0.7, 3) * 0.003 + breathe * 0.0012)) * handheld
            rot[0] += (n[3].fbm(t * 0.8, 4) * 0.0045 + breathe * 0.0008 + n[4](t * 7.5) * 0.0004) * handheld
            rot[1] += (n[5].fbm(t * 0.7, 4) * 0.0050 + n[6](t * 8.3) * 0.0004) * handheld
            rot[2] += (n[7].fbm(t * 0.5, 3) * 0.0030) * handheld
        if wobble > 0:
            # slider bearings / dolly track joints: small, quicker, mostly vertical
            pos += Vector((n[8](t * 4.1) * 0.00025, n[9](t * 3.3) * 0.0002, n[10](t * 5.7) * 0.0004)) * wobble
            rot[0] += n[11](t * 6.1) * 0.00025 * wobble
            rot[1] += n[8](t * 5.3 + 40) * 0.0002 * wobble
        return pos, rot


# ---------------------------------------------------------------------------
# Easing
# ---------------------------------------------------------------------------

def smootherstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (t * 6 - 15) + 10)


def dolly_ease(t, ramp=0.3):
    """Constant speed in the middle with soft acceleration/deceleration (like a grip pushing a dolly)."""
    t = max(0.0, min(1.0, t))
    r = ramp
    v = 1.0 / (1.0 - r)  # peak speed so the total distance is 1
    if t < r:
        return 0.5 * v * t * t / r
    if t > 1 - r:
        u = 1 - t
        return 1 - 0.5 * v * u * u / r
    return 0.5 * v * r + v * (t - r)


def lerp(a, b, t):
    return a + (b - a) * t


def slerp_dir(a: Vector, b: Vector, t: float) -> Vector:
    a, b = a.normalized(), b.normalized()
    dot = max(-1.0, min(1.0, a.dot(b)))
    th = math.acos(dot)
    if th < 1e-5:
        return a.lerp(b, t).normalized()
    s = math.sin(th)
    return (a * math.sin((1 - t) * th) / s + b * math.sin(t * th) / s).normalized()


# ---------------------------------------------------------------------------
# Rig
# ---------------------------------------------------------------------------

@dataclass
class Anchors:
    subject: Vector                      # world point the shot is about (centre of the picture)
    card_normal: Vector                  # world direction the print faces
    card_height: float                   # metres
    view_dir: Vector                     # unit vector from subject towards the default camera position
    rack_point: Vector | None = None     # background object for rack focus
    tilt_from: Vector | None = None      # where tilt reveals start (e.g. the window)
    pan_from: Vector | None = None       # neighbouring object for pan-across
    reveal_target: Vector | None = None  # where pull-outs drift to
    min_height: float | None = None      # keep the camera above this z (table top + clearance)
    extra: dict = field(default_factory=dict)


@dataclass
class Pose:
    eye: Vector
    target: Vector
    focus_point: Vector
    roll: float = 0.0


def rot_z(v: Vector, ang: float) -> Vector:
    return Matrix.Rotation(ang, 3, "Z") @ v


def framing_distance(card_h: float, fill: float, focal_mm: float, sensor_h_mm: float) -> float:
    vfov = 2 * math.atan(sensor_h_mm / 2 / focal_mm)
    return (card_h / fill) / (2 * math.tan(vfov / 2))


def elevate(v: Vector, delta_deg: float) -> Vector:
    """Raise/lower a direction vector by delta degrees towards +Z."""
    horiz = Vector((v.x, v.y, 0.0))
    if horiz.length < 1e-6:
        return v
    el = math.atan2(v.z, horiz.length) + math.radians(delta_deg)
    el = max(math.radians(-10), min(math.radians(89.5), el))
    h = horiz.normalized()
    return Vector((h.x * math.cos(el), h.y * math.cos(el), math.sin(el)))


def make_move(move: str, a: Anchors, D: float, amount: float):
    """Return a function t(0..1) -> Pose."""
    S = a.subject
    base = a.view_dir.normalized()
    right = base.cross(Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    am = amount

    def pose(eye, target, focus=None, roll=0.0):
        return Pose(eye, target, focus if focus is not None else S, roll)

    if move == "push_in":
        return lambda t: pose(S + elevate(base, lerp(4, -1, dolly_ease(t))) * D * lerp(1 + 0.4 * am, 1 - 0.2 * am, dolly_ease(t)), S)
    if move == "pull_out":
        rt = a.reveal_target if a.reveal_target is not None else S + Vector((0, 0, 0.05))

        def f(t):
            e = dolly_ease(t)
            eye = S + elevate(base, lerp(-1, 7 * am, e)) * D * lerp(0.8, 0.8 + 1.4 * am, e)
            return pose(eye, S.lerp(rt, e * 0.6))
        return f
    if move in ("slide_right", "slide_left"):
        sgn = 1 if move == "slide_right" else -1

        def f(t):
            e = lerp(t, smootherstep(t), 0.65)
            off = (e - 0.5) * 2 * sgn
            eye = S + base * D + right * (0.42 * D * am * off)
            tgt = S + right * (0.14 * D * am * off)
            return pose(eye, tgt)
        return f
    if move in ("arc_right", "arc_left"):
        sgn = 1 if move == "arc_right" else -1

        def f(t):
            ang = math.radians(lerp(-22, 22, dolly_ease(t)) * am * sgn)
            return pose(S + rot_z(base, ang) * D, S)
        return f
    if move == "tilt_reveal":
        eye = S + elevate(base, 2) * D * 1.05
        start = a.tilt_from if a.tilt_from is not None else S + Vector((0, 0, 0.6)) - base * 1.5
        d0, d1 = (start - eye).normalized(), (S - eye).normalized()

        def f(t):
            d = slerp_dir(d0, d1, smootherstep(t))
            return pose(eye, eye + d * D)
        return f
    if move in ("rack_in", "rack_out"):
        rp = a.rack_point if a.rack_point is not None else S - base * 0.5 + Vector((0.15, 0, 0.1))
        side = rot_z(base, math.radians(-14))
        eye = S + elevate(side, 2) * D * 1.15
        tgt = S.lerp(rp, 0.32)

        def f(t):
            k = smootherstep((t - 0.28) / 0.4)
            if move == "rack_out":
                k = 1 - k
            return pose(eye, tgt, rp.lerp(S, k))
        return f
    if move == "crane_down":
        def f(t):
            e = dolly_ease(t)
            return pose(S + elevate(base, lerp(38 * am, 0, e)) * D * lerp(1.25, 1.0, e), S)
        return f
    if move == "top_down":
        def f(t):
            e = lerp(t, smootherstep(t), 0.5)
            roll = math.radians(lerp(-12, 12, e) * am)
            eye = S + Vector((0, 0, 1)) * D * lerp(1.05, 0.92, e) + base * 0.001
            return pose(eye, S, roll=roll)
        return f
    if move == "drift":
        def f(t):
            e = lerp(t, smootherstep(t), 0.5)
            eye = S + base * D * lerp(1.06, 0.96, e) + right * (0.06 * D * am * (e - 0.5))
            return pose(eye, S + right * (0.02 * D * (e - 0.5)))
        return f
    if move == "pan_across":
        eye = S + base * D * 1.05
        start = a.pan_from if a.pan_from is not None else S + right * 0.35
        d0, d1 = (start - eye).normalized(), (S - eye).normalized()

        def f(t):
            e = smootherstep(t)
            d = slerp_dir(d0, d1, e)
            # a camera operator racks focus with the pan
            return pose(eye, eye + d * D, start.lerp(S, smootherstep((t - 0.15) / 0.7)))
        return f
    # handheld / locked_off / unknown: static base position
    return lambda t: pose(S + elevate(base, 1) * D, S)


class FocusPuller:
    """Follows the target focus distance like a human: slight lag, a little overshoot on fast pulls,
    and tiny drift."""

    def __init__(self, seed: int, skill_noise: float):
        self.noise = Noise1D(seed + 991)
        self.amount = skill_noise
        self.pos = None
        self.vel = 0.0

    def step(self, target: float, dt: float, t: float) -> float:
        if self.pos is None:
            self.pos = target
            return target
        if self.amount <= 0:
            self.pos = target
            return target
        # under-damped spring towards the target (in diopters, which is how focus throw behaves)
        omega = 9.0 / (0.35 + self.amount)
        zeta = 0.62
        x, v = 1.0 / self.pos, self.vel
        xt = 1.0 / target
        acc = omega * omega * (xt - x) - 2 * zeta * omega * v
        steps = 8
        h = dt / steps
        for _ in range(steps):
            acc = omega * omega * (xt - x) - 2 * zeta * omega * v
            v += acc * h
            x += v * h
        self.vel = v
        drift = self.noise.fbm(t * 0.35, 3) * 0.006 * self.amount
        self.pos = 1.0 / max(1e-3, x * (1 + drift))
        return self.pos


_SEE_THROUGH = ("Haze", "DustMotes", "_glass", "Glass", "Portal", "HeroPrint")


def _clear_view(p: Pose, anchors: Anchors) -> bool:
    """True if the straight line from the camera to the subject is unobstructed."""
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    eye = p.eye.copy()
    if anchors.min_height is not None and eye.z < anchors.min_height:
        eye.z = anchors.min_height
    target = anchors.subject
    d = target - eye
    dist = d.length
    if dist < 1e-4:
        return True
    d.normalize()
    origin = eye.copy()
    travelled = 0.0
    for _ in range(16):
        hit, loc, _n, _i, obj, _m = scene.ray_cast(dg, origin, d, distance=dist - travelled)
        if not hit:
            return True
        travelled += (loc - origin).length
        if travelled > dist - 0.03:
            return True
        if obj is not None and any(k in obj.name for k in _SEE_THROUGH):
            origin = loc + d * 1e-4
            continue
        return False
    return True


def macro_move(a: Anchors, D_macro: float):
    """Slowly explore the picture itself: a gentle drift across the image while easing in."""
    S = a.subject
    base = a.view_dir.normalized()
    right = base.cross(Vector((0, 0, 1)))
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    up = right.cross(base).normalized()
    # surface directions of the print itself (so the drift stays on the picture plane)
    n = a.card_normal.normalized()
    r_s = (right - n * right.dot(n)).normalized()
    u_s = (up - n * up.dot(n)).normalized()
    span = a.card_height * 0.12

    def f(t):
        e = lerp(t, smootherstep(t), 0.6)
        tgt = S + r_s * span * lerp(-0.5, 0.35, e) + u_s * span * lerp(0.25, -0.1, e)
        eye = tgt + base * D_macro * lerp(1.04, 0.97, e)
        return Pose(eye, tgt, tgt)
    return f


def animate_camera(cam_obj, cam_spec: dict, anchors: Anchors, fps: float, frame_start: int, frame_end: int,
                   sensor: tuple[float, float], fill: float, seed: int, aspect: float):
    """Keyframe camera transform and focus for every frame."""
    focal = float(cam_spec["focal_mm"])
    sensor_w, _ = sensor
    sensor_h_eff = sensor_w / aspect
    D = framing_distance(anchors.card_height, fill, focal, sensor_h_eff)
    # user adjustments of the default viewpoint
    base = rot_z(anchors.view_dir, math.radians(float(cam_spec.get("angle", 0.0))))
    base = elevate(base, float(cam_spec.get("height", 0.0)) * 25.0)
    move = cam_spec["move"]
    amount = float(cam_spec.get("move_amount", 1.0))
    is_cut = move == "macro_cut"
    cut_t = min(0.9, max(0.1, float(cam_spec.get("cut_at", 0.4))))
    cut_to = cam_spec.get("cut_to", "push_in")
    if cut_to == "macro_cut":
        cut_to = "push_in"
    D_macro = framing_distance(anchors.card_height, float(cam_spec.get("macro_fill", 4.0)), focal, sensor_h_eff)

    def build(view_dir):
        a = Anchors(**{**anchors.__dict__, "view_dir": view_dir})
        if not is_cut:
            return make_move(move, a, D, amount), None, None
        fa = macro_move(a, D_macro)
        fb = make_move(cut_to, a, D, amount)
        return (lambda t: fa(t / cut_t) if t < cut_t else fb((t - cut_t) / (1 - cut_t))), fa, fb

    # make sure nothing solid sits between the lens and the photo anywhere along the move;
    # if something does, raise the camera a little at a time (like an operator would)
    for _ in range(14):
        fn, fa, fb = build(base)
        if all(_clear_view(fn(t), anchors) for t in (0.0, 0.25, 0.5, 0.75, 1.0)):
            break
        base = elevate(base, 3.0)

    handheld = float(cam_spec.get("handheld", 0.0)) + (1.0 if move == "handheld" or cut_to == "handheld" and is_cut else 0.0)
    wobble = 0.0 if move == "locked_off" else float(cam_spec.get("rig_wobble", 0.0))
    if move == "locked_off":
        handheld = 0.0
    shake = Shake(seed)
    puller = FocusPuller(seed, float(cam_spec.get("focus_drift", 0.0)))
    cam = cam_obj.data
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = float(cam_spec["fstop"])
    cam.dof.aperture_blades = 0  # the lens shader draws the aperture
    cam_obj.rotation_mode = "QUATERNION"

    n = frame_end - frame_start + 1
    dt = 1.0 / fps
    cut_frame = None
    if is_cut:
        cut_frame = frame_start + int(math.ceil(cut_t * (n - 1)))

    def solve(p: Pose, time_s: float, prev_q):
        eye = p.eye.copy()
        if anchors.min_height is not None and eye.z < anchors.min_height:
            eye.z = anchors.min_height
        off, (pitch, yaw, roll) = shake.sample(time_s, handheld, wobble)
        m = look_at_matrix(eye, p.target)
        rot = m.to_3x3() @ Matrix.Rotation(p.roll + roll, 3, "Z") @ Matrix.Rotation(pitch, 3, "X") \
            @ Matrix.Rotation(yaw, 3, "Y")
        loc = eye + m.to_3x3() @ off
        q = rot.to_quaternion()
        if prev_q is not None and prev_q.dot(q) < 0:
            q.negate()
        fwd = rot @ Vector((0, 0, -1))
        dist = max(0.02, (p.focus_point - loc).dot(fwd))
        return loc, q, dist

    prev_q = None
    for i in range(n):
        frame = frame_start + i
        t = i / max(1, n - 1)
        time_s = i * dt
        if frame == cut_frame:
            puller.pos = None  # a new shot: the focus is simply set, not pulled
            puller.vel = 0.0
        loc, q, target_dist = solve(fn(t), time_s, prev_q)
        prev_q = q
        cam_obj.location = loc
        cam_obj.rotation_quaternion = q
        cam_obj.keyframe_insert("location", frame=frame)
        cam_obj.keyframe_insert("rotation_quaternion", frame=frame)
        cam.dof.focus_distance = puller.step(target_dist, dt, time_s)
        cam.dof.keyframe_insert("focus_distance", frame=frame)

    if cut_frame is not None and frame_start < cut_frame <= frame_end:
        # a clean cut: hold the close-up until half a frame before the cut, then jump. Motion blur
        # of the last close-up frame and the first wide frame never mixes the two shots.
        half = cut_frame - 0.5
        loc, q, dist = solve(fb(0.0), (half - frame_start) * dt, prev_q=None)
        cam_obj.location = loc
        cam_obj.rotation_quaternion = q
        cam_obj.keyframe_insert("location", frame=half)
        cam_obj.keyframe_insert("rotation_quaternion", frame=half)
        cam.dof.focus_distance = dist
        cam.dof.keyframe_insert("focus_distance", frame=half)
        for owner in (cam_obj, cam):
            ad = owner.animation_data
            if not ad or not ad.action:
                continue
            for fc in _fcurves(ad.action):
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - (cut_frame - 1)) < 1e-3:
                        kp.interpolation = "CONSTANT"
    return D


def _fcurves(action):
    """F-curves of an action (Blender 4.4+ layered actions or the classic list)."""
    fcs = getattr(action, "fcurves", None)
    if fcs is not None and len(fcs):
        return list(fcs)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out
