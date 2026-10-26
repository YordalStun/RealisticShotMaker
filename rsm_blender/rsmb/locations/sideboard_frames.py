"""Sideboard of family photos: the top of an old sideboard crowded with framed photos, the big ones standing at the
back, a lamp, a vase of flowers and a lace runner, wallpaper and a painting behind.

Built for several photos: the camera can look past a frame in front onto the hero, or track along the rows.
"""
from __future__ import annotations

import math

from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder
from .common import (Ctx, Room, curtain, frame_size_m, keep_off_wall, opt, outdoor_backdrop, place_card, switched_on, wall,
                     wallpaper, window)

TOP_Z = 0.86


def _sideboard(col, x, face, w=1.7, d=0.5):
    wood = M.wood("SideboardWood", "mahogany", varnish=0.7, wear=0.3, grain_axis="X")
    side_wood = M.wood("SideboardWoodZ", "mahogany", varnish=0.7, wear=0.3, grain_axis="Z")
    y = face - d / 2 - 0.02
    box("SideboardTop", w + 0.04, d + 0.03, 0.035, (x, y - 0.012, TOP_Z - 0.0175), wood, col, bevel=0.008, segments=4)
    box("SideboardCarcass", w, d - 0.02, TOP_Z - 0.16, (x, y, 0.12 + (TOP_Z - 0.16) / 2), side_wood, col, bevel=0.004)
    box("SideboardPlinth", w - 0.04, d - 0.06, 0.12, (x, y + 0.01, 0.06), wood, col, bevel=0.003)
    brass = M.metal("SideboardBrass", "#b8925a", 0.3, 0.4, 0.5)
    front = y - (d - 0.02) / 2
    # two drawers over three cupboard doors, each a raised panel with a brass knob
    for i in range(3):
        cx = x - w / 3 + i * w / 3
        box(f"SideboardDoor{i}", w / 3 - 0.03, 0.018, TOP_Z - 0.36, (cx, front - 0.008, 0.14 + (TOP_Z - 0.36) / 2),
            side_wood, col, bevel=0.006, segments=3)
        box(f"SideboardPanel{i}", w / 3 - 0.12, 0.01, TOP_Z - 0.48, (cx, front - 0.019, 0.2 + (TOP_Z - 0.48) / 2),
            side_wood, col, bevel=0.01, segments=3)
        cylinder(f"SideboardKnob{i}", 0.011, 0.02, (cx + (0.1 if i < 2 else -0.1), front - 0.027, 0.5), brass, col, 20,
                 rot=(math.radians(90), 0, 0))
    for i in range(2):
        cx = x - w / 4 + i * w / 2
        box(f"SideboardDrawer{i}", w / 2 - 0.03, 0.018, 0.13, (cx, front - 0.008, TOP_Z - 0.115), wood, col, bevel=0.005)
        cylinder(f"SideboardPull{i}", 0.006, 0.12, (cx, front - 0.024, TOP_Z - 0.11), brass, col, 16,
                 rot=(0, math.radians(90), 0))
    return y, d


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    lights = []
    X0, X1, Y0, Y1, H = -2.6, 2.6, -3.0, 0.4, 2.65
    face = Y1 - 0.06
    paper = wallpaper("DiningPaper", "#a9917a", "#8f7660", 5.0)
    plain = M.plaster("DiningPlaster", "#ddd3c0", 0.88, 0.8, 0.15)
    floor = M.wood("DiningFloor", "oak", varnish=0.55, wear=0.5, grain_axis="X", planks=(1.4, 0.12))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("DCeil", "#ece6da", 0.9, 0.4, 0.1), col)
    wall("BackWall", col, paper, "y", Y1, X0, X1, 0, H)
    side = dict(c=-1.2, w=1.1, b=0.8, t=2.2)
    wall("LeftWall", col, paper, "x", X0, Y0, Y1, 0, H, openings=[(side["c"], side["w"], side["b"], side["t"])])
    window("DiningWindow", col, "x", X0, side["c"], side["w"], side["b"], side["t"], inward=1, panes=(2, 3))
    curtain("DiningCurtain", col, "x", X0, side["c"] + 0.72, 0.5, 0.05, 2.5, 1, color="#6f4a3a", sheer=0.15, folds=8)
    outdoor_backdrop(col, Vector((X0, side["c"], 0)), Vector((-1, 0, 0)), rng, distance=7.0, trees=8)
    wall("RightWall", col, paper, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, plain, "y", Y0, X0, X1, 0, H)
    trim = M.wood("DiningTrim", "painted_white", varnish=0.45, wear=0.3, scale=2.0, grain_axis="X")
    box("Skirting", X1 - X0, 0.022, 0.17, (0, face - 0.011, 0.085), trim, col, bevel=0.004)
    box("PictureRail", X1 - X0, 0.025, 0.04, (0, face - 0.0125, 2.18), trim, col, bevel=0.006, segments=3)

    sx = 0.15
    y, d = _sideboard(col, sx, face)
    back_y = face - 0.07                 # where the back row stands
    front_y = face - d + 0.13            # where the front row stands
    if opt(ctx, "runner", True):
        lace = M.fabric("LaceRunner", "#f1ece0", 2600, 0.85, 0.5, translucent=0.3, pattern="gingham",
                        pattern_color="#e2dccd", pattern_scale=90.0)
        box("LaceRunner", 1.25, d - 0.08, 0.0015, (sx, y - 0.02, TOP_Z + 0.0008), lace, col)
    surf = TOP_Z + 0.0016

    # ------------------------------------------------------------------ the frames
    metas = list(ctx.job.get("extra_prints", []))
    hero_meta = ctx.job["polaroid"]
    two_rows = opt(ctx, "rows", "2") == "2"
    # biggest frames at the back
    metas.sort(key=lambda m: -frame_size_m(m)[1])
    back = metas[:4] if two_rows else []
    front = metas[4:] if two_rows else metas[:4]
    lean = 13.0

    def row(items, y_at, x_span, prefix, hero_at=None):
        widths = [frame_size_m(m)[0] for m in items]
        total = sum(widths)
        gap = max(0.02, (x_span - total) / max(1, len(items) - 1)) if len(items) > 1 else 0.0
        x = sx - (total + gap * (len(items) - 1)) / 2
        out = []
        for j, m in enumerate(items):
            cx = x + widths[j] / 2
            # angled a little towards the room's centre, never quite straight
            yaw = math.radians(rng.uniform(-10, 10) - cx * 8)
            name = "HeroPrint" if m is hero_meta else f"{prefix}{j}"
            obj, c, n = place_card(m, name, col, Vector((cx, y_at + rng.uniform(-0.015, 0.015), surf)), yaw,
                                   "leaning", lean + rng.uniform(-2, 2))
            moved = keep_off_wall(obj, face, 0.006)
            out.append((m, (obj, c - Vector((0, moved, 0)), n)))
            x += widths[j] + gap
        return out

    if back:
        row(back, back_y, 1.35, "BackFrame")
    front = list(front)
    front.insert(len(front) // 2, hero_meta)
    placed = row(front, front_y, 1.25, "FrontFrame")
    hero, centre, normal = next(res for m, res in placed if m is hero_meta)

    # ------------------------------------------------------------------ around them
    lamp_on = switched_on(ctx, "lamp")
    _, ll = P.bankers_lamp("SideboardLamp", col, (sx + 0.76, face - 0.2, surf), math.radians(-30), on=lamp_on, power=8.0)
    if ll:
        lights.append(ll)
    if opt(ctx, "flowers", True):
        P.vase_with_stems("SideboardVase", col, (sx - 0.78, face - 0.18, surf), rng, color="#d8cdb6")
    P.candle("SideboardCandle", col, (sx + 0.62, front_y - 0.07, surf), 0.15, 0.016, lit=ctx.lights_on)
    P.ring_dish("SideboardDish", col, (sx - 0.66, front_y - 0.06, surf), math.radians(rng.uniform(0, 360)))
    if opt(ctx, "painting", True):
        frames = ctx.job.get("frame_photos", [])
        if frames:
            P.picture_frame("Painting", col, (sx, face - 0.025, 1.38), 0.0, frames[0], size=(0.7, 0.52), border=0.05,
                            wood_preset="walnut", lean=4, glass=False)
    if ctx.lights_on:
        _, fl = P.bankers_lamp("FloorLamp", col, (-1.7, -0.6, 1.0), 0.0, on=True, power=10.0)
        box("LampTable", 0.42, 0.42, 1.0, (-1.7, -0.6, 0.5), M.wood("LampTable", "walnut", 0.6, 0.4), col, bevel=0.006)
        if fl:
            lights.append(fl)

    w, h, dd = frame_size_m(hero_meta)
    view = Vector((0.1, -1.0, 0.0)).normalized()
    el = 9.0
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = h * max(0.35, abs(normal.dot(vd)))
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd,
        rack_point=Vector((sx + 0.2, back_y, surf + 0.15)), tilt_from=Vector((sx, face - 0.03, 1.5)),
        pan_from=centre + Vector((0.45, 0.1, 0.03)), reveal_target=Vector((sx, face - 0.2, surf + 0.2)),
        min_height=surf + 0.04,
    )
    ctx.sun_window = dict(centre=(X0, side["c"], (side["b"] + side["t"]) / 2), bottom=side["b"], top=side["t"],
                          along=(0, 1, 0), width=side["w"], panes=2, rows=3)
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((sx - 1.1, face - 1.4, surf - 0.1)), Vector((sx + 1.1, face, surf + 1.0)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
