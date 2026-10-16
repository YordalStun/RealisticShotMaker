"""Living-room mantelpiece: clock, candles, frames, a gilt mirror and the glow of the fire below."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder, link
from ..world import kelvin_rgb
from .common import (Ctx, Room, animate_flicker, curtain, fairy_lights, opt, outdoor_backdrop, place_card,
                     switched_on, wall, wallpaper, window)

SHELF_Z = 1.22


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))
    fps = float(ctx.quality["fps"])
    fs, fe = int(ctx.quality["frame_start"]), int(ctx.quality["frame_end"])

    X0, X1, Y0, Y1, H = -2.4, 2.4, -3.0, 0.3, 2.7
    paper = wallpaper("LoungePaper", "#8f9c86", "#7b8a72", 6.0)
    floor = M.wood("LoungeFloor", "oak", varnish=0.5, wear=0.5, grain_axis="X", planks=(1.4, 0.12))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("LCeil", "#ebe5d8", 0.9, 0.4, 0.1), col)
    wall("ChimneyWall", col, paper, "y", Y1, X0, X1, 0, H)
    side = dict(c=-1.6, w=1.1, b=0.75, t=2.2)
    wall("LeftWall", col, paper, "x", X0, Y0, Y1, 0, H, openings=[(side["c"], side["w"], side["b"], side["t"])])
    window("LoungeWindow", col, "x", X0, side["c"], side["w"], side["b"], side["t"], inward=1, panes=(2, 3))
    curtain("LoungeCurtain", col, "x", X0, side["c"] + 0.7, 0.55, 0.05, 2.5, 1, color="#7a3b33", sheer=0.2, folds=8)
    wall("RightWall", col, paper, "x", X1, Y0, Y1, 0, H)
    wall("BackWall", col, paper, "y", Y0, X0, X1, 0, H)
    outdoor_backdrop(col, Vector((X0, side["c"], 0)), Vector((-1, 0, 0)), rng, distance=7.0, trees=8)

    # ------------------------------------------------------------------ fireplace
    paint = M.wood("Surround", "painted_white", varnish=0.4, wear=0.4, scale=2.0, grain_axis="Z")
    marble = M.ceramic("Marble", "#d9d4c9", rough=0.12, speckle=0.6, crazing=0.0)
    soot = M.plaster("Soot", "#1a1512", rough=0.95, bump=1.0, stains=0.6)
    fy = Y1 - 0.02
    box("PilasterL", 0.22, 0.12, SHELF_Z - 0.06, (-0.62, fy - 0.06, (SHELF_Z - 0.06) / 2), paint, col, bevel=0.01, segments=4)
    box("PilasterR", 0.22, 0.12, SHELF_Z - 0.06, (0.62, fy - 0.06, (SHELF_Z - 0.06) / 2), paint, col, bevel=0.01, segments=4)
    box("Frieze", 1.46, 0.1, 0.24, (0, fy - 0.05, SHELF_Z - 0.18), paint, col, bevel=0.01, segments=4)
    box("Shelf", 1.62, 0.24, 0.05, (0, fy - 0.12, SHELF_Z - 0.025), paint, col, bevel=0.012, segments=5)
    box("FireboxBack", 1.02, 0.3, SHELF_Z - 0.3, (0, fy + 0.1, (SHELF_Z - 0.3) / 2), soot, col)
    box("Hearth", 1.7, 0.5, 0.05, (0, fy - 0.3, 0.025), marble, col, bevel=0.006)
    # embers and logs in the grate
    logs = M.wood("Logs", "aged_beam", varnish=0.0, wear=1.0, scale=3.0, grain_axis="X")
    for i in range(3):
        lg = cylinder(f"Log{i}", 0.055, 0.55, (rng.uniform(-0.1, 0.1), fy + 0.02 - i * 0.04, 0.12 + i * 0.05), logs, col, 24)
        lg.rotation_euler = (0, math.radians(90), math.radians(rng.uniform(-14, 14)))
    fire_state = opt(ctx, "fire", "lit")
    ember_mat = M.emitter("Embers", 1500.0, 8.0 if fire_state != "out" else 0.0)
    for i in range(14 if fire_state != "out" else 6):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rng.uniform(0.012, 0.03),
                                              location=(rng.uniform(-0.28, 0.28), fy + rng.uniform(-0.05, 0.08), 0.08))
        e = bpy.context.object
        for c_ in e.users_collection:
            c_.objects.unlink(e)
        col.objects.link(e)
        e.data.materials.append(ember_mat)
    lights = []
    fire_on = fire_state != "out"
    if fire_on:
        ld = bpy.data.lights.new("FireGlow", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = 0.7, 0.25
        ld.energy = 140 if fire_state == "lit" else 35
        ld.color = kelvin_rgb(1700 if fire_state == "lit" else 1300)
        fire = bpy.data.objects.new("FireGlow", ld)
        link(fire, col)
        fire.location = (0, fy - 0.08, 0.25)
        fire.rotation_euler = (math.radians(-60), 0, 0)
        lights.append(fire)
        animate_flicker(fire, ld.energy, 0.35 if fire_state == "lit" else 0.1, fps, fs, fe, seed=11,
                        speed=1.4 if fire_state == "lit" else 0.3)

    # gilt mirror above the mantel
    gilt = M.metal("Gilt", "#c9a356", rough=0.28, smudge=0.5, tarnish=0.55)
    mirror_mat = M.metal("Mirror", "#e8e8e6", rough=0.02, smudge=0.25, tarnish=0.05)
    mz = SHELF_Z + 0.55
    box("MirrorGlass", 0.9, 0.01, 0.75, (0, fy - 0.02, mz), mirror_mat, col)
    for i, (sx, sz, c) in enumerate(((1.0, 0.07, (0, mz + 0.41)), (1.0, 0.07, (0, mz - 0.41)),
                                     (0.07, 0.89, (-0.485, mz)), (0.07, 0.89, (0.485, mz)))):
        box(f"MirrorFrame{i}", sx, 0.04, sz, (c[0], fy - 0.035, c[1]), gilt, col, bevel=0.012, segments=4)

    surf = SHELF_Z
    meta = ctx.job["polaroid"]
    card_h = meta["card_mm"][1] / 1000.0
    # the camera looks along the mantel so the clock, candles and frames recede into bokeh behind the print;
    # the print is turned to face the camera and leans against a small frame standing behind it
    view = Vector((-0.86, -0.5, 0.0)).normalized()
    yaw = math.atan2(view.x, -view.y)  # card normal (sin yaw, -cos yaw) faces the camera
    lean = 14.0
    anchor = Vector((-0.42, fy - 0.15, surf))
    back = Vector((-view.x, -view.y, 0.0))
    support = anchor + back * (card_h * math.sin(math.radians(lean)) + 0.012)
    frames = ctx.job.get("frame_photos", [])
    P.picture_frame("SupportFrame", col, tuple(support), yaw, frames[1] if len(frames) > 1 else None, size=(0.1, 0.13),
                    wood_preset="walnut", lean=6)
    hero, centre, normal = place_card(meta, "HeroPrint", col, anchor, yaw + math.radians(rng.uniform(-3, 3)),
                                      "leaning", lean)
    el = 5.0
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))

    P.carriage_clock("CarriageClock", col, (-0.05, fy - 0.13, surf), math.radians(-20))
    rack_point = Vector((-0.05, fy - 0.13, surf + 0.07))
    lit = switched_on(ctx, "candles")
    for i, (x, h) in enumerate(((0.22, 0.16), (0.32, 0.12), (0.4, 0.2))):
        _, cl = P.candle(f"Candle{i}", col, (x, fy - 0.12 + 0.02 * i, surf), h, 0.017, lit=lit)
        if cl:
            lights.append(cl)
            animate_flicker(cl, cl.data.energy, 0.25, fps, fs, fe, seed=20 + i, speed=2.2)
    if clutter > 0.3 and frames:
        P.picture_frame("MantelFrame", col, (0.55, fy - 0.09, surf), math.radians(-10), frames[0], size=(0.13, 0.17),
                        wood_preset="mahogany", lean=8)
    if clutter > 0.55:
        P.vase_with_stems("MantelVase", col, (0.72, fy - 0.12, surf), rng, color="#d9cfb8")
    if opt(ctx, "christmas", False):
        front = fy - 0.245
        pts = [Vector((x, front, surf - 0.02)) for x in (-0.8, -0.4, 0.0, 0.4, 0.8)]
        fairy_lights(col, pts, 60, rng, name="MantelFairyLights")
        garland_mat = M.fabric("Garland", "#1f3a22", threads_per_m=200, rough=0.9, sheen=0.8)
        for i in range(4):
            a, b2 = pts[i], pts[i + 1]
            mid = (a + b2) / 2 - Vector((0, 0, 0.05))
            curve = bpy.data.curves.new(f"Garland{i}", "CURVE")
            curve.dimensions = "3D"
            sp = curve.splines.new("BEZIER")
            sp.bezier_points.add(2)
            for bp, co in zip(sp.bezier_points, (a, mid, b2)):
                bp.co = co
                bp.handle_left_type = bp.handle_right_type = "AUTO"
            curve.bevel_depth = 0.022
            curve.bevel_resolution = 4
            g = bpy.data.objects.new(f"Garland{i}", curve)
            link(g, col)
            g.data.materials.append(garland_mat)
            disp = g.modifiers.new("Needles", "DISPLACE")
            tex = bpy.data.textures.new(f"Needles{i}", "CLOUDS")
            tex.noise_scale = 0.01
            disp.texture = tex
            disp.strength = 0.012
        for i, x in enumerate((0.48, 0.62, 0.78)):
            card = box(f"XmasCard{i}", 0.1, 0.002, 0.14, (x, fy - 0.06 - i * 0.01, surf + 0.07),
                       M.paper(f"XmasCard{i}", rng.choice(["#b23a2e", "#2f5a3a", "#efe8d8"]), 0.6, 0.1), col)
            card.rotation_euler = (math.radians(-8), 0, math.radians(rng.uniform(-20, 20)))
    if ctx.lights_on:
        # a standard lamp in the corner of the room
        _, fl = P.bankers_lamp("CornerLamp", col, (1.9, -0.4, 1.05), 0.0, on=True, power=12.0)
        if fl:
            lights.append(fl)
        box("SideTable", 0.45, 0.45, 1.05, (1.9, -0.4, 0.525), M.wood("SideTable", "walnut", 0.6, 0.4), col, bevel=0.006)

    ctx.sun_window = dict(centre=(X0, side["c"], (side["b"] + side["t"]) / 2), bottom=side["b"], top=side["t"],
                          along=(0, 1, 0), width=side["w"], panes=2, rows=3)
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd, rack_point=rack_point,
        tilt_from=Vector((0, fy - 0.03, mz)), pan_from=Vector((-0.25, fy - 0.12, surf + 0.07)),
        reveal_target=Vector((0.1, fy - 0.15, surf + 0.1)), min_height=surf + 0.012,
    )
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-0.9, fy - 1.2, surf - 0.2)), Vector((0.9, fy, surf + 0.8)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
