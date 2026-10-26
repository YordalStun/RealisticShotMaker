"""Shot programs: a shot is a list of segments joined by transitions.

Each segment frames one photo with its own little move. Segments either flow into each other
(continuous camera travel) or are joined by a cut. Cuts can be hidden the way editors and camera
operators do it: inside the motion blur of a whip pan, or behind something passing right in front
of the lens.

`build_program()` returns a Program the camera rig samples per frame.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import bpy
from mathutils import Matrix, Vector

from .camera_rig import (Anchors, Pose, dolly_ease, elevate, framing_distance, lerp, make_move, rot_z, slerp_dir,
                         smootherstep)

FUN_MOVES = ("whip_pan", "whip_cut", "crash_zoom", "dolly_zoom", "wipe_reveal", "speed_ramp", "roll_reveal",
             "orbit")
MULTI_MOVES = ("photo_tour", "photo_montage")
FRAME_MOVES = ("frame_track", "frame_rack", "frame_reflection", "frame_tilt")
ZOOM_MOVES = ("crash_zoom", "dolly_zoom")


@dataclass
class Segment:
    t0: float
    t1: float
    fn: object                 # local t (0..1) -> Pose
    cut_in: bool = False       # a cut happens at t0 (camera jumps, focus snaps)

    def local(self, t: float) -> float:
        return (t - self.t0) / max(1e-9, self.t1 - self.t0)


@dataclass
class Program:
    segments: list
    zoomable: bool = False
    occluders: list = field(default_factory=list)

    def __call__(self, t: float) -> Pose:
        for s in self.segments:
            if t <= s.t1 or s is self.segments[-1]:
                return s.fn(min(1.0, max(0.0, s.local(t))))
        return self.segments[-1].fn(1.0)

    @property
    def cuts(self) -> list[tuple[float, Segment]]:
        return [(s.t0, s) for s in self.segments if s.cut_in]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ease_in(t, p=3):
    return max(0.0, min(1.0, t)) ** p


def ease_out(t, p=3):
    return 1 - (1 - max(0.0, min(1.0, t))) ** p


def ease_in_out_quint(t):
    t = max(0.0, min(1.0, t))
    return 16 * t ** 5 if t < 0.5 else 1 - (-2 * t + 2) ** 5 / 2


def _right_of(view: Vector) -> Vector:
    r = view.cross(Vector((0, 0, 1)))
    if r.length < 1e-6:
        r = Vector((1, 0, 0))
    return r.normalized()


def photo_view(photo: dict, base: Vector) -> Vector:
    """Where to look at a photo from: square to an upright print, from above for one lying flat."""
    n = Vector(photo["normal"]).normalized()
    if n.z < 0.6:
        return (base * 0.2 + n * 0.8).normalized()
    horiz = Vector((base.x, base.y, 0.0))
    if horiz.length < 1e-6:
        horiz = Vector((0, -1, 0))
    return elevate(horiz.normalized(), 48.0)


def photo_distance(photo: dict, fill: float, focal: float, sensor_h: float, view: Vector) -> float:
    n = Vector(photo["normal"]).normalized()
    apparent = photo["height"] * max(0.4, abs(n.dot(view)))
    return framing_distance(apparent, fill, focal, sensor_h)


def other_photos(anchors: Anchors, count: int) -> list[dict]:
    """Nearby non-hero photos, nearest first."""
    photos = (anchors.extra or {}).get("photos", [])
    S = anchors.subject
    others = [p for p in photos if not p.get("hero") and (Vector(p["centre"]) - S).length > 0.03]
    others.sort(key=lambda p: (Vector(p["centre"]) - S).length)
    return others[:count]


def _hold(eye: Vector, target: Vector, drift: Vector, push: float = 0.0, focus=None):
    """A gentle 'breathing' hold on a photo: tiny drift and push so the frame never feels frozen."""
    def f(t):
        e = lerp(t, smootherstep(t), 0.5)
        d = (target - eye)
        tgt = target + drift * (e - 0.5)
        return Pose(eye + d * (push * e) + drift * (e - 0.5) * 1.3, tgt, focus if focus is not None else tgt)
    return f


def _occluder(name: str, at: Vector, up_len: float = 0.6, radius: float = 0.035):
    """A dark object right in front of the lens (a door frame / post / plant stem). Fully defocused it
    becomes a soft dark wipe across the frame."""
    from . import materials as M
    from .util import cylinder, link
    col = bpy.data.collections.get("RSM_Set") or bpy.context.scene.collection
    o = cylinder(name, radius, up_len, (at.x, at.y, at.z - up_len / 2), M.wood(f"{name}Wood", "walnut", 0.5, 0.4,
                                                                              grain_axis="Z"), col, 32)
    return o


# ---------------------------------------------------------------------------
# Program builders
# ---------------------------------------------------------------------------

def build_program(move: str, a: Anchors, D: float, amount: float, focal: float, sensor_h: float, fill: float,
                  cam_spec: dict) -> Program:
    S = a.subject
    base = a.view_dir.normalized()
    right = _right_of(base)
    eye0 = S + elevate(base, 1) * D

    if move == "whip_pan":
        start = a.pan_from if a.pan_from is not None else S + right * 0.5
        others = other_photos(a, 1)
        if others:
            start = Vector(others[0]["centre"])
        d_start, d_end = (start - eye0).normalized(), (S - eye0).normalized()

        def f(t):
            if t < 0.3:          # a beat on the first thing
                return Pose(eye0, eye0 + d_start * D, start)
            if t < 0.46:         # the whip: very fast, all motion blur
                e = ease_in_out_quint((t - 0.3) / 0.16)
                return Pose(eye0, eye0 + slerp_dir(d_start, d_end, e) * D, start.lerp(S, e))
            k = (t - 0.46) / 0.54
            # the operator lands a touch past the photo and settles back, then eases in
            over = 0.035 * math.sin(min(1.0, k / 0.25) * math.pi) * (1 - min(1.0, k / 0.25))
            d = slerp_dir(d_start, d_end, 1.0 + over)
            push = dolly_ease(k) * 0.12 * amount
            return Pose(eye0 + (S - eye0) * push, eye0 + d * D, S)
        return Program([Segment(0, 1, f)])

    if move == "whip_cut":
        others = other_photos(a, 1)
        if others:
            P = others[0]
            vP = photo_view(P, base)
            DP = photo_distance(P, fill, focal, sensor_h, vP)
            PC = Vector(P["centre"])
        else:  # no second photo: open on the room instead
            PC = a.pan_from if a.pan_from is not None else S + right * 0.4
            vP = rot_z(base, math.radians(-40))
            DP = D
        eyeA = PC + vP * DP
        rA = _right_of(vP)
        whip = math.radians(55)

        def seg_a(t):
            # a held look at the first photo, then the camera whips away (accelerating into a blur)
            hold = 0.62
            if t < hold:
                return _hold(eyeA, PC, rA * 0.01)(t / hold)
            e = ease_in((t - hold) / (1 - hold), 3)
            d = rot_z((PC - eyeA).normalized(), -whip * e)
            return Pose(eyeA, eyeA + d * DP, PC)

        def seg_b(t):
            # ...and arrives already whipping, decelerating onto the hero photo, then a slow push
            land = 0.3
            dS = (S - eye0).normalized()
            if t < land:
                e = ease_out(t / land, 3)
                d = rot_z(dS, whip * (1 - e))
                return Pose(eye0, eye0 + d * D, S)
            k = (t - land) / (1 - land)
            return Pose(eye0 + (S - eye0) * dolly_ease(k) * 0.14 * amount, S, S)
        cut = 0.42
        return Program([Segment(0, cut, seg_a), Segment(cut, 1, seg_b, cut_in=True)])

    if move == "crash_zoom":
        z1 = 2.6
        eye = S + elevate(base, 1) * D * z1

        def f(t):
            k = (t - 0.35) / 0.12
            z = 1.0 + (z1 - 1.0) * ease_in_out_quint(k)
            if k > 1.0:  # a little bounce as the zoom ring hits its stop
                bounce = math.exp(-(k - 1.0) * 4.0) * math.sin((k - 1.0) * 9.0) * 0.06
                z = z1 * (1 + bounce)
            p = Pose(eye, S, S)
            p.zoom = z
            return p
        return Program([Segment(0, 1, f)], zoomable=True)

    if move == "dolly_zoom":
        k1 = 1.0 + 1.4 * amount

        def f(t):
            e = dolly_ease(t)
            k = lerp(1.0, k1, e)
            p = Pose(S + elevate(base, 1) * D * k, S, S)
            p.zoom = k  # zoom in exactly as fast as the camera backs off: the photo stays put, the room stretches
            return p
        return Program([Segment(0, 1, f)], zoomable=True)

    if move == "wipe_reveal":
        # slide sideways past something right in front of the lens
        span = 0.5 * D * amount
        path0 = S + base * D - right * span
        path1 = S + base * D + right * span * 0.35
        t_cover = 0.22
        cover_eye = path0.lerp(path1, smootherstep(t_cover))
        towards = (S - cover_eye).normalized()
        occ = _occluder("WipeOccluder", cover_eye + towards * 0.09, up_len=1.2, radius=0.03)

        def f(t):
            e = smootherstep(t)
            eye = path0.lerp(path1, e)
            return Pose(eye, S + right * (e - 0.5) * 0.04, S)
        prog = Program([Segment(0, 1, f)])
        prog.occluders.append(occ)
        return prog

    if move == "speed_ramp":
        def f(t):
            e = ease_out(t, 4)  # rushes in, then crawls the last little bit
            k = lerp(2.4, 0.86, e)
            return Pose(S + elevate(base, lerp(6, 1, e)) * D * k, S, S)
        return Program([Segment(0, 1, f)])

    if move == "roll_reveal":
        def f(t):
            e = ease_out(min(1.0, t / 0.7), 3)
            p = Pose(S + elevate(base, 1) * D * lerp(1.5, 0.95, dolly_ease(t)), S, S, roll=math.radians(-75) * (1 - e))
            return p
        return Program([Segment(0, 1, f)])

    if move == "orbit":
        flat = a.card_normal.z > 0.6
        sweep = math.radians(360 if flat else 150) * min(1.0, amount)
        el = 40.0 if flat else 4.0

        def f(t):
            e = lerp(t, smootherstep(t), 0.35)
            ang = -sweep / 2 + sweep * e
            v = elevate(rot_z(Vector((base.x, base.y, 0)).normalized(), ang), el)
            return Pose(S + v * D * 1.1, S, S)
        return Program([Segment(0, 1, f)])

    if move in ("photo_tour", "photo_montage"):
        others = other_photos(a, 3)
        stops = [dict(centre=p["centre"], normal=p["normal"], height=p["height"]) for p in reversed(others)]
        stops.append(dict(centre=S, normal=a.card_normal, height=a.card_height, hero=True))
        n = len(stops)
        shots = []
        for p in stops:
            v = photo_view(p, base)
            Dp = photo_distance(p, fill, focal, sensor_h, v) if not p.get("hero") else D
            c = Vector(p["centre"])
            shots.append((c, c + v * Dp, _right_of(v)))
        if n == 1:
            return Program([Segment(0, 1, make_move("push_in", a, D, amount))])
        # the hero gets the most time
        weights = [1.0] * (n - 1) + [1.6]
        total = sum(weights)
        bounds = [0.0]
        for w in weights:
            bounds.append(bounds[-1] + w / total)
        segs = []
        if move == "photo_montage":
            for i, (c, eye, r) in enumerate(shots):
                sgn = 1 if i % 2 == 0 else -1  # alternate the drift direction between shots
                segs.append(Segment(bounds[i], bounds[i + 1],
                                    _hold(eye, c, r * 0.012 * sgn, push=0.1 * amount), cut_in=i > 0))
            return Program(segs)
        # photo_tour: hold on each photo, travel smoothly to the next while racking focus
        for i, (c, eye, r) in enumerate(shots):
            t0, t1 = bounds[i], bounds[i + 1]
            if i == 0:
                segs.append(Segment(t0, t1, _hold(eye, c, r * 0.01, push=0.05)))
                continue
            prev_end = segs[-1].fn(1.0)   # start exactly where the last hold finished: no jump
            pc = prev_end.focus_point

            def travel(t, c=c, eye=eye, prev_end=prev_end, pc=pc, r=r):
                move_part = 0.45
                if t < move_part:
                    e = smootherstep(t / move_part)
                    # rise slightly between photos like a camera on a slider arm
                    lift = Vector((0, 0, 0.04 * math.sin(e * math.pi)))
                    tgt = prev_end.target.lerp(c, e)
                    return Pose(prev_end.eye.lerp(eye, e) + lift, tgt,
                                pc.lerp(c, smootherstep((t / move_part - 0.2) / 0.6)))
                return _hold(eye, c, r * 0.01, push=0.05)((t - move_part) / (1 - move_part))
            segs.append(Segment(t0, t1, travel))
        return Program(segs)

    if move in FRAME_MOVES:
        return _frame_move(move, a, D, amount, base, right)

    return Program([Segment(0, 1, make_move(move, a, D, amount))])


def _soft_focus(photos: list, look: Vector, fallback: Vector, width: float = 0.09) -> Vector:
    """Focus on whichever photo the frame is looking at, blending smoothly between neighbours the way a
    focus puller follows a pan along a wall of pictures."""
    if not photos:
        return fallback
    wsum, acc = 0.0, Vector()
    for p in photos:
        c = Vector(p["centre"])
        w = math.exp(-((c - look).length / width) ** 2) + 1e-9
        wsum += w
        acc += c * w
    near = min(photos, key=lambda p: (Vector(p["centre"]) - look).length)
    soft = acc / wsum
    # nothing near the look point: hold focus on the closest photo rather than on empty wall
    return soft if (Vector(near["centre"]) - look).length < 0.25 else Vector(near["centre"])


def _frame_move(move: str, a: Anchors, D: float, amount: float, base: Vector, right: Vector) -> Program:
    """Moves made for walls and rows of framed photos."""
    S = a.subject
    photos = [dict(p, centre=Vector(p["centre"])) for p in (a.extra or {}).get("photos", [])]
    others = [p for p in photos if not p.get("hero")]
    eye0 = S + elevate(base, 1) * D

    if move == "frame_track":
        # come from the side with more frames, passing two or three of them, and settle on the hero
        def lateral(p):
            return (p["centre"] - S).dot(right)
        left = [p for p in others if -1.2 < lateral(p) < -0.05 and abs(p["centre"].z - S.z) < 0.35]
        rgt = [p for p in others if 0.05 < lateral(p) < 1.2 and abs(p["centre"].z - S.z) < 0.35]
        side = -1.0 if len(left) >= len(rgt) else 1.0
        pool = left if side < 0 else rgt
        span = max(0.35, min(1.0, max((abs(lateral(p)) for p in pool), default=0.45) + 0.1)) * min(1.4, 0.6 + amount * 0.5)
        start = right * span * side

        def f(t):
            e = 1 - (1 - min(1.0, t / 0.88)) ** 2.2       # decelerating track that lands on the hero
            drift = max(0.0, t - 0.88) / 0.12 * 0.004      # the last moments still breathe
            off = start * (1 - e) - right * side * drift
            eye = eye0 + off
            look = S + off
            return Pose(eye, look, _soft_focus(photos, look, S))
        return Program([Segment(0, 1, f)])

    if move == "frame_rack":
        # a neighbouring frame sits soft and large on one side of the picture; focus pulls past it to the hero
        nb = min(others, key=lambda p: (p["centre"] - S).length) if others else None
        if nb is None:
            return Program([Segment(0, 1, make_move("rack_in", a, D, amount))])
        to_nb = nb["centre"] - S
        u = Vector((to_nb.x, to_nb.y, 0.0))
        u = u.normalized() if u.length > 1e-6 else right
        hb = Vector((base.x, base.y, 0.0)).normalized()
        v = (hb * math.cos(math.radians(50)) + u * math.sin(math.radians(50))).normalized()
        v = elevate(v, 6 + max(0.0, (nb["centre"].z - S.z)) * 20)
        Dr = D * 0.85
        eye = S + v * Dr
        tgt = S + to_nb * 0.18
        P = nb["centre"]

        def f(t):
            k = smootherstep((t - 0.3) / 0.35)
            push = dolly_ease(t) * 0.06 * amount
            return Pose(eye + (tgt - eye) * push, tgt, P.lerp(S, k))
        return Program([Segment(0, 1, f)])

    if move == "frame_reflection":
        # from an angle the glass shows the room; swinging square, the reflection slides off the photo
        side = 1.0
        hb = Vector((base.x, base.y, 0.0)).normalized()
        start_dir = elevate(rot_z(hb, math.radians(38) * side), 9)
        end_dir = elevate(base, 1)

        def f(t):
            e = smootherstep(t)
            d = slerp_dir(start_dir, end_dir, e)
            dist = D * (1.12 - 0.12 * dolly_ease(t) * min(1.5, amount))
            return Pose(S + d * dist, S, S)
        return Program([Segment(0, 1, f)])

    if move == "frame_tilt":
        # start on a frame higher up the wall (or the top of the wall) and sink down onto the hero
        above = [p for p in others if p["centre"].z > S.z + 0.12 and abs((p["centre"] - S).dot(right)) < 0.6]
        if above:
            top = min(above, key=lambda p: abs((p["centre"] - S).dot(right)) + 0.3 * (p["centre"].z - S.z))["centre"]
        else:
            top = a.tilt_from if a.tilt_from is not None else S + Vector((0, 0, 0.45))
        rise = (top.z - S.z) * min(1.3, 0.55 + 0.4 * amount)
        eye_hi = eye0 + Vector((0, 0, rise))

        def f(t):
            e = dolly_ease(t, 0.35)
            eye = eye_hi.lerp(eye0, e)
            tgt = top.lerp(S, smootherstep(t * 1.05))
            return Pose(eye, tgt, _soft_focus(photos, tgt, S, 0.12))
        return Program([Segment(0, 1, f)])

    return Program([Segment(0, 1, make_move("push_in", a, D, amount))])
