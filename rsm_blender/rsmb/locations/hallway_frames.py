"""Hallway wall of family photos: framed photos of every size and style hung in a loose gallery along a hallway,
golden light raking along them from the window at the end. Dado rail, console table, runner on the floorboards.

Built for several photos: the camera can track along the frames, look past one onto another, or tilt down them.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder, link
from .common import (Ctx, Room, curtain, frame_size_m, hang_frame, opt, outdoor_backdrop, place_card, switched_on,
                     wall, wallpaper, window)

DADO_Z = 0.92


def _rows(metas, row_count, centre_z, rng, gap=(0.06, 0.1)):
    """Lay frames out in rows (centres aligned per row, the way people hang a gallery wall).
    Returns [(row_index, meta, x, z)], with the row heights worked out from the frames in them."""
    rows = [[] for _ in range(row_count)]
    for i, m in enumerate(metas):
        rows[i % row_count].append(m)
    placed = []
    heights = [max(frame_size_m(m)[1] for m in r) if r else 0.0 for r in rows]
    # middle row on centre_z, the others stacked above and below with a hand's width between
    mid = row_count // 2
    zs = [0.0] * row_count
    zs[mid] = centre_z
    for k in range(mid - 1, -1, -1):
        zs[k] = zs[k + 1] + heights[k + 1] / 2 + heights[k] / 2 + rng.uniform(*gap)
    for k in range(mid + 1, row_count):
        zs[k] = zs[k - 1] - heights[k - 1] / 2 - heights[k] / 2 - rng.uniform(*gap)
    for k, r in enumerate(rows):
        widths = [frame_size_m(m)[0] for m in r]
        gaps = [rng.uniform(*gap) for _ in r[:-1]]
        total = sum(widths) + sum(gaps)
        x = -total / 2 + rng.uniform(-0.04, 0.04)
        for j, m in enumerate(r):
            placed.append((k, m, x + widths[j] / 2, zs[k] + rng.uniform(-0.012, 0.012)))
            x += widths[j] + (gaps[j] if j < len(gaps) else 0.0)
    return placed


def _radiator(col, x, face, width=0.8):
    paint = M.plastic("RadiatorPaint", "#ece8de", 0.35, coat=0.2)
    n = int(width / 0.06)
    for i in range(n):
        cx = x - width / 2 + (i + 0.5) * width / n
        box(f"RadiatorFin{i}", 0.045, 0.07, 0.56, (cx, face - 0.06, 0.45), paint, col, bevel=0.012, segments=3)
    for z in (0.2, 0.7):
        cylinder("RadiatorPipe", 0.016, width, (x, face - 0.06, z), paint, col, 24, rot=(0, math.radians(90), 0))
    cylinder("RadiatorValve", 0.012, 0.15, (x - width / 2 - 0.04, face - 0.06, 0.1),
             M.metal("Valve", "#c9a25e", 0.3, 0.4, 0.4), col, 24)


def _console(col, x, face, rng, lamp_on, lights, hero_on_top=False):
    wood = M.wood("ConsoleWood", "walnut", varnish=0.65, wear=0.35, grain_axis="X")
    top_z, w, d = 0.8, 1.0, 0.32
    y = face - d / 2 - 0.01
    box("ConsoleTop", w, d, 0.03, (x, y, top_z - 0.015), wood, col, bevel=0.005, segments=3)
    box("ConsoleApron", w - 0.06, d - 0.04, 0.09, (x, y + 0.01, top_z - 0.075), wood, col, bevel=0.003)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cylinder("ConsoleLeg", 0.018, top_z - 0.03, (x + sx * (w / 2 - 0.05), y + sy * (d / 2 - 0.05), (top_z - 0.03) / 2),
                     wood, col, 16, radius2=0.012)
    box("ConsoleShelf", w - 0.08, d - 0.06, 0.02, (x, y, 0.16), wood, col, bevel=0.003)
    knob = M.metal("ConsoleKnob", "#b08d57", 0.3, 0.3, 0.4)
    cylinder("ConsoleKnob", 0.009, 0.014, (x, y - d / 2 + 0.015, top_z - 0.075), knob, col, 16,
             rot=(math.radians(90), 0, 0))
    # with a photo standing in the middle, the lamp, bowl and post move out to the ends
    lamp_x = x + (0.36 if hero_on_top else w / 2 - 0.2)
    bowl_x = x - (0.37 if hero_on_top else 0.3)
    post_x = x + (0.22 if hero_on_top else -0.02)
    lamp, ll = P.bankers_lamp("HallLamp", col, (lamp_x, y + 0.04, top_z), math.radians(-20), on=lamp_on, power=7.0)
    if ll:
        lights.append(ll)
    P.fruit_bowl("KeysBowl", col, (bowl_x, y - 0.03, top_z), rng, color="#3f5d6b")
    # post waiting on the table
    P.envelope("HallPost1", col, (post_x, y - 0.07, top_z + 0.0005), math.radians(rng.uniform(-15, 15)))
    P.envelope("HallPost2", col, (post_x + 0.03, y - 0.06, top_z + 0.0012), math.radians(rng.uniform(-25, 5)),
               color="#d9cdb2")
    P.book_stack("HallBooks", col, (x, y + 0.02, 0.17), 2, rng, rot_z=math.radians(90))
    return top_z, y


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    lights = []
    X0, X1, Y1, H = -3.2, 3.2, 0.6, 2.6
    Y0 = Y1 - 2.4
    face = Y1 - 0.06
    wall_kind = opt(ctx, "wall", "paper")
    plaster = M.plaster("HallPlaster", "#e4dccb", 0.88, 0.8, 0.15)
    if wall_kind == "paper":
        upper = wallpaper("HallPaper", "#cdbf9f", "#b39e78", 7.0)
    elif wall_kind == "panel":
        upper = M.plaster("HallUpper", "#d9cfb9", 0.88, 0.7, 0.12)
    else:
        upper = M.plaster("HallPaint", "#b7b9a3", 0.85, 0.7, 0.2)
    floor = M.wood("HallFloor", "oak", varnish=0.55, wear=0.55, grain_axis="X", planks=(1.3, 0.13))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("HallCeil", "#efeae0", 0.9, 0.4, 0.1), col)
    door = opt(ctx, "door", True)
    door_x = 2.15
    wall("PhotoWall", col, upper, "y", Y1, X0, X1, 0, H, openings=[(door_x, 0.86, 0.0, 2.04)] if door else [])
    end_win = dict(c=Y1 - 1.05, w=0.9, b=0.85, t=2.15)
    wall("EndWall", col, plaster, "x", X0, Y0, Y1, 0, H, openings=[(end_win["c"], end_win["w"], end_win["b"], end_win["t"])])
    window("HallWindow", col, "x", X0, end_win["c"], end_win["w"], end_win["b"], end_win["t"], inward=1, panes=(2, 3))
    curtain("HallCurtain", col, "x", X0, end_win["c"] + 0.62, 0.42, 0.05, 2.45, 1, color="#c9b48a", sheer=0.4, folds=7)
    # open ground beyond the end window, so low evening sun can reach all the way down the hall
    outdoor_backdrop(col, Vector((X0, end_win["c"], 0)), Vector((-1, 0, 0)), rng, distance=12.0, trees=0, hedge=False)
    wall("FarWall", col, plaster, "x", X1, Y0, Y1, 0, H)
    wall("BackWall", col, plaster, "y", Y0, X0, X1, 0, H)

    # ------------------------------------------------------------------ joinery
    trim = M.wood("HallTrim", "painted_white", varnish=0.45, wear=0.3, scale=2.0, grain_axis="X")
    spans = [(X0, door_x - 0.5), (door_x + 0.5, X1)] if door else [(X0, X1)]
    for i, (a, b) in enumerate(spans):
        box(f"Skirting{i}", b - a, 0.022, 0.16, ((a + b) / 2, face - 0.011, 0.08), trim, col, bevel=0.004)
        box(f"DadoRail{i}", b - a, 0.028, 0.045, ((a + b) / 2, face - 0.014, DADO_Z), trim, col, bevel=0.008, segments=4)
        if wall_kind == "panel":
            panel = M.wood("HallPanel", "painted_white", varnish=0.4, wear=0.25, scale=2.0, grain_axis="Z")
            n = int((b - a) / 0.11)
            for k in range(n):
                box(f"Panel{i}_{k}", 0.105, 0.012, DADO_Z - 0.18, (a + (k + 0.5) * (b - a) / n, face - 0.006,
                                                                  0.16 + (DADO_Z - 0.18) / 2), panel, col, bevel=0.002)
    if door:
        for sx in (-1, 1):
            box("Architrave", 0.07, 0.025, 2.11, (door_x + sx * 0.465, face - 0.012, 1.055), trim, col, bevel=0.006)
        box("ArchitraveTop", 1.0, 0.025, 0.07, (door_x, face - 0.012, 2.075), trim, col, bevel=0.006)
        # the room beyond: dim, a glimpse of a chair and a lamp
        box("NextFloor", 1.6, 2.4, 0.05, (door_x, Y1 + 1.2, -0.024), floor, col)
        box("NextBackWall", 2.4, 0.1, H, (door_x, Y1 + 2.4, H / 2), upper, col)
        box("NextSideA", 0.1, 2.4, H, (door_x - 0.8, Y1 + 1.2, H / 2), plaster, col)
        box("NextSideB", 0.1, 2.4, H, (door_x + 0.8, Y1 + 1.2, H / 2), plaster, col)
        box("NextCeil", 1.6, 2.4, 0.05, (door_x, Y1 + 1.2, H + 0.02), plaster, col)
        box("NextChair", 0.5, 0.5, 0.45, (door_x - 0.2, Y1 + 1.6, 0.225), M.fabric("NextChair", "#5a3d36", 1200, 0.8, 0.6),
            col, bevel=0.03)
        if ctx.lights_on:
            _, nl = P.bankers_lamp("NextLamp", col, (door_x + 0.4, Y1 + 2.1, 0.0), 0.0, on=True, power=10.0)
            if nl:
                lights.append(nl)
        box("LightSwitch", 0.086, 0.01, 0.086, (door_x - 0.62, face - 0.005, 1.2),
            M.plastic("Switch", "#efece4", 0.3, 0.2), col, bevel=0.003)
    # a runner down the hall
    box("Runner", 5.2, 0.72, 0.008, (-0.4, face - 0.62, 0.004), M.fabric("HallRunner", "#7a3a2c", 900, 0.9, 0.5,
                                                                         pattern="stripe", pattern_color="#c9a66b",
                                                                         pattern_scale=3.0), col)
    if opt(ctx, "radiator", True):
        _radiator(col, -1.75, face)

    # ------------------------------------------------------------------ the frames
    placement = s.get("placement", "wall")
    metas = list(ctx.job.get("extra_prints", []))
    if opt(ctx, "how_many", "lots") == "some":
        metas = metas[:4]
    hero_meta = ctx.job["polaroid"]
    lamp_on = switched_on(ctx, "lamp")
    console = opt(ctx, "console", True) or placement == "standing"
    console_x = 0.0 if placement == "standing" else 1.05
    top_z = None
    if console:
        top_z, cy = _console(col, console_x, face, rng, lamp_on, lights, hero_on_top=placement == "standing")

    if placement == "standing":
        # the hero stands on the console; the gallery hangs above it
        hero, centre, normal = place_card(hero_meta, "HeroPrint", col, Vector((console_x - 0.02, cy - 0.04, top_z)),
                                          math.radians(rng.uniform(-8, 4)), "leaning", 14.0)
        gallery = metas
        rows = 2 if len(gallery) > 3 else 1
        lay = _rows(gallery, rows, 0.0, rng)
        lowest = min(z - frame_size_m(m)[1] / 2 for _, m, _, z in lay)
        lift = top_z + 0.62 - lowest
        for i, (k, m, x, z) in enumerate(lay):
            hang_frame(m, f"WallFrame{i}", col, Vector((x, 0, z + lift)), face, rng.uniform(-1.4, 1.4),
                       rng.uniform(0.8, 2.2))
        view = Vector((0.15, -1.0, 0.0)).normalized()
        el = 12.0
    else:
        # hero halfway along the middle row, at eye level
        n_rows = 3 if len(metas) >= 6 else (2 if len(metas) >= 2 else 1)
        mid = n_rows // 2
        rows = [metas[i::n_rows] for i in range(n_rows)]
        rows[mid].insert(len(rows[mid]) // 2, hero_meta)
        # lay out each row directly
        heights = [max(frame_size_m(m)[1] for m in r) for r in rows]
        zs = [0.0] * n_rows
        zs[mid] = 1.52
        for k in range(mid - 1, -1, -1):
            zs[k] = zs[k + 1] + heights[k + 1] / 2 + heights[k] / 2 + rng.uniform(0.06, 0.1)
        for k in range(mid + 1, n_rows):
            zs[k] = zs[k - 1] - heights[k - 1] / 2 - heights[k] / 2 - rng.uniform(0.06, 0.1)
        floor_z = DADO_Z + 0.12
        low = zs[-1] - heights[-1] / 2
        if low < floor_z:
            zs = [z + (floor_z - low) for z in zs]
        hero = centre = normal = None
        for k, r in enumerate(rows):
            widths = [frame_size_m(m)[0] for m in r]
            gaps = [rng.uniform(0.06, 0.1) for _ in r[:-1]]
            total = sum(widths) + sum(gaps)
            x = -total / 2 + rng.uniform(-0.03, 0.03) - 0.35
            for j, m in enumerate(r):
                cx = x + widths[j] / 2
                cz = zs[k] + rng.uniform(-0.01, 0.01)
                if m is hero_meta:
                    hero, centre, normal = hang_frame(m, "HeroPrint", col, Vector((cx, 0, cz)), face,
                                                      rng.uniform(-0.6, 0.6), 1.5)
                else:
                    hang_frame(m, f"WallFrame{k}_{j}", col, Vector((cx, 0, cz)), face, rng.uniform(-1.6, 1.6),
                               rng.uniform(0.8, 2.2))
                x += widths[j] + (gaps[j] if j < len(gaps) else 0.0)
        view = Vector((0.18, -1.0, 0.0)).normalized()
        el = 2.0

    # an old-fashioned pendant down the hall when the lights are on
    if ctx.lights_on:
        cylinder("PendantFlex", 0.003, 0.5, (-0.4, face - 0.7, H - 0.25), M.plastic("Flex", "#2a2622", 0.4), col, 8)
        shade = cylinder("PendantShade", 0.16, 0.16, (-0.4, face - 0.7, H - 0.58),
                         M.lampshade("PendantShade", "#e8d7b4", 0.7), col, 48, radius2=0.09)
        ld = bpy.data.lights.new("PendantLight", "POINT")
        ld.energy = 35.0
        ld.shadow_soft_size = 0.05
        ld.color = (1.0, 0.78, 0.55)
        pl = bpy.data.objects.new("PendantLight", ld)
        link(pl, col)
        pl.location = (-0.4, face - 0.7, H - 0.62)
        lights.append(pl)

    w, h, d = frame_size_m(hero_meta)
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = h * max(0.35, abs(normal.dot(vd)))
    top = max(o.matrix_world.translation.z + frame_size_m(hero_meta)[1]
              for o in bpy.data.objects if o.name.startswith(("WallFrame", "HeroPrint")))
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd,
        rack_point=Vector((door_x, Y1 + 1.6, 1.0)) if door else centre + Vector((0.6, -0.3, -0.5)),
        tilt_from=Vector((centre.x, face, min(H - 0.15, top))), pan_from=centre + Vector((-0.5, 0, 0.0)),
        reveal_target=Vector((centre.x + 0.2, face, centre.z)), min_height=0.4,
    )
    ctx.sun_window = dict(centre=(X0, end_win["c"], (end_win["b"] + end_win["t"]) / 2), bottom=end_win["b"],
                          top=end_win["t"], along=(0, 1, 0), width=end_win["w"], panes=2, rows=3)
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((centre.x - 1.2, face - 1.4, 0.8)), Vector((centre.x + 1.2, face, 2.3)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
