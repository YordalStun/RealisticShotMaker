"""Study desk by the window: an old wooden writing desk in a family home."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..util import add_bevel, box, cylinder
from .common import (Ctx, Room, aim_sun_through, curtain, outdoor_backdrop, place_card, scatter_prints, wall,
                     window)

DESK_Z = 0.76


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))

    # ------------------------------------------------------------------ room shell
    X0, X1, Y0, Y1, H = -2.2, 2.0, -2.4, 2.3, 2.6
    plaster = M.plaster("Walls", "#d6cbb6", rough=0.88, bump=1.0, stains=0.25)
    ceiling = M.plaster("Ceiling", "#e9e4da", rough=0.9, bump=0.5, stains=0.1)
    floor = M.wood("Floorboards", "oak", varnish=0.45, wear=0.6, dust=0.15, scale=1.0, grain_axis="Y",
                   planks=(1.8, 0.14))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, ((X0 + X1) / 2, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, ((X0 + X1) / 2, (Y0 + Y1) / 2, H + 0.025), ceiling, col)
    # back wall (behind the desk) with the main window
    back_win = dict(c=-0.45, w=1.35, b=0.86, t=2.2)
    wall("BackWall", col, plaster, "y", Y1, X0, X1, 0, H, openings=[(back_win["c"], back_win["w"], back_win["b"], back_win["t"])])
    window("BackWindow", col, "y", Y1, back_win["c"], back_win["w"], back_win["b"], back_win["t"], inward=-1, panes=(3, 3))
    curtain("CurtainL", col, "y", Y1, back_win["c"] - back_win["w"] / 2 - 0.12, 0.5, 0.25, 2.45, -1, sheer=0.6)
    curtain("CurtainR", col, "y", Y1, back_win["c"] + back_win["w"] / 2 + 0.12, 0.5, 0.25, 2.45, -1, sheer=0.6)
    # left wall with the side window the sun comes through
    side_win = dict(c=-0.75, w=1.1, b=0.8, t=2.05)  # forward of the desk: sun rakes across the print
    wall("LeftWall", col, plaster, "x", X0, Y0, Y1, 0, H, openings=[(side_win["c"], side_win["w"], side_win["b"], side_win["t"])])
    window("SideWindow", col, "x", X0, side_win["c"], side_win["w"], side_win["b"], side_win["t"], inward=1, panes=(2, 3))
    curtain("CurtainS", col, "x", X0, side_win["c"] + side_win["w"] / 2 + 0.15, 0.45, 0.2, 2.4, 1, sheer=0.6,
            color="#cfc3a8")
    wall("RightWall", col, plaster, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, plaster, "y", Y0, X0, X1, 0, H)
    # skirting boards
    skirt = M.wood("Skirting", "painted_white", varnish=0.3, wear=0.3)
    box("SkirtBack", X1 - X0, 0.02, 0.12, ((X0 + X1) / 2, Y1 - 0.07, 0.06), skirt, col, bevel=0.003)
    box("SkirtLeft", 0.02, Y1 - Y0, 0.12, (X0 + 0.07, (Y0 + Y1) / 2, 0.06), skirt, col, bevel=0.003)

    # outdoor world behind both windows
    outdoor_backdrop(col, Vector((back_win["c"], Y1, 0)), Vector((0, 1, 0)), rng, distance=7.0)
    # the sun comes through the side window, so keep its path clear: lawn only, distant trees off-axis
    outdoor_backdrop(col, Vector((X0, side_win["c"], 0)), Vector((-1, 0, 0)), rng, distance=6.0, trees=0, hedge=False)

    # ------------------------------------------------------------------ desk
    walnut = M.wood("DeskTop", "walnut", varnish=0.65, wear=0.45, dust=0.05, scale=1.0, grain_axis="X", seed=1.7)
    carcass = M.wood("DeskBody", "walnut", varnish=0.55, wear=0.3, scale=1.0, grain_axis="Z", seed=3.1)
    top = box("DeskTop", 1.5, 0.78, 0.034, (0, 0.39, DESK_Z - 0.017), walnut, col, bevel=0.006, segments=4)
    # apron, drawers and legs
    box("DeskApron", 1.42, 0.7, 0.1, (0, 0.4, DESK_Z - 0.085), carcass, col, bevel=0.003)
    brass = M.metal("DrawerBrass", "#b8924e", rough=0.3, smudge=0.6, tarnish=0.5)
    for i, x in enumerate((-0.45, 0.0, 0.45)):
        box(f"Drawer{i}", 0.4, 0.012, 0.08, (x, 0.045, DESK_Z - 0.085), carcass, col, bevel=0.004)
        cylinder(f"Knob{i}", 0.009, 0.014, (x, 0.04, DESK_Z - 0.085), brass, col, 24, rot=(math.radians(90), 0, 0))
    for i, (x, y) in enumerate(((-0.68, 0.08), (0.68, 0.08), (-0.68, 0.72), (0.68, 0.72))):
        leg = box(f"Leg{i}", 0.05, 0.05, DESK_Z - 0.13, (x, y, (DESK_Z - 0.13) / 2), carcass, col, bevel=0.004)
    # a leather writing mat
    box("DeskMat", 0.62, 0.42, 0.003, (0.02, 0.3, DESK_Z + 0.0015), M.leather("DeskMat", "#3a2a20", 0.55, 0.6), col,
        bevel=0.0015)
    surf = DESK_Z + 0.003

    # ------------------------------------------------------------------ the hero print
    placement = s.get("placement", "leaning")
    if ctx.spec["camera"]["move"] == "top_down" and placement == "leaning":
        placement = "flat"
    hero_meta = ctx.job["polaroid"]
    extras = ctx.job.get("extra_prints", [])
    anchor = Vector((0.02, 0.27, surf))
    card_w, card_h = hero_meta["card_mm"][0] / 1000.0, hero_meta["card_mm"][1] / 1000.0
    lean = 17.0
    if placement == "leaning":
        # pencil pot behind the print acts as the support
        pot_r = 0.036
        pot_y = anchor.y + card_h * math.sin(math.radians(lean)) + pot_r + 0.002
        P.pencil_pot("PencilPot", col, (anchor.x + 0.012, pot_y, surf), style="ceramic", color="#2f4f5d", rng=rng,
                     radius=pot_r, height=card_h * math.cos(math.radians(lean)) + 0.004)
        hero, centre, normal = place_card(hero_meta, "HeroPrint", col, anchor, math.radians(rng.uniform(-6, 6)),
                                          "leaning", lean)
        view_dir = Vector((0.08, -1.0, 0.0)).normalized()
        el = 4.0
    else:
        base_z = surf
        if placement == "pile" and extras:
            pile = extras[: max(3, len(extras) // 2)]
            scatter_prints(pile, col, anchor, 0.03, rng, surf, prefix="Pile", stack=True)
            base_z = surf + len(pile) * 0.0013
            extras = extras[len(pile):]
        hero, centre, normal = place_card(hero_meta, "HeroPrint", col, Vector((anchor.x, anchor.y, base_z)),
                                          math.radians(rng.uniform(-12, 12)), "flat")
        P.pencil_pot("PencilPot", col, (anchor.x + 0.17, anchor.y + 0.2, surf), style="ceramic", color="#2f4f5d",
                     rng=rng)
        view_dir = Vector((0.1, -1.0, 0.0)).normalized()
        el = 34.0
    # apparent height of the print for framing
    vd = Vector((view_dir.x, view_dir.y, 0)).normalized()
    vd = Vector((vd.x * math.cos(math.radians(el)), vd.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))

    # ------------------------------------------------------------------ props
    lights = []
    on = ctx.lights_on
    lamp, lamp_light = P.bankers_lamp("Lamp", col, (-0.5, 0.58, surf), math.radians(12), on=on, power=7.0)
    if lamp_light:
        lights.append(lamp_light)
    frame_imgs = ctx.job.get("frame_photos", [])
    frame = P.picture_frame("Frame", col, (0.24, 0.6, surf), math.radians(-14),
                            frame_imgs[0] if frame_imgs else None, size=(0.15, 0.2), wood_preset="walnut")
    rack_point = Vector((0.24, 0.6, surf + 0.1))
    if clutter > 0.15:
        P.mug("Mug", col, (-0.27, 0.07, surf), math.radians(rng.uniform(0, 360)), color="#6c8a7e")
        P.book_stack("Books", col, (0.5, 0.42, surf), count=3 + int(clutter * 2), rng=rng, rot_z=math.radians(8))
    if clutter > 0.35:
        P.reading_glasses("Glasses", col, (0.23, 0.08, surf), math.radians(-25))
        P.letter_pile("Letters", col, (-0.18, 0.33, surf), count=3, rng=rng)
    if clutter > 0.55:
        P.fountain_pen("Pen", col, (0.11, 0.13, surf), math.radians(70))
        P.potted_plant("Plant", col, (0.62, 0.62, surf), rng=rng)
        if len(frame_imgs) > 1:
            P.picture_frame("Frame2", col, (-0.15, 0.68, surf), math.radians(10), frame_imgs[1], size=(0.1, 0.13),
                            wood_preset="mahogany", lean=10.0)
    if s.get("extra_photos", True) and extras:
        scatter_prints(extras[:3], col, Vector((anchor.x, anchor.y - 0.05, surf)), 0.24, rng, surf,
                       avoid=Vector((anchor.x, anchor.y, surf)), avoid_r=0.12)

    # bookcase in the background (right of the window)
    bc_wood = M.wood("Bookcase", "oak", varnish=0.5, wear=0.4, scale=1.0, grain_axis="X", seed=5.5)
    bx, by = 1.25, Y1 - 0.2
    box("BookcaseSideL", 0.025, 0.32, 2.0, (bx - 0.45, by, 1.0), bc_wood, col, bevel=0.003)
    box("BookcaseSideR", 0.025, 0.32, 2.0, (bx + 0.45, by, 1.0), bc_wood, col, bevel=0.003)
    for k, z in enumerate((0.05, 0.45, 0.85, 1.25, 1.65, 2.0)):
        box(f"Shelf{k}", 0.9, 0.32, 0.025, (bx, by, z), bc_wood, col, bevel=0.003)
        if 0 < k < 5:
            x = bx - 0.42
            while x < bx + 0.4:
                bw = rng.uniform(0.022, 0.05)
                bh = rng.uniform(0.2, 0.32)
                col_hex = rng.choice(P.BOOK_COLOURS)
                b = box(f"ShelfBook{k}", bw, 0.2, bh, (x + bw / 2, by + rng.uniform(-0.02, 0.02), z + 0.0125 + bh / 2),
                        M.fabric(f"Spine{col_hex}", col_hex, 2600, 0.75, 0.2), col, bevel=0.002)
                if rng.random() < 0.12:
                    b.rotation_euler = (0, math.radians(rng.uniform(5, 14)), 0)
                x += bw + 0.002
    # evening/night: a floor lamp in the far corner gives background bokeh
    if on:
        fl_root, fl_light = P.bankers_lamp("CornerLamp", col, (1.7, 1.6, 0.9), 0.0, on=True, power=10.0)
        if fl_light:
            lights.append(fl_light)
        box("CornerTable", 0.4, 0.4, 0.9, (1.7, 1.6, 0.45), carcass, col, bevel=0.005)

    # sun aiming through the side window
    ctx.sun_window = dict(centre=(X0, side_win["c"], (side_win["b"] + side_win["t"]) / 2), bottom=side_win["b"],
                          top=side_win["t"])
    back_window_centre = Vector((back_win["c"], Y1, (back_win["b"] + back_win["t"]) / 2))

    anchors = Anchors(
        subject=centre,
        card_normal=normal,
        card_height=apparent,
        view_dir=vd,
        rack_point=rack_point,
        tilt_from=back_window_centre + Vector((0.3, 0, -0.2)),
        pan_from=Vector((-0.27, 0.07, surf + 0.06)),
        reveal_target=Vector((0.0, 0.5, surf + 0.12)),
        min_height=surf + 0.012,
    )
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-0.9, -0.3, surf)), Vector((0.9, 1.4, surf + 0.9)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
