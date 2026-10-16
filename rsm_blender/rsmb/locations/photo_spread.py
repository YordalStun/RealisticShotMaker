"""Photo spread: a shoebox of old photos tipped out across a living-room coffee table.

Built for several photos: prints overlap and fan out from the box, so the camera can drift from one to
the next or cut between them. Magnifying glass, a cup of tea and reading glasses lie among them; a sofa,
floor lamp and window sit softly in the background.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Euler, Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import add_subsurf, box, cylinder, lathe, link, mesh_object, set_smooth
from ..world import kelvin_rgb
from .common import (Ctx, Room, curtain, opt, outdoor_backdrop, place_card, scatter_prints, surface_z, switched_on,
                     wall, window)

TABLE_Z = 0.45


def _shoebox(col, at: Vector, rot_z: float, size=(0.33, 0.21, 0.12)):
    """An open cardboard shoebox (walls with real thickness) and its lid, knocked askew beside it."""
    sx, sy, sz = size
    card = M.paper("ShoeboxCard", "#b98f5f", rough=0.8, age=0.6)
    label = M.paper("ShoeboxLabel", "#ece3cc", rough=0.7, age=0.5)
    stripe = M.paper("ShoeboxStripe", "#8c2f2f", rough=0.6, age=0.4)
    root = bpy.data.objects.new("Shoebox", None)
    link(root, col)
    root.location = at
    root.rotation_euler = (0, 0, rot_z)
    t = 0.003
    parts = [
        ("Bottom", (sx, sy, t), (0, 0, t / 2)),
        ("Front", (sx, t, sz), (0, -sy / 2 + t / 2, sz / 2)),
        ("Back", (sx, t, sz), (0, sy / 2 - t / 2, sz / 2)),
        ("Left", (t, sy, sz), (-sx / 2 + t / 2, 0, sz / 2)),
        ("Right", (t, sy, sz), (sx / 2 - t / 2, 0, sz / 2)),
    ]
    for nm, dims, loc in parts:
        o = box(f"Shoebox{nm}", *dims, loc, card, col, bevel=0.0008, segments=2)
        o.parent = root
    lab = box("ShoeboxLabel", 0.1, 0.0008, 0.05, (0.06, -sy / 2 - 0.0004, sz * 0.55), label, col)
    lab.parent = root
    for dz in (-0.017, 0.017):  # the printed band across the label
        band = box("ShoeboxLabelBand", 0.1, 0.0004, 0.004, (0.06, -sy / 2 - 0.0009, sz * 0.55 + dz), stripe, col)
        band.parent = root
    # the lid was tossed onto the sofa behind (a soft shape in the background)
    lid = bpy.data.objects.new("ShoeboxLid", None)
    link(lid, col)
    lid.location = (0.45, 1.2, 0.412)
    lid.rotation_euler = (math.radians(-3), math.radians(4), math.radians(23))
    lsx, lsy, lsz = sx + 0.008, sy + 0.008, 0.035
    for nm, dims, loc in [("Top", (lsx, lsy, t), (0, 0, lsz - t / 2)), ("F", (lsx, t, lsz), (0, -lsy / 2, lsz / 2)),
                          ("B", (lsx, t, lsz), (0, lsy / 2, lsz / 2)), ("L", (t, lsy, lsz), (-lsx / 2, 0, lsz / 2)),
                          ("R", (t, lsy, lsz), (lsx / 2, 0, lsz / 2))]:
        o = box(f"ShoeboxLid{nm}", *dims, loc, card, col, bevel=0.0008, segments=2)
        o.parent = lid
    return root


def _magnifier(col, at: Vector, rot_z: float, z: float):
    """A reading magnifier lying on the table: brass rim, glass lens, turned wooden handle."""
    root = bpy.data.objects.new("Magnifier", None)
    link(root, col)
    root.location = (at.x, at.y, z)
    root.rotation_euler = (0, 0, rot_z)
    brass = M.metal("MagRim", "#b8904c", rough=0.25, smudge=0.6, tarnish=0.3)
    r = 0.045
    rim = lathe("MagRimRing", [(r - 0.004, 0.0), (r + 0.002, 0.0), (r + 0.002, 0.009), (r - 0.004, 0.009),
                               (r - 0.004, 0.0)], 64, brass, col)
    rim.parent = root
    lens = cylinder("MagLens", r - 0.002, 0.0045, (0, 0, 0.002), M.glass("MagGlass", "#f4f7f4", 0.0, 1.52, 0.25), col,
                    64)
    # a convex lens: bulge the caps so it really magnifies what's under it
    bm = bmesh.new()
    bm.from_mesh(lens.data)
    for v in bm.verts:
        d = math.hypot(v.co.x, v.co.y) / r
        bulge = 0.0035 * max(0.0, 1 - d * d)
        v.co.z += bulge if v.co.z > 0.002 else -bulge
    bm.to_mesh(lens.data)
    bm.free()
    add_subsurf(lens, 1, 2)
    set_smooth(lens)
    lens.parent = root
    wood = M.wood("MagHandle", "walnut", varnish=0.7, wear=0.4, grain_axis="X")
    ferrule = cylinder("MagFerrule", 0.008, 0.02, (r + 0.0, 0, 0.0045), brass, col, 24, rot=(0, math.radians(90), 0))
    ferrule.parent = root
    handle = lathe("MagHandleWood", [(0.0, 0.0), (0.008, 0.0), (0.0095, 0.03), (0.0085, 0.08), (0.0095, 0.1),
                                     (0.006, 0.108), (0.0, 0.11)], 32, wood, col)
    handle.rotation_euler = (0, math.radians(90), 0)
    handle.location = (r + 0.02, 0, 0.0045)
    handle.parent = root
    return root


def _sofa(col, centre: Vector, width=2.0, color="#6e5a48"):
    """A soft three-seat sofa: rounded base, back, arms and slumped cushions."""
    cloth = M.fabric("SofaCloth", color, threads_per_m=900, rough=0.9, sheen=0.7)
    x, y = centre.x, centre.y
    d = 0.9

    def soft(name, sx, sy, sz, loc, sub=2):
        o = box(name, sx, sy, sz, loc, cloth, col, bevel=min(sx, sy, sz) * 0.3, segments=4)
        return o

    soft("SofaBase", width, d, 0.24, (x, y, 0.16))
    soft("SofaBack", width, 0.22, 0.52, (x, y + d / 2 - 0.11, 0.54))
    for s in (-1, 1):
        soft("SofaArm", 0.2, d, 0.36, (x + s * (width / 2 - 0.1), y, 0.4))
    n = 3
    cw = (width - 0.42) / n
    for i in range(n):
        cx = x - (width - 0.42) / 2 + cw * (i + 0.5)
        c = soft(f"SeatCushion{i}", cw - 0.01, d - 0.24, 0.13, (cx, y - 0.1, 0.345))
        c.rotation_euler = (math.radians(-2), 0, 0)
        b = soft(f"BackCushion{i}", cw - 0.02, 0.18, 0.42, (cx, y + d / 2 - 0.3, 0.6))
        b.rotation_euler = (math.radians(-12), 0, 0)
    throw = M.fabric("Throw", "#b7a07a", threads_per_m=300, rough=0.95, sheen=0.5, pattern="stripe",
                     pattern_color="#7d3a2e", pattern_scale=6.0)
    t = box("SofaThrow", 0.55, 0.012, 0.5, (x + width / 2 - 0.45, y + d / 2 - 0.17, 0.62), throw, col, bevel=0.004)
    t.rotation_euler = (math.radians(-14), 0, math.radians(4))
    for k, (dx, colr) in enumerate(((-0.55, "#c89a4b"), (0.62, "#5b6b5a"))):
        p = soft(f"Cushion{k}", 0.42, 0.13, 0.42, (x + dx, y + 0.12, 0.62))
        p.data.materials.clear()
        p.data.materials.append(M.fabric(f"Cushion{k}", colr, threads_per_m=700, rough=0.9, sheen=0.8))
        p.rotation_euler = (math.radians(-18), math.radians(rng_tilt(k)), math.radians(8 - 16 * k))
    for leg_x in (-1, 1):
        for leg_y in (-1, 1):
            cylinder("SofaLeg", 0.018, 0.04, (x + leg_x * (width / 2 - 0.08), y + leg_y * (d / 2 - 0.08), 0.0),
                     M.wood("SofaLegs", "walnut", 0.6, 0.3), col, 16, radius2=0.012)


def rng_tilt(k: int) -> float:
    return (-6, 9)[k % 2]


def _floor_lamp(col, at: Vector, on: bool):
    """A brass floor lamp with a pleated fabric drum shade."""
    brass = M.metal("FloorLampBrass", "#b38d4c", rough=0.3, smudge=0.5, tarnish=0.4)
    lathe("FloorLampBase", [(0.0, 0.0), (0.16, 0.0), (0.16, 0.012), (0.12, 0.03), (0.02, 0.04), (0.0, 0.04)], 64,
          brass, col, loc=(at.x, at.y, 0.0))
    cylinder("FloorLampPole", 0.011, 1.42, (at.x, at.y, 0.04), brass, col, 24)
    shade = lathe("FloorLampShade", [(0.17, 1.28), (0.12, 1.55)], 72, M.lampshade("FloorShade", "#e8d8b6", 0.7), col,
                  loc=(at.x, at.y, 0.0))
    sol = shade.modifiers.new("Thick", "SOLIDIFY")
    sol.thickness = 0.003
    light = None
    if on:
        bulb = lathe("FloorLampBulb", [(0.0, 1.38), (0.03, 1.4), (0.032, 1.43), (0.0, 1.47)], 32,
                     M.frosted_bulb("FloorBulb", 2600.0, 30.0), col, loc=(at.x, at.y, 0.0))
        ld = bpy.data.lights.new("FloorLampLight", "POINT")
        ld.shadow_soft_size = 0.035
        ld.energy = 55.0
        ld.color = kelvin_rgb(2600.0)
        light = bpy.data.objects.new("FloorLampLight", ld)
        link(light, col)
        light.location = (at.x, at.y, 1.43)
    return light


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))

    X0, X1, Y0, Y1, H = -2.4, 2.4, -2.4, 2.1, 2.5
    walls = M.plaster("LoungeWalls", "#d9cbb0", rough=0.85, bump=0.8, stains=0.15)
    floor = M.wood("LoungeFloor", "oak", varnish=0.5, wear=0.5, dust=0.05, grain_axis="Y", planks=(1.2, 0.12))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("LCeil", "#efe9dd", 0.9, 0.4, 0.1),
        col)
    side = dict(c=0.0, w=1.3, b=0.7, t=2.15)
    wall("LeftWall", col, walls, "x", X0, Y0, Y1, 0, H, openings=[(side["c"], side["w"], side["b"], side["t"])])
    window("SpreadWindow", col, "x", X0, side["c"], side["w"], side["b"], side["t"], inward=1, panes=(2, 3))
    outdoor_backdrop(col, Vector((X0, side["c"], 0)), Vector((-1, 0, 0)), rng, distance=7.0, trees=3, hedge=True)
    if opt(ctx, "curtains", "open") == "half":
        curtain("SpreadCurtainA", col, "x", X0, side["c"] - side["w"] / 2 + 0.2, 0.6, 0.3, 2.4, 1, sheer=0.55)
        curtain("SpreadCurtainB", col, "x", X0, side["c"] + side["w"] / 2 - 0.2, 0.6, 0.3, 2.4, 1, sheer=0.55)
    else:
        curtain("SpreadCurtainA", col, "x", X0, side["c"] - side["w"] / 2 - 0.25, 0.45, 0.3, 2.4, 1, sheer=0.55)
        curtain("SpreadCurtainB", col, "x", X0, side["c"] + side["w"] / 2 + 0.25, 0.45, 0.3, 2.4, 1, sheer=0.55)
    wall("BackWall", col, walls, "y", Y1, X0, X1, 0, H)
    wall("RightWall", col, walls, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, walls, "y", Y0, X0, X1, 0, H)
    # skirting and a picture rail give the walls scale when they're out of focus
    trim = M.wood("Skirting", "painted_white", varnish=0.4, wear=0.3, grain_axis="X")
    box("Skirting", X1 - X0, 0.02, 0.14, (0, Y1 - 0.07, 0.07), trim, col, bevel=0.003)
    box("PictureRail", X1 - X0, 0.025, 0.035, (0, Y1 - 0.072, 2.05), trim, col, bevel=0.004)

    # rug, sofa, lamp, sideboard
    rug = M.fabric("Rug", "#8a4b3a", threads_per_m=500, rough=0.95, sheen=0.4, pattern="gingham",
                   pattern_color="#c9a66b", pattern_scale=3.0)
    box("Rug", 2.4, 1.7, 0.012, (0.0, 0.25, 0.006), rug, col, bevel=0.004)
    _sofa(col, Vector((0.0, 1.35, 0.0)))
    lights = []
    lamp_on = switched_on(ctx, "floor_lamp")
    ll = _floor_lamp(col, Vector((1.35, 1.6, 0.0)), lamp_on)
    if ll:
        lights.append(ll)
    side_wood = M.wood("Sideboard", "walnut", varnish=0.6, wear=0.4, grain_axis="X")
    box("Sideboard", 1.4, 0.45, 0.78, (X1 - 0.25, 0.4, 0.39), side_wood, col, bevel=0.006)
    box("SideboardTop", 0.47, 1.44, 0.025, (X1 - 0.25, 0.4, 0.79), side_wood, col, bevel=0.004, rot=(0, 0, 0))
    P.potted_plant("SpreadPlant", col, (X1 - 0.25, 0.85, 0.80), rng)
    P.picture_frame("SpreadFrame", col, (X1 - 0.3, 0.1, 0.80), math.radians(-100),
                    (ctx.job.get("frame_photos") or [None])[0])

    # ------------------------------------------------------------------ coffee table
    oak = M.wood("CoffeeTable", "oak", varnish=0.55, wear=0.6, dust=0.05, grain_axis="X")
    box("CoffeeTop", 1.15, 0.62, 0.035, (0.0, 0.2, TABLE_Z - 0.0175), oak, col, bevel=0.006)
    for lx in (-0.5, 0.5):
        for ly in (-0.24, 0.24):
            box("CoffeeLeg", 0.045, 0.045, TABLE_Z - 0.035, (lx, 0.2 + ly, (TABLE_Z - 0.035) / 2), oak, col,
                bevel=0.003)
    box("CoffeeShelf", 1.05, 0.52, 0.02, (0.0, 0.2, 0.1), oak, col, bevel=0.004)
    P.book_stack("ShelfBooks", col, (-0.25, 0.2, 0.11), 3, rng, rot_z=math.radians(6))
    surf = TABLE_Z

    # ------------------------------------------------------------------ the box and the spilled prints
    meta = ctx.job["polaroid"]
    extras = list(ctx.job.get("extra_prints", []))
    card_h = meta["card_mm"][1] / 1000.0
    placement = s.get("placement", "flat")
    if ctx.spec["camera"]["move"] == "top_down" and placement == "leaning":
        placement = "flat"
    box_at = Vector((0.24, 0.36, surf))
    box_rot = math.radians(-8)
    if opt(ctx, "shoebox", True):
        _shoebox(col, box_at, box_rot)
        # a few prints still standing in the box (not visited by multi-photo moves: you only see their tops)
        inside = extras[-3:] if len(extras) > 6 else []
        extras = extras[:-3] if inside else extras
        for i, m in enumerate(inside):
            off = Vector((rng.uniform(-0.08, 0.08), 0.06 - i * 0.035, surf + 0.004))
            off.rotate(Euler((0, 0, box_rot)))
            place_card(m, f"Boxed{i}", col, Vector((box_at.x + off.x, box_at.y + off.y, surf + 0.004)),
                       box_rot + math.radians(rng.uniform(-6, 6)), "leaning", lean_deg=rng.uniform(8, 20),
                       register=False)
    spread = opt(ctx, "spread", "lots")
    n_loose = len(extras) if spread == "lots" else min(len(extras), 5)
    anchor = Vector((-0.06, 0.12, surf))
    if placement == "leaning":
        # propped against the front of the box, the others spilled around it
        lean = 15.0
        front_y = box_at.y - 0.105
        hero_at = Vector((box_at.x - 0.04, front_y - card_h * math.sin(math.radians(lean)) - 0.006, surf))
        scatter_prints(extras[:n_loose], col, Vector((anchor.x, anchor.y - 0.02, surf)), 0.3, rng, surf,
                       prefix="Loose", avoid=Vector((hero_at.x, hero_at.y, surf)), avoid_r=0.1)
        hero, centre, normal = place_card(meta, "HeroPrint", col, hero_at, box_rot + math.radians(rng.uniform(-3, 3)),
                                          "leaning", lean)
        anchor = hero_at
        el = 9.0
    else:
        # the prints fell out first; the hero lies on top of them, a little apart
        base = surf
        if placement == "pile":
            pile = extras[: max(3, n_loose // 2)]
            scatter_prints(pile, col, anchor, 0.035, rng, surf, prefix="Pile", stack=True)
            base = surf + len(pile) * 0.0013
            rest = extras[len(pile):n_loose]
        else:
            rest = extras[:n_loose]
        scatter_prints(rest, col, Vector((anchor.x + 0.03, anchor.y + 0.03, surf)), 0.32, rng, surf, prefix="Loose",
                       avoid=Vector((anchor.x, anchor.y, surf)), avoid_r=0.07)
        hero, centre, normal = place_card(meta, "HeroPrint", col, Vector((anchor.x, anchor.y, base)),
                                          math.radians(rng.uniform(-14, 14)), "flat")
        el = 38.0

    # ------------------------------------------------------------------ the things lying among them
    if opt(ctx, "magnifier", True):
        mx, my = anchor.x + 0.22, anchor.y - 0.14
        z = surface_z(mx, my, surf + 0.02) or surf
        _magnifier(col, Vector((mx, my, 0)), math.radians(rng.uniform(-40, -10)), z)
    if opt(ctx, "tea", True):
        P.cup_and_saucer("SpreadTea", col, (-0.42, 0.34, surf), math.radians(rng.uniform(0, 360)))
    if clutter > 0.3:
        P.reading_glasses("SpreadGlasses", col, (-0.36, 0.0, surf), math.radians(rng.uniform(-30, 30)))
    if clutter > 0.6:
        pen = P.pencil("SpreadPencil", col, rng=rng)
        pen.location = (0.4, 0.04, surf + 0.0038)
        pen.rotation_euler = (0, math.radians(90), math.radians(rng.uniform(60, 120)))
        P.envelope("SpreadEnvelope", col, (0.47, -0.02, surf), math.radians(rng.uniform(-20, 20)))

    view = Vector((0.15, -1.0, 0.0)).normalized()
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))
    ctx.sun_window = dict(centre=(X0, side["c"], (side["b"] + side["t"]) / 2), bottom=side["b"], top=side["t"],
                          along=(0, 1, 0), width=side["w"], panes=2, rows=3)
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd,
        rack_point=Vector((box_at.x, box_at.y, surf + 0.1)), tilt_from=Vector((X0 + 0.1, side["c"], 1.6)),
        pan_from=Vector((-0.42, 0.34, surf + 0.05)), reveal_target=Vector((0.0, 0.5, surf + 0.25)),
        min_height=surf + 0.02,
    )
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-1.2, -0.6, surf)), Vector((1.0, 1.0, surf + 1.2)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
