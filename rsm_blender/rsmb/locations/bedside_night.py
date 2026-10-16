"""Bedside table at night: warm lamp, alarm clock, glass of water; moonlight and street lights outside."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder, lathe, link
from ..world import kelvin_rgb
from .common import (Ctx, Room, animate_flicker, curtain, outdoor_backdrop, place_card, scatter_prints, wall,
                     wallpaper, window)

TOP_Z = 0.62


def table_lamp(col, loc, on=True, power=14.0, kelvin=2600.0):
    root = bpy.data.objects.new("TableLamp", None)
    link(root, col)
    root.location = loc
    glaze = M.ceramic("LampBase", "#c7b48f", rough=0.15, speckle=0.3, crazing=0.4)
    base = lathe("LampBody", [(0.0, 0.0), (0.06, 0.0), (0.065, 0.01), (0.09, 0.09), (0.085, 0.16), (0.04, 0.22),
                              (0.018, 0.24), (0.012, 0.27), (0.0, 0.27)], 72, glaze, col)
    base.parent = root
    stem = cylinder("LampStem", 0.006, 0.12, (0, 0, 0.27), M.metal("LampBrass", "#c09a52", 0.25, 0.4, 0.3), col, 16)
    stem.parent = root
    shade = lathe("LampShade", [(0.11, 0.0), (0.09, 0.2)], 96, M.lampshade("Shade", "#efe2c4", 0.75), col,
                  loc=(0, 0, 0.3), smooth=True)
    shade.modifiers.new("Thick", "SOLIDIFY").thickness = 0.0015
    shade.parent = root
    light = None
    if on:
        bulb = lathe("LampBulb", [(0.0, 0.0), (0.012, 0.004), (0.028, 0.03), (0.026, 0.055), (0.0, 0.07)], 32,
                     M.frosted_bulb("LampBulb", kelvin, 22.0), col, loc=(0, 0, 0.36))
        bulb.parent = root
        ld = bpy.data.lights.new("LampLight", "POINT")
        ld.energy = power
        ld.shadow_soft_size = 0.03
        ld.color = kelvin_rgb(kelvin)
        light = bpy.data.objects.new("LampLight", ld)
        link(light, col)
        light.location = (0, 0, 0.395)
        light.parent = root
    return root, light


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))
    tod = s.get("time_of_day", "night")
    lamp_on = tod in ("evening", "night") or ctx.lights_on

    X0, X1, Y0, Y1, H = -2.0, 2.4, -2.2, 1.2, 2.5
    paper = wallpaper("BedroomPaper", "#bfae90", "#a3906c", 8.0)
    floor = M.wood("BedroomFloor", "oak", varnish=0.5, wear=0.4, grain_axis="Y", planks=(1.6, 0.13))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, ((X0 + X1) / 2, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, ((X0 + X1) / 2, (Y0 + Y1) / 2, H + 0.025),
        M.plaster("BCeil", "#ece6da", 0.9, 0.4, 0.1), col)
    win = dict(c=-0.9, w=1.0, b=0.85, t=2.1)
    wall("BackWall", col, paper, "y", Y1, X0, X1, 0, H, openings=[(win["c"], win["w"], win["b"], win["t"])])
    window("BedroomWindow", col, "y", Y1, win["c"], win["w"], win["b"], win["t"], inward=-1, panes=(2, 3))
    curtain("NightCurtainL", col, "y", Y1, win["c"] - 0.62, 0.55, 0.05, 2.4, -1, color="#3d4a5c", sheer=0.15,
            folds=7)
    curtain("NightCurtainR", col, "y", Y1, win["c"] + 0.62, 0.55, 0.05, 2.4, -1, color="#3d4a5c", sheer=0.15,
            folds=7)
    for nm, ax, pl in (("LeftWall", "x", X0), ("RightWall", "x", X1)):
        wall(nm, col, paper, ax, pl, Y0, Y1, 0, H)
    wall("FrontWall", col, paper, "y", Y0, X0, X1, 0, H)
    outdoor_backdrop(col, Vector((win["c"], Y1, 0)), Vector((0, 1, 0)), rng, distance=9.0, trees=6)
    # street lights far outside: bright points that become big soft bokeh
    for i in range(5):
        p = Vector((win["c"] + rng.uniform(-6, 6), Y1 + rng.uniform(14, 30), rng.uniform(2.5, 4.5)))
        ld = bpy.data.lights.new(f"StreetLight{i}", "POINT")
        ld.energy = rng.uniform(800, 2000)
        ld.shadow_soft_size = 0.1
        ld.color = kelvin_rgb(rng.choice([2100, 2200, 3000, 4000]))
        o = bpy.data.objects.new(f"StreetLight{i}", ld)
        link(o, col)
        o.location = p
        globe = cylinder(f"StreetGlobe{i}", 0.12, 0.25, tuple(p - Vector((0, 0, 0.12))), M.emitter(f"Sodium{i}", 2100, 60),
                         col, 24)

    # bed: frame, mattress, duvet, pillows (on the right of the bedside table)
    bed_wood = M.wood("BedFrame", "walnut", varnish=0.5, wear=0.3, grain_axis="X")
    box("BedFrame", 1.5, 2.0, 0.3, (1.25, 0.15, 0.25), bed_wood, col, bevel=0.01)
    box("Headboard", 1.55, 0.06, 1.1, (1.25, Y1 - 0.1, 0.55), bed_wood, col, bevel=0.015, segments=4)
    duvet = M.fabric("Duvet", "#e4ddd0", threads_per_m=2200, rough=0.9, sheen=0.6, pattern="stripe",
                     pattern_color="#c8beab", pattern_scale=14.0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(1.25, 0.05, 0.53))
    dv = bpy.context.object
    for c_ in dv.users_collection:
        c_.objects.unlink(dv)
    col.objects.link(dv)
    dv.name = "Duvet"
    dv.scale = (1.5, 1.9, 0.26)
    sub = dv.modifiers.new("Soft", "SUBSURF")
    sub.levels = sub.render_levels = 3
    disp = dv.modifiers.new("Rumple", "DISPLACE")
    tex = bpy.data.textures.new("Rumple", "CLOUDS")
    tex.noise_scale = 0.25
    disp.texture = tex
    disp.strength = 0.035
    dv.data.materials.append(duvet)
    for p_ in dv.data.polygons:
        p_.use_smooth = True
    for i, x in enumerate((0.92, 1.58)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=48, ring_count=24, location=(x, Y1 - 0.35, 0.72))
        pl = bpy.context.object
        for c_ in pl.users_collection:
            c_.objects.unlink(pl)
        col.objects.link(pl)
        pl.scale = (0.33, 0.2, 0.09)
        pl.data.materials.append(M.fabric("Pillow", "#efe9dd", 2400, 0.9, 0.6))
        for p_ in pl.data.polygons:
            p_.use_smooth = True

    # bedside table
    painted = M.plaster("BedsidePaint", "#5d6b62", rough=0.4, bump=0.3, stains=0.15)
    tx, ty = 0.0, 0.85
    box("BedsideBody", 0.48, 0.4, TOP_Z - 0.03, (tx, ty, (TOP_Z - 0.03) / 2), painted, col, bevel=0.008)
    top = box("BedsideTop", 0.52, 0.44, 0.03, (tx, ty, TOP_Z - 0.015), M.wood("BedsideTop", "oak", 0.6, 0.5, grain_axis="X"),
              col, bevel=0.006)
    box("Drawer", 0.42, 0.02, 0.14, (tx, ty - 0.21, TOP_Z - 0.12), painted, col, bevel=0.006)
    cylinder("DrawerKnob", 0.012, 0.022, (tx, ty - 0.23, TOP_Z - 0.12), M.metal("BKnob", "#b8924e", 0.3, 0.5, 0.4), col, 24,
             rot=(math.radians(90), 0, 0), bevel=0.003)
    surf = TOP_Z

    lights = []
    lamp, lamp_light = table_lamp(col, (tx - 0.1, ty + 0.08, surf), on=lamp_on)
    if lamp_light:
        lights.append(lamp_light)
        animate_flicker(lamp_light, lamp_light.data.energy, 0.015, float(ctx.quality["fps"]),
                        int(ctx.quality["frame_start"]), int(ctx.quality["frame_end"]), seed=5, speed=0.6)

    meta = ctx.job["polaroid"]
    extras = ctx.job.get("extra_prints", [])
    card_h = meta["card_mm"][1] / 1000.0
    anchor = Vector((tx + 0.03, ty - 0.08, surf))
    placement = s.get("placement", "leaning")
    if ctx.spec["camera"]["move"] == "top_down" and placement == "leaning":
        placement = "flat"
    if placement == "leaning":
        lean = 14.0
        # leaning against the lamp base
        hero, centre, normal = place_card(meta, "HeroPrint", col,
                                          Vector((tx - 0.06, ty - 0.03 - card_h * math.sin(math.radians(lean)), surf)),
                                          math.radians(rng.uniform(-8, 4)), "leaning", lean)
        el = 6.0
    else:
        base_z = surf
        if placement == "pile" and extras:
            pile = extras[: max(3, len(extras) // 2)]
            scatter_prints(pile, col, anchor, 0.03, rng, surf, prefix="Pile", stack=True)
            base_z = surf + len(pile) * 0.0013
            extras = extras[len(pile):]
        hero, centre, normal = place_card(meta, "HeroPrint", col, Vector((anchor.x, anchor.y, base_z)),
                                          math.radians(rng.uniform(-12, 12)), "flat")
        el = 36.0
    view = Vector((0.2, -1.0, 0.0)).normalized()
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))

    P.alarm_clock("Clock", col, (tx + 0.15, ty + 0.06, surf), math.radians(-20))
    rack_point = Vector((tx + 0.15, ty + 0.06, surf + 0.06))
    if clutter > 0.25:
        P.drinking_glass("Water", col, (tx - 0.17, ty - 0.12, surf), water=0.65)
    if clutter > 0.45:
        P.reading_glasses("Glasses", col, (tx + 0.13, ty - 0.12, surf), math.radians(15))
        P.book("NightBook", col, (tx + 0.02, ty + 0.1, surf + 0.0), (0.14, 0.21, 0.028), "#2f3e52",
               (0, 0, math.radians(80)), rng)
    if s.get("extra_photos", True) and extras and clutter > 0.6:
        scatter_prints(extras[:1], col, Vector((tx + 0.16, ty - 0.13, surf)), 0.02, rng, surf)

    ctx.sun_window = dict(centre=(win["c"], Y1, (win["b"] + win["t"]) / 2), bottom=win["b"], top=win["t"],
                          along=(1, 0, 0), width=win["w"], panes=2, rows=3)
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd, rack_point=rack_point,
        tilt_from=Vector((win["c"], Y1, 1.4)), pan_from=Vector((tx - 0.17, ty - 0.12, surf + 0.06)),
        reveal_target=Vector((tx + 0.3, ty, surf + 0.2)), min_height=surf + 0.015,
    )
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-0.6, 0.0, surf)), Vector((0.6, 1.2, surf + 0.8)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
