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
    zoom: float = 1.0      # optical zoom factor on top of the lens' focal length


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
    """Follows the target focus distance like a good human focus puller: he has rehearsed the move, so he
    tracks its speed as well as its position (no lag on smooth moves), overshoots a touch on sudden racks
    and drifts very slightly while holding."""

    def __init__(self, seed: int, skill_noise: float):
        self.noise = Noise1D(seed + 991)
        self.amount = skill_noise
        self.pos = None
        self.vel = 0.0
        self.prev_target = None

    def step(self, target: float, dt: float, t: float) -> float:
        xt = 1.0 / max(target, 1e-3)      # work in diopters, which is how a focus ring behaves
        vt = 0.0 if self.prev_target is None else (xt - self.prev_target) / dt
        self.prev_target = xt
        if self.pos is None or self.amount <= 0:
            self.pos = target
            self.vel = vt
            return target
        omega = 16.0 / (0.4 + self.amount)
        zeta = 0.62
        x, v = 1.0 / self.pos, self.vel
        steps = 8
        h = dt / steps
        for _ in range(steps):
            acc = omega * omega * (xt - x) + 2 * zeta * omega * (vt - v)
            v += acc * h
            x += v * h
        self.vel = v
        drift = self.noise.fbm(t * 0.35, 3) * 0.0012 * self.amount  # a good focus puller holds within the DoF
        self.pos = 1.0 / max(1e-3, x * (1 + drift))
        return self.pos


_SEE_THROUGH = ("Haze", "DustMotes", "_glass", "Glass", "Portal", "HeroPrint")


def _clear_view(p: Pose, anchors: Anchors) -> bool:
    """True if the straight line from the camera to the subject is unobstructed."""
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    eye = _inside_room(p.eye.copy(), p.target, anchors)
    if anchors.min_height is not None and eye.z < anchors.min_height:
        eye.z = anchors.min_height
    target = p.focus_point
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


def _inside_room(eye: Vector, target: Vector, anchors: Anchors, margin: float = 0.25) -> Vector:
    """Walls are real: if a framing would put the camera through a wall, stop just inside it."""
    room = anchors.extra.get("room") if anchors.extra else None
    if not room:
        return eye
    mn, mx = Vector(room[0]), Vector(room[1])
    lo, hi = mn + Vector((margin, margin, margin)), mx - Vector((margin, margin, margin))
    if all(lo[i] <= eye[i] <= hi[i] for i in range(3)):
        return eye
    d = eye - target
    t_max = 1.0
    for i in range(3):
        if abs(d[i]) < 1e-9:
            continue
        for bound in (lo[i], hi[i]):
            t = (bound - target[i]) / d[i]
            if 0 < t < t_max:
                t_max = t
    return target + d * max(0.05, t_max)


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


def _speed(a: Pose, b: Pose) -> float:
    """How much the picture changes between two poses (camera travel plus where it points)."""
    return (b.eye - a.eye).length + 0.5 * (b.target - a.target).length + 0.2 * abs(b.zoom - a.zoom)


def roll_into_cuts(prog: Program, samples: int = 96) -> Program:
    """After a cut, start each move mid-stride, the way an editor cuts into a shot that's already moving.

    Every move eases in from a standstill, which looks wrong straight after a cut: the new shot sits still
    for a beat before it gets going. For each segment that begins with a cut, find how far into its own
    motion it reaches its normal pace and begin there instead, so frame one after the cut is already moving.
    Segments that are already moving at the cut (a whip landing) start where they are."""
    for seg in prog.segments:
        if not seg.cut_in:
            continue
        f = seg.fn
        poses = [f(k / samples) for k in range(samples + 1)]
        steps = [_speed(poses[k], poses[k + 1]) for k in range(samples)]
        mean = sum(steps) / samples
        if mean < 1e-7:
            continue  # a locked-off hold: nothing to roll into
        u0 = 0.0
        for k, sp in enumerate(steps):
            if sp >= 0.8 * mean:
                u0 = k / samples
                break
        u0 = min(u0, 0.35)   # never skip more than about a third of the move
        if u0 > 0.0:
            seg.fn = (lambda t, f=f, u0=u0: f(u0 + (1.0 - u0) * t))
    return prog


