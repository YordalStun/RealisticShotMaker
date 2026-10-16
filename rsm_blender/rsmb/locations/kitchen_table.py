"""Kitchen table, morning: a farmhouse kitchen with soft light through net curtains."""
from __future__ import annotations

import math

from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder
from .common import (Ctx, Room, crumbs, curtain, drink_ring, opt, outdoor_backdrop, place_card, scatter_prints,
                     switched_on, wall, window)

TABLE_Z = 0.77


def _cabinet_run(col, x0, x1, y, depth, height, z0, door_w, wood, worktop=None, knob_mat=None, rng=None):
    """A run of panelled cabinet doors."""
    n = max(1, int(round((x1 - x0) / door_w)))
    dw = (x1 - x0) / n
    box("CabCarcass", x1 - x0, depth, height, ((x0 + x1) / 2, y, z0 + height / 2), wood, col, bevel=0.004)
    for i in range(n):
        cx = x0 + dw * (i + 0.5)
        box(f"Door{i}", dw - 0.006, 0.02, height - 0.02, (cx, y - depth / 2 - 0.01, z0 + height / 2), wood, col,
            bevel=0.006, segments=3)
        # raised panel
        box(f"Panel{i}", dw - 0.09, 0.012, height - 0.11, (cx, y - depth / 2 - 0.022, z0 + height / 2), wood, col,
            bevel=0.012, segments=4)
        if knob_mat is not None:
            cylinder(f"Knob{i}", 0.011, 0.02, (cx + (dw / 2 - 0.05) * (1 if i % 2 else -1), y - depth / 2 - 0.04,
                                                 z0 + height * (0.82 if z0 < 1 else 0.18)), knob_mat, col, 24,
                     rot=(math.radians(90), 0, 0), bevel=0.003)
    if worktop is not None:
        box("Worktop", x1 - x0 + 0.04, depth + 0.04, 0.04, ((x0 + x1) / 2, y - 0.01, z0 + height + 0.02), worktop, col,
            bevel=0.004)


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))

    X0, X1, Y0, Y1, H = -2.4, 2.4, -2.2, 2.0, 2.5
    walls = M.plaster("KitchenWalls", "#e2d9c3", rough=0.8, bump=0.8, stains=0.2)
    tiles = M.ceramic("Tiles", "#e8e4d8", rough=0.08, speckle=0.15, crazing=0.2)
    floor = M.wood("KitchenFloor", "pine", varnish=0.3, wear=0.7, dust=0.1, grain_axis="Y", planks=(1.5, 0.16))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("KCeiling", "#efebe2", 0.9, 0.5, 0.1), col)
    win = dict(c=-0.2, w=1.2, b=1.0, t=2.1)
    wall("BackWall", col, walls, "y", Y1, X0, X1, 0, H, openings=[(win["c"], win["w"], win["b"], win["t"])])
    window("KitchenWindow", col, "y", Y1, win["c"], win["w"], win["b"], win["t"], inward=-1, panes=(2, 2))
    # net curtains: very sheer, half height (cafe curtains)
    if opt(ctx, "net_curtains", True):
        curtain("NetCurtain", col, "y", Y1, win["c"], win["w"] * 1.6, win["b"] + 0.02, win["b"] + 0.6, -1,
                color="#f4f1ea", sheer=0.9, folds=22, gather=0.65)
    side = dict(c=-0.9, w=0.9, b=0.95, t=2.0)
    wall("LeftWall", col, walls, "x", X0, Y0, Y1, 0, H, openings=[(side["c"], side["w"], side["b"], side["t"])])
    window("SideWindow", col, "x", X0, side["c"], side["w"], side["b"], side["t"], inward=1, panes=(2, 2))
    wall("RightWall", col, walls, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, walls, "y", Y0, X0, X1, 0, H)
    outdoor_backdrop(col, Vector((win["c"], Y1, 0)), Vector((0, 1, 0)), rng, distance=6.0)
    outdoor_backdrop(col, Vector((X0, side["c"], 0)), Vector((-1, 0, 0)), rng, distance=6.0, trees=0, hedge=False)

    # kitchen units along the back wall, tiled splashback
    painted = M.wood("Units", "painted_white", varnish=0.35, wear=0.35, scale=2.0, grain_axis="Z")
    sage = M.plaster("UnitPaint", "#8fa293", rough=0.45, bump=0.3, stains=0.1)
    oak_top = M.wood("Worktop", "oak", varnish=0.6, wear=0.5, grain_axis="X", seed=2.2)
    brass = M.metal("Knobs", "#b38d4c", rough=0.3, smudge=0.5, tarnish=0.4)
    _cabinet_run(col, 0.55, 2.3, Y1 - 0.32, 0.6, 0.86, 0.0, 0.45, sage, oak_top, brass, rng)
    _cabinet_run(col, 0.65, 2.3, Y1 - 0.2, 0.34, 0.7, 1.45, 0.45, sage, None, brass, rng)
    box("Splashback", 1.8, 0.01, 0.55, (1.45, Y1 - 0.065, 0.9 + 0.275), tiles, col)
    # open shelf with plates
    box("PlateShelf", 0.9, 0.22, 0.025, (-1.4, Y1 - 0.12, 1.55), painted, col, bevel=0.004)
    for i in range(5):
        pl = cylinder(f"Plate{i}", 0.11, 0.012, (-1.75 + i * 0.17, Y1 - 0.16, 1.565 + 0.11), M.ceramic(
            "PlateGlaze", rng.choice(["#e9e3d3", "#c9d6dc", "#e5d4b8"]), 0.05, 0.3, 0.3), col, 48, bevel=0.003)
        pl.rotation_euler = (math.radians(80), 0, 0)
    # hanging pendant lamp (on in the evening)
    lights = []
    if switched_on(ctx, "pendant"):
        from ..world import kelvin_rgb
        import bpy
        ld = bpy.data.lights.new("Pendant", "POINT")
        ld.energy = 45
        ld.shadow_soft_size = 0.05
        ld.color = kelvin_rgb(2700)
        pend = bpy.data.objects.new("Pendant", ld)
        col.objects.link(pend)
        pend.location = (0.0, 0.3, 1.6)
        lights.append(pend)
        shade = P.lathe("PendantShade", [(0.02, 0.0), (0.16, -0.12), (0.17, -0.13)], 64,
                        M.metal("Enamel", "#2f4a3c", 0.35, 0.2, 0.0), col, loc=(0.0, 0.3, 1.72))
        shade.modifiers.new("Thick", "SOLIDIFY").thickness = 0.002

    # ------------------------------------------------------------------ table
    pine = M.wood("TableTop", "pine", varnish=0.15, wear=0.85, dust=0.03, grain_axis="X", seed=4.4, planks=(2.0, 0.19))
    leg_wood = M.wood("TableLegs", "pine", varnish=0.2, wear=0.6, grain_axis="Z", seed=6.1)
    box("TableTop", 1.8, 0.95, 0.045, (0, 0.35, TABLE_Z - 0.0225), pine, col, bevel=0.008, segments=4)
    box("TableApron", 1.6, 0.8, 0.1, (0, 0.35, TABLE_Z - 0.095), leg_wood, col, bevel=0.003)
    for i, (x, y) in enumerate(((-0.82, -0.06), (0.82, -0.06), (-0.82, 0.76), (0.82, 0.76))):
        box(f"TableLeg{i}", 0.07, 0.07, TABLE_Z - 0.045, (x, y, (TABLE_Z - 0.045) / 2), leg_wood, col, bevel=0.006)
    # linen runner down the middle
    runner = M.fabric("Runner", "#e9e2d0", threads_per_m=1400, rough=0.9, sheen=0.4, pattern="stripe",
                      pattern_color="#a64a3c", pattern_scale=9.0)
    box("TableRunner", 1.9, 0.36, 0.002, (0, 0.42, TABLE_Z + 0.001), runner, col)
    surf = TABLE_Z

    # ------------------------------------------------------------------ hero print
    placement = s.get("placement", "leaning")
    if ctx.spec["camera"]["move"] == "top_down" and placement == "leaning":
        placement = "flat"
    meta = ctx.job["polaroid"]
    extras = ctx.job.get("extra_prints", [])
    card_h = meta["card_mm"][1] / 1000.0
    anchor = Vector((0.05, 0.2, surf))
    if placement == "leaning":
        lean = 16.0
        # leaning against the jam jar; the teapot sits further back as a soft shape in the background
        P.jar("Jam", col, (anchor.x + 0.01, anchor.y + card_h * math.sin(math.radians(lean)) + 0.036, surf))
        P.teapot("Teapot", col, (anchor.x + 0.34, anchor.y + 0.33, surf), math.radians(200))
        hero, centre, normal = place_card(meta, "HeroPrint", col, anchor, math.radians(rng.uniform(-5, 5)), "leaning",
                                          lean)
        el = 5.0
    else:
        base_z = surf
        if placement == "pile" and extras:
            pile = extras[: max(3, len(extras) // 2)]
            scatter_prints(pile, col, anchor, 0.03, rng, surf, prefix="Pile", stack=True)
            base_z = surf + len(pile) * 0.0013
            extras = extras[len(pile):]
        hero, centre, normal = place_card(meta, "HeroPrint", col, Vector((anchor.x, anchor.y, base_z)),
                                          math.radians(rng.uniform(-12, 12)), "flat")
        P.teapot("Teapot", col, (anchor.x + 0.25, anchor.y + 0.25, surf), math.radians(200))
        el = 34.0
    view = Vector((-0.12, -1.0, 0.0)).normalized()
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))

    # ------------------------------------------------------------------ props
    P.cup_and_saucer("Cup", col, (anchor.x - 0.22, anchor.y - 0.12, surf), math.radians(rng.uniform(0, 360)))
    rack_point = Vector((anchor.x + 0.34, anchor.y + 0.33, surf + 0.08))
    if clutter > 0.2 and opt(ctx, "fruit", True):
        P.fruit_bowl("Fruit", col, (-0.42, 0.62, surf), rng)
    if clutter > 0.4:
        if placement != "leaning":
            P.jar("Jam", col, (-0.35, 0.42, surf))
        if opt(ctx, "flowers", True):
            P.vase_with_stems("Flowers", col, (0.62, 0.68, surf), rng)
    mess = opt(ctx, "mess", "some")
    if mess in ("some", "lots"):
        crumbs(col, Vector((anchor.x - 0.08, anchor.y - 0.1, surf)), 0.09, 40 if mess == "some" else 160, rng,
               "#c48d4c", name="Crumbs")
        _knife(col, Vector((anchor.x + 0.15, anchor.y - 0.13, surf)), math.radians(rng.uniform(15, 40)), jam=True)
        _spoon(col, Vector((anchor.x - 0.3, anchor.y - 0.02, surf)), math.radians(rng.uniform(-30, 30)))
    if mess == "lots":
        plate = cylinder("TostPlate", 0.1, 0.012, (anchor.x + 0.3, anchor.y - 0.06, surf),
                         M.ceramic("Plate", "#ece6d6", 0.05, 0.3, 0.3), col, 64, bevel=0.004)
        _toast(col, Vector((anchor.x + 0.3, anchor.y - 0.06, surf + 0.012)), rng)
        crumbs(col, Vector((anchor.x + 0.12, anchor.y + 0.02, surf)), 0.05, 120, rng, "#f4f1ea", (0.0004, 0.0009),
               name="Sugar")
        drink_ring(col, Vector((anchor.x - 0.15, anchor.y - 0.22, surf)), 0.04, name="TeaRing1")
        drink_ring(col, Vector((anchor.x + 0.22, anchor.y + 0.14, surf)), 0.045, name="TeaRing2", strength=0.4)
    if clutter > 0.6:
        box("BreadBoard", 0.36, 0.22, 0.02, (0.6, 0.12, surf + 0.01), M.wood("Board", "oak", 0.0, 0.9, grain_axis="X"),
            col, bevel=0.005)
        P.letter_pile("Post", col, (-0.12, 0.05, surf), 2, rng)
    if s.get("extra_photos", True) and extras:
        scatter_prints(extras[:3], col, Vector((anchor.x, anchor.y - 0.05, surf)), 0.26, rng, surf,
                       avoid=Vector((anchor.x, anchor.y, surf)), avoid_r=0.13)

    ctx.sun_window = dict(centre=(X0, side["c"], (side["b"] + side["t"]) / 2), bottom=side["b"], top=side["t"],
                          along=(0, 1, 0), width=side["w"], panes=2, rows=2)
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd, rack_point=rack_point,
        tilt_from=Vector((win["c"], Y1, 1.5)), pan_from=Vector((anchor.x - 0.22, anchor.y - 0.12, surf + 0.05)),
        reveal_target=Vector((0.0, 0.5, surf + 0.15)), min_height=surf + 0.015,
    )
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-1.0, -0.3, surf)), Vector((1.0, 1.4, surf + 1.0)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)


