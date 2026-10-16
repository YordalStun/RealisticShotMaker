"""Attic memory trunk: dusty attic, skylight beam, an open trunk of letters and photos."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import box, cylinder
from .common import Ctx, Room, cobweb_strands, opt, place_card, scatter_prints, switched_on


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))
    W, D, RIDGE, EAVE = 5.0, 6.0, 2.6, 0.6
    boards = M.wood("AtticFloor", "pine", varnish=0.0, wear=0.9, dust=0.6, grain_axis="Y", planks=(2.4, 0.2))
    beam = M.wood("Beams", "aged_beam", varnish=0.0, wear=0.7, dust=0.35, scale=1.2, grain_axis="Z")
    sarking = M.wood("RoofBoards", "aged_beam", varnish=0.0, wear=0.6, dust=0.2, grain_axis="Y", planks=(3.0, 0.15))
    box("Floor", W, D, 0.05, (0, 0, -0.025), boards, col)

    # two roof slopes with an opening for the skylight on the left slope
    pitch = math.atan2(RIDGE - EAVE, W / 2)
    slope_len = math.hypot(W / 2, RIDGE - EAVE)
    sky = dict(y=-0.5, w=0.8, along=1.15, len=0.9)  # skylight position along the left slope
    for side in (-1, 1):
        cx = side * W / 4
        cz = (RIDGE + EAVE) / 2
        rot = (0, side * pitch, 0)
        if side == -1:
            # split the left slope around the skylight
            segs = [(-D / 2, sky["y"] - sky["w"] / 2, 0, slope_len), (sky["y"] + sky["w"] / 2, D / 2, 0, slope_len),
                    (sky["y"] - sky["w"] / 2, sky["y"] + sky["w"] / 2, 0, sky["along"] - sky["len"] / 2),
                    (sky["y"] - sky["w"] / 2, sky["y"] + sky["w"] / 2, sky["along"] + sky["len"] / 2, slope_len)]
            for i, (y0, y1, a0, a1) in enumerate(segs):
                # position along the slope measured from the eave
                mid = (a0 + a1) / 2
                px = -W / 2 + math.cos(pitch) * mid
                pz = EAVE + math.sin(pitch) * mid
                o = box(f"RoofL{i}", a1 - a0, y1 - y0, 0.03, (px, (y0 + y1) / 2, pz), sarking, col)
                o.rotation_euler = (0, -pitch, 0)
        else:
            o = box("RoofR", slope_len, D, 0.03, (cx, 0, cz), sarking, col)
            o.rotation_euler = (0, pitch, 0)
    # rafters and a ridge beam
    for i in range(9):
        y = -D / 2 + 0.3 + i * (D - 0.6) / 8
        for side in (-1, 1):
            r = box(f"Rafter{i}{side}", slope_len, 0.075, 0.15, (side * W / 4, y, (RIDGE + EAVE) / 2 - 0.09), beam, col,
                    bevel=0.006)
            r.rotation_euler = (0, side * pitch, 0)
    box("Ridge", 0.1, D, 0.2, (0, 0, RIDGE - 0.12), beam, col, bevel=0.006)
    for i in range(3):
        box(f"Tie{i}", W - 0.6, 0.12, 0.15, (0, -2.0 + i * 2.0, 1.9), beam, col, bevel=0.006)
    # gable walls
    plaster = M.plaster("Gable", "#a99c86", rough=0.95, bump=1.6, stains=0.6, dust=0.2)
    for y in (-D / 2, D / 2):
        box("Gable", W, 0.1, RIDGE, (0, y, RIDGE / 2), plaster, col)
    # skylight glass + frame
    along = sky["along"]
    gx = -W / 2 + math.cos(pitch) * along
    gz = EAVE + math.sin(pitch) * along + 0.03
    g = box("SkylightGlass", sky["len"], sky["w"], 0.006, (gx, sky["y"], gz), M.glass("SkyGlass", "#eef3f0", 0.03, smudge=0.8),
            col)
    g.rotation_euler = (0, -pitch, 0)
    g.visible_shadow = False
    ld = bpy.data.lights.new("SkyPortal", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = sky["len"], sky["w"]
    ld.cycles.is_portal = True
    portal = bpy.data.objects.new("SkyPortal", ld)
    col.objects.link(portal)
    portal.location = (gx + 0.02, sky["y"], gz - 0.04)
    portal.rotation_euler = (0, -pitch, 0)

    # ------------------------------------------------------------------ the trunk and its contents
    trunk_loc = Vector((0.15, 0.1, 0.0))
    tw, td, th = 0.9, 0.52, 0.46
    P.old_trunk("Trunk", col, tuple(trunk_loc), math.radians(-8), size=(tw, td, th), lid_open_deg=108)
    # the trunk is half full: an old blanket underneath, then a layer of tied letter bundles
    base_z = 0.21
    trunk_rot = math.radians(-8)
    blanket = M.fabric("TrunkBlanket", "#5a4636", threads_per_m=700, rough=0.95, sheen=0.5)
    box("TrunkFill", tw - 0.05, td - 0.05, base_z - 0.02, (trunk_loc.x, trunk_loc.y, 0.015 + (base_z - 0.02) / 2),
        blanket, col).rotation_euler = (0, 0, trunk_rot)
    extras = ctx.job.get("extra_prints", [])
    fill = opt(ctx, "trunk_fill", "letters")
    from mathutils import Matrix
    rot = Matrix.Rotation(trunk_rot, 3, "Z")
    tops = [base_z]
    if fill in ("letters", "mixed"):
        cols_, rows_ = 4, 3
        for ix in range(cols_):
            for iy in range(rows_):
                if fill == "mixed" and (ix, iy) in ((2, 1), (3, 0)):
                    continue  # leave room for loose photos
                lx = (ix + 0.5) / cols_ * (tw - 0.1) - (tw - 0.1) / 2 + rng.uniform(-0.015, 0.015)
                ly = (iy + 0.5) / rows_ * (td - 0.1) - (td - 0.1) / 2 + rng.uniform(-0.01, 0.01)
                p = trunk_loc + rot @ Vector((lx, ly, 0))
                _, top = P.letter_bundle(f"Bundle{ix}{iy}", col, (p.x, p.y, base_z), trunk_rot + rng.uniform(-0.07, 0.07),
                                         count=rng.randint(8, 18), rng=rng)
                tops.append(base_z + top)
    inside_z = max(tops)
    if fill in ("photos", "mixed") and extras:
        scatter_prints(extras[-3:], col, Vector((trunk_loc.x + 0.2, trunk_loc.y + 0.05, inside_z)), 0.12, rng,
                       inside_z, prefix="LoosePrint")
    meta = ctx.job["polaroid"]
    extras = ctx.job.get("extra_prints", [])
    card_h = meta["card_mm"][1] / 1000.0
    anchor = Vector((trunk_loc.x + 0.05, trunk_loc.y - 0.06, inside_z + 0.006))
    placement = s.get("placement", "flat")
    base_z = anchor.z
    if extras:
        n = len(extras) if placement == "pile" else min(3, len(extras))
        scatter_prints(extras[:n], col, anchor, 0.035 if placement == "pile" else 0.16, rng, anchor.z,
                       prefix="TrunkPrint", stack=placement == "pile", avoid=None if placement == "pile" else anchor,
                       avoid_r=0.1)
        if placement == "pile":
            base_z = anchor.z + n * 0.0013
    if placement == "leaning":
        # leaning against the inside wall of the trunk
        hero, centre, normal = place_card(meta, "HeroPrint", col, Vector((anchor.x, trunk_loc.y + td / 2 - 0.09, inside_z)),
                                          math.radians(rng.uniform(-6, 6)), "leaning", 20.0)
        el = 28.0  # look down over the front wall of the trunk
    else:
        hero, centre, normal = place_card(meta, "HeroPrint", col, Vector((anchor.x, anchor.y, base_z)),
                                          math.radians(rng.uniform(-15, 15)), "flat")
        el = 55.0
    view = Vector((0.15, -1.0, 0.0)).normalized()
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))

    # ------------------------------------------------------------------ attic clutter
    sheet = M.fabric("DustSheet", "#d8d0bf", threads_per_m=1200, rough=0.95, sheen=0.4)
    if clutter > 0.2 and opt(ctx, "dust_sheets", True):
        # sheet-covered armchair shape
        bpy.ops.mesh.primitive_cube_add(size=1, location=(1.4, 1.6, 0.45))
        ch = bpy.context.object
        ch.scale = (0.8, 0.8, 0.9)
        for c_ in ch.users_collection:
            c_.objects.unlink(ch)
        col.objects.link(ch)
        sub = ch.modifiers.new("Soft", "SUBSURF")
        sub.levels = 3
        sub.render_levels = 3
        disp = ch.modifiers.new("Drape", "DISPLACE")
        tex = bpy.data.textures.new("Drape", "CLOUDS")
        tex.noise_scale = 0.35
        disp.texture = tex
        disp.strength = 0.08
        ch.data.materials.append(sheet)
        for p_ in ch.data.polygons:
            p_.use_smooth = True
        P.book_stack("AtticBooks", col, (-0.75, 0.6, 0.0), count=5, rng=rng, rot_z=0.4)
    if clutter > 0.45:
        # an old suitcase and a hatbox
        box("Suitcase", 0.62, 0.2, 0.42, (-1.2, 1.3, 0.21), M.leather("Suitcase", "#5a3a24", 0.55, 0.8), col, bevel=0.02)
        cylinder("Hatbox", 0.2, 0.22, (-0.9, -1.3, 0.0), M.paper("Hatbox", "#b9a38a", 0.8, 0.8), col, 64, bevel=0.004)
    if clutter > 0.65:
        P.candle("AtticCandle", col, (trunk_loc.x + 0.55, trunk_loc.y - 0.25, 0.0), 0.09, 0.025, lit=False)
        box("Crate", 0.45, 0.35, 0.3, (1.0, -0.9, 0.15), M.wood("Crate", "pine", 0.0, 0.8, 0.5, planks=(0.6, 0.09)), col,
            bevel=0.004)
    lights = []
    if opt(ctx, "cobwebs", True):
        pairs = []
        for i in range(10):
            y = rng.uniform(-1.5, 1.5)
            a = Vector((rng.uniform(-1.6, -0.6), y, rng.uniform(1.2, 1.9)))
            b = a + Vector((rng.uniform(0.15, 0.6), rng.uniform(-0.3, 0.3), rng.uniform(-0.35, 0.1)))
            pairs.append((a, b))
        # webs strung across the skylight shaft catch the light
        for i in range(5):
            a = Vector((-1.0 + rng.uniform(-0.2, 0.2), -0.5 + rng.uniform(-0.4, 0.4), 1.75))
            pairs.append((a, a + Vector((rng.uniform(0.2, 0.5), rng.uniform(-0.2, 0.2), -rng.uniform(0.1, 0.4)))))
        cobweb_strands(col, pairs, rng)
    if switched_on(ctx, "bare_bulb"):
        # a bare bulb hanging from the ridge
        bulb = cylinder("BareBulb", 0.03, 0.08, (0.0, -0.4, 1.75), M.frosted_bulb("BareBulb", 2400, 30), col, 32)
        from ..world import kelvin_rgb
        ld = bpy.data.lights.new("BulbLight", "POINT")
        ld.energy = 60
        ld.shadow_soft_size = 0.03
        ld.color = kelvin_rgb(2400)
        lo = bpy.data.objects.new("BulbLight", ld)
        col.objects.link(lo)
        lo.location = (0.0, -0.4, 1.79)
        lights.append(lo)
        cylinder("Flex", 0.003, 0.7, (0.0, -0.4, 1.83), M.plastic("Flex", "#1a1a1a", 0.5), col, 8)

    ctx.sun_window = dict(centre=(gx, sky["y"], gz), bottom=gz - 0.25, top=gz + 0.25)
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd,
        rack_point=Vector((-0.75, 0.6, 0.12)), tilt_from=Vector((gx, sky["y"], gz - 0.2)),
        pan_from=Vector((trunk_loc.x - 0.18, trunk_loc.y - 0.05, inside_z)), reveal_target=trunk_loc + Vector((0, 0, 0.3)),
        min_height=th + 0.06,
    )
    room = Room(Vector((-W / 2, -D / 2, 0)), Vector((W / 2, D / 2, RIDGE)))
    dust_box = (Vector((-1.2, -1.2, 0.1)), Vector((1.2, 1.2, 2.0)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