def animate_camera(cam_obj, cam_spec: dict, anchors: Anchors, fps: float, frame_start: int, frame_end: int,
                   sensor: tuple[float, float], fill: float, seed: int, aspect: float):
    """Keyframe camera transform, focus and zoom for every frame. Returns (framing distance, program)."""
    from .shots import Program, Segment, build_program
    focal = float(cam_spec["focal_mm"])
    sensor_w, _ = sensor
    sensor_h_eff = sensor_w / aspect
    D = framing_distance(anchors.card_height, fill, focal, sensor_h_eff)
    # square up to the print like a DP shooting an insert: look at its face, not at its edge, so the whole
    # print lies in the (very thin, at 4K) plane of focus. Flat prints keep the set's own viewpoint.
    view0 = anchors.view_dir.normalized()
    nrm = anchors.card_normal.normalized()
    if nrm.z < 0.6:
        old_dot = max(0.35, abs(nrm.dot(view0)))
        view0 = (view0 * 0.2 + nrm * 0.8).normalized()
        # the print now faces the lens more squarely, so it looks taller: frame for that
        anchors = Anchors(**{**anchors.__dict__,
                             "card_height": anchors.card_height * max(0.35, abs(nrm.dot(view0))) / old_dot})
        D = framing_distance(anchors.card_height, fill, focal, sensor_h_eff)
    # user adjustments of the default viewpoint
    base = rot_z(view0, math.radians(float(cam_spec.get("angle", 0.0))))
    base = elevate(base, float(cam_spec.get("height", 0.0)) * 25.0)
    move = cam_spec["move"]
    amount = float(cam_spec.get("move_amount", 1.0))
    cut_t = min(0.9, max(0.1, float(cam_spec.get("cut_at", 0.4))))
    cut_to = cam_spec.get("cut_to", "push_in")
    if cut_to == "macro_cut":
        cut_to = "push_in"
    D_macro = framing_distance(anchors.card_height, float(cam_spec.get("macro_fill", 4.0)), focal, sensor_h_eff)

    def build(view_dir) -> Program:
        a = Anchors(**{**anchors.__dict__, "view_dir": view_dir})
        if move == "macro_cut":
            fb = build_program(cut_to, a, D, amount, focal, sensor_h_eff, fill, cam_spec)
            segs = [Segment(0.0, cut_t, macro_move(a, D_macro))]
            for sg in fb.segments:  # the move after the cut keeps its own segments (and its own cuts)
                segs.append(Segment(cut_t + sg.t0 * (1 - cut_t), cut_t + sg.t1 * (1 - cut_t), sg.fn,
                                    cut_in=sg.cut_in or sg.t0 == 0.0))
            prog_ = Program(segs, zoomable=fb.zoomable, occluders=fb.occluders)
        else:
            prog_ = build_program(move, a, D, amount, focal, sensor_h_eff, fill, cam_spec)
        if cam_spec.get("cut_in_motion", True):
            roll_into_cuts(prog_)
        return prog_

    # make sure nothing solid sits between the lens and the photo anywhere along the move;
    # if something does, raise the camera a little at a time (like an operator would)
    prog = None
    for _ in range(14):
        if prog is not None:
            for o in prog.occluders:
                bpy.data.objects.remove(o, do_unlink=True)
        prog = build(base)
        bpy.context.view_layer.update()
        if all(_clear_view(prog(t), anchors) for t in (0.0, 0.12, 0.25, 0.5, 0.75, 0.9, 1.0)
               if not prog.occluders):
            break
        base = elevate(base, 3.0)

    handheld = float(cam_spec.get("handheld", 0.0)) + (1.0 if move == "handheld" or (move == "macro_cut" and cut_to == "handheld") else 0.0)
    wobble = 0.0 if move in ("locked_off", "crash_zoom") else float(cam_spec.get("rig_wobble", 0.0))
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
    cut_frames = {}
    for t_cut, seg in prog.cuts:
        f = frame_start + int(math.ceil(t_cut * (n - 1) - 1e-6))
        if frame_start < f <= frame_end:
            cut_frames[f] = seg

    def solve(p: Pose, time_s: float, prev_q):
        eye = _inside_room(p.eye.copy(), p.target, anchors)
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

    def key(frame, loc, q, dist, zoom):
        cam_obj.location = loc
        cam_obj.rotation_quaternion = q
        cam_obj.keyframe_insert("location", frame=frame)
        cam_obj.keyframe_insert("rotation_quaternion", frame=frame)
        cam.dof.focus_distance = dist
        cam.dof.keyframe_insert("focus_distance", frame=frame)
        if prog.zoomable:
            cam.dof.aperture_ratio = max(0.05, zoom)
            cam.dof.keyframe_insert("aperture_ratio", frame=frame)

    prev_q = None
    for i in range(n):
        frame = frame_start + i
        t = i / max(1, n - 1)
        time_s = i * dt
        if frame in cut_frames:
            puller.pos = None  # a new shot: the focus is simply set, not pulled
            puller.vel = 0.0
            puller.prev_target = None
        p = prog(t)
        loc, q, target_dist = solve(p, time_s, prev_q)
        prev_q = q
        key(frame, loc, q, puller.step(target_dist, dt, time_s), p.zoom)

    # clean cuts: hold each outgoing shot until half a frame before the cut, then jump. The motion blur of
    # a frame only ever sees its own shot -- which is exactly what lets a whip pan hide the cut.
    for f, seg in cut_frames.items():
        half = f - 0.5
        p = seg.fn(0.0)
        loc, q, dist = solve(p, (half - frame_start) * dt, prev_q=None)
        key(half, loc, q, dist, p.zoom)
        for owner in (cam_obj, cam):
            ad = owner.animation_data
            if not ad or not ad.action:
                continue
            for fc in _fcurves(ad.action):
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - (f - 1)) < 1e-3:
                        kp.interpolation = "CONSTANT"
    return D, prog


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
