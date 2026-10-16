"""Photo line: prints pegged along twine lines on a wall, fairy lights woven through them.

Built for several photos: the camera can tour along the line or cut from print to print.
Optionally a darkroom, lit by a red safelight.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder, link
from ..world import kelvin_rgb
from .common import (Ctx, Room, clothes_peg, fairy_lights, hang_card, opt, outdoor_backdrop, sagging_line,
                     switched_on, wall, window)


def _brick(name="Brick"):
    """Painted brick: mortar recess, slightly uneven bricks, chipped paint."""
    from ..util import Nodes, new_material, srgb
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping", Rotation=(math.radians(90), 0, 0))
    n.link(tc, "Object", mp, "Vector")
    br = n.new("ShaderNodeTexBrick", Scale=1.0, _offset=0.5)
    br.inputs["Brick Width"].default_value = 0.215
    br.inputs["Row Height"].default_value = 0.075
    br.inputs["Mortar Size"].default_value = 0.008
    br.inputs["Mortar Smooth"].default_value = 0.4
    br.inputs["Color1"].default_value = srgb("#e7e1d6")
    br.inputs["Color2"].default_value = srgb("#d9d1c3")
    br.inputs["Mortar"].default_value = srgb("#b9b0a2")
    n.link(mp, None, br, "Vector")
    chip = n.new("ShaderNodeTexNoise", Scale=30.0, Detail=8.0)
    n.link(mp, None, chip, "Vector")
    chips = n.ramp((chip, "Fac"), [(0.66, (0, 0, 0)), (0.7, (1, 1, 1))])
    col = n.mix("RGBA", (chips, "Color"), (br, "Color"), srgb("#8a4a36"))
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.85)
    n.link(col, None, b, "Base Color")
    bump = n.new("ShaderNodeBump", Strength=0.6, Distance=0.004)
    n.link(n.math("SUBTRACT", 1.0, (br, "Fac")), None, bump, "Height")
    rough_n = n.new("ShaderNodeTexNoise", Scale=200.0, Detail=4.0)
    n.link(mp, None, rough_n, "Vector")
    bump2 = n.new("ShaderNodeBump", Strength=0.15, Distance=0.001)
    n.link(rough_n, "Fac", bump2, "Height")
    n.link(bump, None, bump2, "Normal")
    n.link(bump2, None, b, "Normal")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    return mat


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    darkroom = bool(opt(ctx, "darkroom", False))
    lights_on = switched_on(ctx, "fairy_lights", "on")
    wall_kind = opt(ctx, "wall", "brick")
    lines_n = int(opt(ctx, "lines", 2))

    X0, X1, Y0, Y1, H = -2.4, 2.4, -2.6, 0.6, 2.6
    wall_mat = _brick("PaintedBrick") if wall_kind == "brick" else M.plaster("LineWall", "#cfc6b4", 0.85, 1.0, 0.25)
    floor = M.wood("LineFloor", "oak", varnish=0.4, wear=0.5, grain_axis="X", planks=(1.4, 0.14))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("LCeil", "#ebe5d8", 0.9, 0.4, 0.1), col)
    wall("PhotoWall", col, wall_mat, "y", Y1, X0, X1, 0, H)
    side = dict(c=-1.4, w=1.0, b=0.85, t=2.1)
    plain = M.plaster("SideWalls", "#d8cfbd", 0.85, 0.8, 0.2)
    if darkroom:
        wall("LeftWall", col, plain, "x", X0, Y0, Y1, 0, H)
    else:
        wall("LeftWall", col, plain, "x", X0, Y0, Y1, 0, H, openings=[(side["c"], side["w"], side["b"], side["t"])])
        window("LineWindow", col, "x", X0, side["c"], side["w"], side["b"], side["t"], inward=1, panes=(2, 3))
        outdoor_backdrop(col, Vector((X0, side["c"], 0)), Vector((-1, 0, 0)), rng, distance=6.0, trees=4, hedge=False)
    wall("RightWall", col, plain, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, plain, "y", Y0, X0, X1, 0, H)

    # a desk under the lines with a few things on it (blurred foreground/background detail)
    desk_z = 0.74
    box("LineDesk", 1.6, 0.6, 0.03, (0.0, Y1 - 0.36, desk_z - 0.015), M.wood("LineDesk", "oak", 0.5, 0.5, grain_axis="X"),
        col, bevel=0.004)
    for x in (-0.75, 0.75):
        box("LineDeskLeg", 0.04, 0.55, desk_z - 0.03, (x, Y1 - 0.36, (desk_z - 0.03) / 2),
            M.metal("DeskLegSteel", "#2a2a2c", 0.4, 0.3, 0.1), col)
    P.book_stack("LineBooks", col, (0.55, Y1 - 0.35, desk_z), 3, rng, rot_z=math.radians(10))
    P.mug("LineMug", col, (-0.5, Y1 - 0.45, desk_z), rng.uniform(0, 6.28), "#d9d2c4", coffee=0.3)
    lights = []
    if darkroom:
        # developing trays and the red safelight
        for i, x in enumerate((-0.35, 0.0, 0.35)):
            tray = box(f"Tray{i}", 0.3, 0.38, 0.05, (x, Y1 - 0.36, desk_z + 0.025),
                       M.plastic(f"Tray{i}", ["#c23a2e", "#d8d0c0", "#2f5a8a"][i], 0.3, 0.2), col, bevel=0.01)
            liquid = box(f"Chem{i}", 0.27, 0.35, 0.002, (x, Y1 - 0.36, desk_z + 0.035), M.glass(f"Chem{i}", "#e9e2c8", 0.0, 1.33), col)
        ld = bpy.data.lights.new("Safelight", "AREA")
        ld.size = 0.2
        ld.energy = 25
        ld.color = (1.0, 0.08, 0.02)
        sl = bpy.data.objects.new("Safelight", ld)
        link(sl, col)
        sl.location = (1.1, Y1 - 0.25, 1.95)
        sl.rotation_euler = (Vector((0.0, Y1 - 0.4, 1.3)) - sl.location).to_track_quat("-Z", "Y").to_euler()
        box("SafelightBox", 0.22, 0.12, 0.16, (1.1, Y1 - 0.08, 1.95), M.plastic("SafelightBody", "#1b1b1b", 0.4), col,
            bevel=0.01)
        face = box("SafelightFace", 0.18, 0.004, 0.12, (1.1, Y1 - 0.142, 1.95), M.emitter("SafeRed", 900, 0.0), col)
        face.data.materials.clear()
        red = bpy.data.materials.new("SafeRedGlow")
        red.use_nodes = True
        nt = red.node_tree
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (1.0, 0.05, 0.01, 1)
        em.inputs["Strength"].default_value = 12.0
        nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs[0])
        face.data.materials.append(red)
        lights.append(sl)

    # ------------------------------------------------------------------ the lines and the prints
    metas = list(ctx.job.get("extra_prints", []))
    hero_meta = ctx.job["polaroid"]
    wall_y = Y1 - 0.06
    rows = [(1.62, 0.09), (1.28, 0.07)][:max(1, min(2, lines_n))]
    twine = M.fabric("LineTwine", "#a5865c", threads_per_m=2500, rough=0.9, sheen=0.4)
    hero_row = len(rows) - 1 if len(rows) > 1 else 0
    hero_obj = centre = normal = None
    for r_i, (z, sag) in enumerate(rows):
        a = Vector((-1.1, wall_y, z))
        b = Vector((1.1, wall_y, z + rng.uniform(-0.02, 0.02)))
        for nail in (a, b):
            cylinder("Nail", 0.003, 0.03, (nail.x, wall_y + 0.03, nail.z), M.metal("Nail", "#7a7a7a", 0.4, 0.3, 0.6), col,
                     12, rot=(math.radians(90), 0, 0))
        at = sagging_line(f"Line{r_i}", col, a, b, sag, mat=twine)
        if lights_on and not darkroom:
            fairy_lights(col, [at(k / 6) + Vector((0, -0.01, -0.012)) for k in range(7)], 34, rng,
                         name=f"LineFairy{r_i}")
        slots = [0.12, 0.27, 0.42, 0.58, 0.73, 0.88]
        if r_i == hero_row:
            hero_slot = 2
        else:
            hero_slot = -1
        for k, tpos in enumerate(slots):
            jitter = rng.uniform(-0.02, 0.02)
            top = at(tpos + jitter) + Vector((0, -0.004, -0.004))
            yaw = math.radians(rng.uniform(-5, 5))
            roll = math.radians(rng.uniform(-6, 6))
            sway = math.radians(rng.uniform(-6, 2))
            if k == hero_slot:
                hero_obj, centre, normal = hang_card(hero_meta, "HeroPrint", col, top, yaw * 0.4, roll * 0.5, sway * 0.5)
            elif metas:
                hang_card(metas.pop(0), f"LinePrint{r_i}{k}", col, top, yaw, roll, sway)
            else:
                continue
            clothes_peg(f"Peg{r_i}{k}", col, top + Vector((0, -0.006, 0.006)), yaw, roll)

    if hero_obj is None:  # not enough slots: hang the hero in the middle of the first line
        hero_obj, centre, normal = hang_card(hero_meta, "HeroPrint", col, Vector((0, wall_y - 0.004, rows[0][0] - rows[0][1])))

    # a warm practical lamp when not in the darkroom
    if not darkroom:
        lamp, ll = P.bankers_lamp("LineLamp", col, (-0.62, Y1 - 0.25, desk_z), math.radians(15),
                                  on=switched_on(ctx, "lamp"), power=6.0)
        if ll:
            lights.append(ll)

    card_h = hero_meta["card_mm"][1] / 1000.0
    view = Vector((0.12, -1.0, 0.0)).normalized()
    el = 3.0
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=card_h * max(0.35, abs(normal.dot(vd))), view_dir=vd,
        rack_point=Vector((0.4, Y1 - 0.35, desk_z + 0.1)), tilt_from=Vector((0.0, wall_y, 2.2)),
        pan_from=centre + Vector((0.45, 0, 0.02)), reveal_target=Vector((0, wall_y, 1.35)), min_height=desk_z + 0.05,
    )
    if not darkroom:
        ctx.sun_window = dict(centre=(X0, side["c"], (side["b"] + side["t"]) / 2), bottom=side["b"], top=side["t"],
                              along=(0, 1, 0), width=side["w"], panes=2, rows=3)
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-1.2, Y1 - 1.6, 0.8)), Vector((1.2, Y1, 2.2)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero_obj)