def _knife(col, at: Vector, rot: float, jam=False):
    """Butter knife lying on the table, with a smear of jam on the blade."""
    steel = M.metal("Cutlery", "#cfcfcf", rough=0.15, smudge=0.5, tarnish=0.05)
    import bpy
    root = bpy.data.objects.new("Knife", None)
    col.objects.link(root)
    root.location = at
    root.rotation_euler = (0, 0, rot)
    blade = box("KnifeBlade", 0.11, 0.018, 0.0025, (0.055, 0, 0.004), steel, col, bevel=0.0009)
    blade.parent = root
    handle = box("KnifeHandle", 0.1, 0.016, 0.009, (-0.05, 0, 0.0055), M.wood("KnifeHandle", "walnut", 0.6, 0.6), col,
                 bevel=0.004, segments=4)
    handle.parent = root
    if jam:
        j = box("JamSmear", 0.04, 0.012, 0.0012, (0.08, 0.001, 0.0058), M.ceramic("JamSmear", "#6e1422", 0.12, 0.0),
                col, bevel=0.0005)
        j.parent = root
    return root


def _spoon(col, at: Vector, rot: float):
    import bpy
    steel = M.metal("Cutlery", "#cfcfcf", rough=0.15, smudge=0.5, tarnish=0.05)
    root = bpy.data.objects.new("Spoon", None)
    col.objects.link(root)
    root.location = at
    root.rotation_euler = (0, 0, rot)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=32, ring_count=16, location=(0.045, 0, 0.004))
    bowl = bpy.context.object
    for c in bowl.users_collection:
        c.objects.unlink(bowl)
    col.objects.link(bowl)
    bowl.scale = (0.018, 0.012, 0.004)
    bowl.data.materials.append(steel)
    bowl.parent = root
    h = box("SpoonHandle", 0.09, 0.006, 0.0025, (-0.02, 0, 0.003), steel, col, bevel=0.001)
    h.parent = root
    return root


def _toast(col, at: Vector, rng):
    """A slice of toast with a bite out of it."""
    import bmesh
    import bpy
    from ..util import mesh_object, srgb
    mat = bpy.data.materials.new("Toast")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 220.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = srgb("#8a5524")
    ramp.color_ramp.elements[1].color = srgb("#d9a25e")
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.85
    b.inputs["Subsurface Weight"].default_value = 0.15
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    bm = bmesh.new()
    pts = []
    for i in range(40):
        a = i / 40 * 2 * math.pi
        r = 0.05 * (1.0 + 0.08 * math.cos(2 * a))
        x, y = math.cos(a) * r, math.sin(a) * r * 1.1
        if y > 0.035 and abs(x) < 0.025:  # the bite
            y = 0.035 - (0.025 - abs(x)) * 0.6
        pts.append(bm.verts.new((x, y, 0.0)))
    f = bm.faces.new(pts)
    ret = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.z += 0.012
    o = mesh_object("Toast", bm, col, mat=mat)
    o.location = at
    o.rotation_euler = (0, 0, rng.uniform(0, 6.28))
    from ..util import add_bevel
    add_bevel(o, 0.002, 2, 40)
    return o
