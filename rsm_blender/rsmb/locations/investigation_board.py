"""Investigation board: a see-through glass incident board in a detective's office at night.

The camera looks at the board; the office behind it is seen *through* the glass, so desks, screens,
lamps and the light through the blinds melt into bokeh behind the photos.
"""
from __future__ import annotations

import math
import os

import bmesh
import bpy
from mathutils import Euler, Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..polaroid_obj import build_card, image_centre_local
from ..util import Nodes, box, cylinder, link, mesh_object, new_material, srgb
from ..world import kelvin_rgb
from .common import Ctx, Room, opt, wall

BOARD_W, BOARD_H, BOARD_Z = 1.9, 1.15, 1.42   # board size and the height of its centre
GLASS_T = 0.010

STRING_COLOURS = {"red": "#b3121b", "yellow": "#d8a412", "white": "#e8e4dc"}

NOTES = ["WHO TOOK THIS?", "last seen 14:20", "Summer '98", "alibi?", "same car?", "Fri 9th", "CHECK!",
         "pier → station", "2nd witness", "why here?"]


# ---------------------------------------------------------------------------
# Materials specific to this set
# ---------------------------------------------------------------------------

def _marker_ink(name, hexc):
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.35)
    b.inputs["Base Color"].default_value = srgb(hexc)
    tc = n.new("ShaderNodeTexCoord")
    streak = n.new("ShaderNodeTexNoise", Scale=900.0, Detail=2.0)
    n.link(tc, "Object", streak, "Vector")
    # dry-erase ink is slightly streaky and not fully opaque
    a = n.ramp((streak, "Fac"), [(0.2, (0.75, 0.75, 0.75)), (0.8, (0.98, 0.98, 0.98))])
    n.link(a, "Color", b, "Alpha")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    return mat


def _screen(name, hue="#3a6ea8", strength=3.0, seed=0.0):
    """A computer screen: a dim app layout with lines of text-like detail."""
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping", Location=(seed, seed * 0.3, 0))
    n.link(tc, "Generated", mp, "Vector")
    rows = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="Y", Scale=60.0)
    n.link(mp, None, rows, "Vector")
    words = n.new("ShaderNodeTexNoise", Scale=40.0, Detail=1.0)
    n.link(mp, None, words, "Vector")
    text = n.math("MULTIPLY", n.math("GREATER_THAN", (rows, "Fac"), 0.65), n.math("GREATER_THAN", (words, "Fac"), 0.48))
    panel = n.new("ShaderNodeTexGradient")
    n.link(mp, None, panel, "Vector")
    base = n.ramp((panel, "Fac"), [(0.0, srgb("#0d1622")), (1.0, srgb(hue))])
    col = n.mix("RGBA", n.math("MULTIPLY", text, 0.6), (base, "Color"), srgb("#d8e4f0"))
    em = n.new("ShaderNodeEmission", Strength=strength)
    n.link(col, None, em, "Color")
    gl = n.new("ShaderNodeBsdfPrincipled", Roughness=0.08)
    gl.inputs["Base Color"].default_value = (0, 0, 0, 1)
    add = n.new("ShaderNodeAddShader")
    n.link(em, None, add, 0)
    n.link(gl, None, add, 1)
    out = n.new("ShaderNodeOutputMaterial")
    n.link(add, None, out, "Surface")
    return mat


def _cork():
    mat = new_material("Cork")
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    v = n.new("ShaderNodeTexVoronoi", Scale=900.0)
    n.link(tc, "Object", v, "Vector")
    nz = n.new("ShaderNodeTexNoise", Scale=300.0, Detail=4.0)
    n.link(tc, "Object", nz, "Vector")
    col = n.ramp((nz, "Fac"), [(0.3, srgb("#8a5f38")), (0.7, srgb("#c4925c"))])
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.9)
    n.link(col, "Color", b, "Base Color")
    bump = n.new("ShaderNodeBump", Strength=0.6, Distance=0.0006)
    n.link(v, "Distance", bump, "Height")
    n.link(bump, None, b, "Normal")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    return mat


def _string_mat(hexc):
    mat = new_material(f"String_{hexc}")
    n = Nodes(mat.node_tree)
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.8)
    b.inputs["Base Color"].default_value = srgb(hexc)
    b.inputs["Sheen Weight"].default_value = 0.8
    b.inputs["Subsurface Weight"].default_value = 0.2
    tc = n.new("ShaderNodeTexCoord")
    twist = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="DIAGONAL", Scale=600.0)
    n.link(tc, "Object", twist, "Vector")
    bump = n.new("ShaderNodeBump", Strength=0.6, Distance=0.0002)
    n.link(twist, "Fac", bump, "Height")
    n.link(bump, None, b, "Normal")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    return mat


# ---------------------------------------------------------------------------
# Board furniture
# ---------------------------------------------------------------------------

def _text(col, body, font, size, loc, rot, mat, name="Note"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if font:
        cu.font = font
    cu.size = size
    cu.align_x = "CENTER"
    cu.extrude = 0.00008
    o = bpy.data.objects.new(name, cu)
    link(o, col)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    return o


def _stroke(col, pts, width, mat, name="Stroke"):
    """A flat marker stroke along a polyline on the glass (XZ plane, facing -Y)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    y0 = pts[0].y
    for k, p in enumerate(pts):
        sp.points[k].co = (p.x, 0.0, p.z, 1)
    cu.bevel_depth = width / 2
    cu.bevel_resolution = 1
    o = bpy.data.objects.new(name, cu)
    link(o, col)
    o.location = (0.0, y0, 0.0)
    o.scale = (1.0, 0.08, 1.0)  # flatten against the glass (around the glass plane, not the world origin)
    o.data.materials.append(mat)
    return o


def _magnet(col, at: Vector, colour="#d8d4cc", name="Magnet"):
    m = cylinder(name, 0.009, 0.006, (at.x, at.y - 0.006, at.z), M.plastic(f"Magnet{colour}", colour, 0.25, 0.6), col,
                 32, bevel=0.0015, rot=(math.radians(90), 0, 0))
    return m


def _tape(col, centre: Vector, angle: float, length=0.045, name="Tape"):
    mat = bpy.data.materials.get("ClearTape")
    if mat is None:
        mat = new_material("ClearTape")
        n = Nodes(mat.node_tree)
        b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.18)
        b.inputs["Base Color"].default_value = (0.95, 0.93, 0.85, 1)
        b.inputs["Transmission Weight"].default_value = 0.85
        b.inputs["Alpha"].default_value = 0.6
        out = n.new("ShaderNodeOutputMaterial")
        n.link(b, None, out, "Surface")
    t = box(name, length, 0.0003, 0.019, (centre.x, centre.y - 0.0004, centre.z), mat, col)
    t.rotation_euler = (0, angle, 0)
    return t


def _paper_item(col, kind, at: Vector, size, roll, rng, name):
    """Index cards, sticky notes, clippings and a map, stuck flat to the board."""
    w, h = size
    if kind == "sticky":
        mat = M.paper(f"{name}_mat", rng.choice(["#f2e46a", "#f5b0c4", "#9fd8e8"]), 0.6, 0.1, ink_lines=True,
                      line_color="#1d2a6a")
    elif kind == "clipping":
        mat = M.paper(f"{name}_mat", "#e3dcc8", 0.8, 0.7, ink_lines=True, line_color="#2a2a2a")
    elif kind == "map":
        mat = M.paper(f"{name}_mat", "#e8e0c4", 0.7, 0.5, ink_lines=True, line_color="#6a8aa8")
    else:
        mat = M.paper(f"{name}_mat", "#f1ede2", 0.65, 0.2, ink_lines=True, line_color="#1f2a5a")
    o = box(name, w, 0.0004, h, (at.x, at.y - 0.0005, at.z), mat, col)
    o.rotation_euler = (0, roll, 0)
    return o


def _pin_print(meta, name, col, centre: Vector, roll: float, face_y: float):
    """Stick an instant print flat on the board (front face towards -Y)."""
    obj = build_card(meta, name, col)
    w_mm, h_mm = meta["card_mm"]
    obj.rotation_euler = Euler((0.0, roll, 0.0), "XYZ")
    # card origin is its bottom-centre edge: shift down so `centre` is the card centre
    # rotating about Y maps the card's (0, 0, h/2) to (h/2·sin, 0, h/2·cos)
    obj.location = (centre.x - math.sin(roll) * h_mm / 2000.0, face_y, centre.z - math.cos(roll) * h_mm / 2000.0)
    bpy.context.view_layer.update()
    from .common import register_print
    register_print(obj, meta, obj.matrix_world @ image_centre_local(meta), Vector((0, -1, 0)), hero=name == "HeroPrint")
    return obj


# ---------------------------------------------------------------------------
# Office behind the board
# ---------------------------------------------------------------------------

def _desk(col, at: Vector, rot, rng, monitors_on: bool, lamp_on: bool, idx: int):
    root = bpy.data.objects.new(f"Desk{idx}", None)
    link(root, col)
    root.location = at
    root.rotation_euler = (0, 0, rot)
    top_mat = M.wood(f"DeskTop{idx}", "oak", 0.5, 0.6, grain_axis="X", seed=idx * 1.7)
    steel = M.metal("DeskSteel", "#6c7277", 0.35, 0.4, 0.1)
    parts = [box(f"DeskTop{idx}", 1.4, 0.75, 0.03, (0, 0, 0.74), top_mat, col, bevel=0.004),
             box(f"DeskPedestal{idx}", 0.42, 0.7, 0.71, (0.45, 0, 0.355), steel, col, bevel=0.004)]
    for k in range(3):
        parts.append(box(f"DeskDrawer{idx}{k}", 0.4, 0.01, 0.2, (0.45, -0.355, 0.12 + k * 0.23), steel, col, bevel=0.003))
    for x in (-0.66,):
        for y in (-0.33, 0.33):
            parts.append(box(f"DeskLeg{idx}", 0.04, 0.04, 0.72, (x, y, 0.36), steel, col))
    for o in parts:
        o.parent = root
    # monitors
    for k in range(2 if rng.random() < 0.6 else 1):
        mx = -0.22 + k * 0.5
        bezel = box(f"Monitor{idx}{k}", 0.56, 0.03, 0.34, (mx, 0.12, 1.02), M.plastic("Bezel", "#16171a", 0.3, 0.4), col,
                    bevel=0.006)
        stand = box(f"MonStand{idx}{k}", 0.05, 0.05, 0.16, (mx, 0.15, 0.83), M.plastic("Bezel", "#16171a", 0.3, 0.4), col)
        base = box(f"MonBase{idx}{k}", 0.22, 0.16, 0.012, (mx, 0.12, 0.76), M.plastic("Bezel", "#16171a", 0.3, 0.4), col,
                   bevel=0.004)
        scr_mat = _screen(f"Screen{idx}{k}", rng.choice(["#3a6ea8", "#2f7a6a", "#5a5aa8"]), 3.5 if monitors_on else 0.0,
                          seed=rng.uniform(0, 10))
        scr = box(f"Screen{idx}{k}", 0.53, 0.002, 0.31, (mx, 0.104, 1.02), scr_mat, col)
        for o in (bezel, stand, base, scr):
            o.parent = root
        kb = box(f"Keyboard{idx}{k}", 0.44, 0.15, 0.022, (mx, -0.18, 0.765), M.plastic("Keys", "#222326", 0.5), col,
                 bevel=0.004)
        kb.parent = root
    # case files and a mug
    for k in range(rng.randint(2, 5)):
        f = box(f"Folder{idx}{k}", 0.24, 0.31, 0.012, (-0.45 + rng.uniform(-0.05, 0.05), -0.1 + rng.uniform(-0.05, 0.05),
                                                       0.762 + k * 0.013),
                M.paper(f"Manila{k % 3}", ["#d9b77a", "#c9a868", "#b8946a"][k % 3], 0.8, 0.5), col, bevel=0.002)
        f.rotation_euler = (0, 0, rng.uniform(-0.3, 0.3))
        f.parent = root
    m = P.mug(f"DeskMug{idx}", col, (0.25, -0.2, 0.755), rng.uniform(0, 6.28), rng.choice(["#e8e4dc", "#2f3e52", "#8c2f2f"]),
              coffee=0.4)
    m.parent = root
    light = None
    if lamp_on:
        lamp, light = P.bankers_lamp(f"DeskLamp{idx}", col, (0.55, 0.15, 0.755), math.radians(rng.uniform(-30, 30)),
                                     on=True, power=6.0)
        lamp.parent = root
    return root, light


def _blinds_window(col, x0, x1, z0, z1, y_wall, rng, light_on: bool):
    """A window with Venetian blinds; a sodium street light outside throws stripes through them."""
    w = x1 - x0
    frame = M.metal("WinFrame", "#c9ccce", 0.35, 0.2, 0.05)
    for (sx, sz, cx, cz) in ((w, 0.04, (x0 + x1) / 2, z0), (w, 0.04, (x0 + x1) / 2, z1), (0.04, z1 - z0, x0, (z0 + z1) / 2),
                             (0.04, z1 - z0, x1, (z0 + z1) / 2)):
        box("WinFrame", sx, 0.06, sz, (cx, y_wall - 0.03, cz), frame, col)
    g = box("WinGlass", w, 0.006, z1 - z0, ((x0 + x1) / 2, y_wall, (z0 + z1) / 2), M.glass("OfficeGlass", "#f2f6f6", 0.0),
            col)
    g.visible_shadow = False
    slat_mat = M.metal("Slat", "#d8d6cf", 0.4, 0.3, 0.05)
    bm = bmesh.new()
    n = int((z1 - z0) / 0.025)
    for i in range(n):
        z = z0 + 0.012 + i * 0.025
        ret = bmesh.ops.create_cube(bm, size=1.0)
        for v in ret["verts"]:
            v.co.x *= w - 0.02
            v.co.y *= 0.025
            v.co.z *= 0.0008
            # tilt the slat 35 degrees
            y, zz = v.co.y, v.co.z
            a = math.radians(35)
            v.co.y = y * math.cos(a) - zz * math.sin(a)
            v.co.z = y * math.sin(a) + zz * math.cos(a)
            v.co += Vector(((x0 + x1) / 2, y_wall - 0.07, z))
    mesh_object("Blinds", bm, col, mat=slat_mat)
    if light_on:
        ld = bpy.data.lights.new("StreetLamp", "SPOT")
        ld.energy = 2600
        ld.spot_size = math.radians(40)
        ld.spot_blend = 0.3
        ld.shadow_soft_size = 0.08
        ld.color = kelvin_rgb(2000)
        o = bpy.data.objects.new("StreetLamp", ld)
        link(o, col)
        o.location = ((x0 + x1) / 2 + 1.2, y_wall + 3.0, z1 + 2.2)
        target = Vector(((x0 + x1) / 2 - 0.8, y_wall - 2.6, 0.6))
        o.rotation_euler = (target - o.location).to_track_quat("-Z", "Y").to_euler()
        return o
    return None


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))
    board_kind = opt(ctx, "board", "glass")
    string_on = bool(opt(ctx, "string", True))
    string_hex = STRING_COLOURS.get(opt(ctx, "string_color", "red"), "#b3121b")
    room_lights = opt(ctx, "room_lights", "off") == "on"
    spotlight = bool(opt(ctx, "spotlight", True))
    monitors_on = bool(opt(ctx, "monitors", True))
    blinds_on = bool(opt(ctx, "blinds", True))
    notes_on = bool(opt(ctx, "marker_notes", True))

    font = None
    fdir = ctx.job["paths"].get("fonts") or os.path.join(os.path.dirname(__file__), "..", "..", "..", "rsm", "assets",
                                                          "fonts")
    for fname in ("ShadowsIntoLight.ttf", "Caveat.ttf"):
        fp = os.path.join(fdir, fname)
        if os.path.exists(fp):
            font = bpy.data.fonts.load(fp, check_existing=True)
            break

    # ------------------------------------------------------------------ office shell
    X0, X1, Y0, Y1, H = -3.0, 3.0, -3.2, 3.6, 2.8
    paint = M.plaster("OfficeWalls", "#a9b2a4", rough=0.7, bump=0.6, stains=0.35)
    carpet = M.fabric("Carpet", "#3c3f44", threads_per_m=500, rough=0.95, sheen=0.2)
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), carpet, col)
    tiles = M.plaster("CeilingTiles", "#d9d6cc", rough=0.95, bump=1.5, stains=0.3)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), tiles, col)
    win = dict(x0=-2.2, x1=-0.4, z0=0.95, z1=2.25)
    wall("BackWall", col, paint, "y", Y1, X0, X1, 0, H, openings=[((win["x0"] + win["x1"]) / 2, win["x1"] - win["x0"],
                                                                  win["z0"], win["z1"])])
    wall("LeftWall", col, paint, "x", X0, Y0, Y1, 0, H)
    wall("RightWall", col, paint, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, paint, "y", Y0, X0, X1, 0, H)
    lights = []
    street = _blinds_window(col, win["x0"], win["x1"], win["z0"], win["z1"], Y1, rng, blinds_on)
    # the street outside: dark buildings with a few lit windows (bokeh through the blinds)
    for i in range(8):
        bx_ = rng.uniform(-6, 4)
        b_ = box(f"Building{i}", rng.uniform(2, 5), 2.0, rng.uniform(6, 14), (bx_, Y1 + rng.uniform(10, 22), 3.0),
                 M.plaster("BuildingConcrete", "#2a2c30", 0.9, 0.5, 0.2), col)
        for k in range(6):
            wz = rng.uniform(1.5, 9)
            wx = bx_ + rng.uniform(-1.5, 1.5)
            box(f"LitWindow{i}{k}", 0.6, 0.05, 0.8, (wx, b_.location.y - 1.03, wz),
                M.emitter(f"WinGlow{k % 3}", rng.choice([2600, 3200, 4500]), rng.uniform(1.5, 4)), col)
    # ceiling fluorescent panels
    panel_mat = M.emitter("Fluorescent", 4300, 9.0 if room_lights else 0.0)
    for i, (px, py) in enumerate(((-1.5, 1.2), (1.5, 1.2), (-1.5, -1.2), (1.5, -1.2), (0, 2.6))):
        box(f"Panel{i}", 1.2, 0.6, 0.02, (px, py, H - 0.01), panel_mat, col)
        if room_lights:
            ld = bpy.data.lights.new(f"PanelLight{i}", "AREA")
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = 1.2, 0.6
            ld.energy = 120
            ld.color = kelvin_rgb(4300)
            o = bpy.data.objects.new(f"PanelLight{i}", ld)
            link(o, col)
            o.location = (px, py, H - 0.03)
            lights.append(o)
    # an exit sign glowing green over the door
    box("ExitSign", 0.36, 0.06, 0.16, (2.4, Y1 - 0.04, 2.35), M.emitter("ExitGlow", 6500, 0.0), col)
    exit_face = box("ExitFace", 0.32, 0.004, 0.12, (2.4, Y1 - 0.072, 2.35), M.emitter("ExitGreen", 6500, 6.0), col)
    exit_face.data.materials.clear()
    em = new_material("ExitGreenMat")
    nn = Nodes(em.node_tree)
    e = nn.new("ShaderNodeEmission", Strength=8.0)
    e.inputs["Color"].default_value = srgb("#1fcf6a")
    o_ = nn.new("ShaderNodeOutputMaterial")
    nn.link(e, None, o_, "Surface")
    exit_face.data.materials.append(em)
    # wall clock
    clock = cylinder("WallClock", 0.17, 0.04, (1.2, Y1 - 0.06, 2.1), M.plastic("ClockRim", "#1b1b1b", 0.3, 0.3), col, 64,
                     bevel=0.01, rot=(math.radians(90), 0, 0))
    cylinder("WallClockFace", 0.155, 0.002, (1.2, Y1 - 0.082, 2.1), M.paper("ClockFace", "#f3efe6", 0.4, 0.1), col, 64,
             rot=(math.radians(90), 0, 0))
    # filing cabinets along the right wall
    steel = M.metal("Cabinet", "#7d8388", 0.3, 0.5, 0.2)
    for i in range(3):
        cab = box(f"Cabinet{i}", 0.47, 0.62, 1.32, (X1 - 0.35, 0.6 + i * 0.5, 0.66), steel, col, bevel=0.004)
        cab.rotation_euler = (0, 0, math.radians(90))
        for k in range(4):
            box(f"CabDrawer{i}{k}", 0.012, 0.42, 0.28, (X1 - 0.66, 0.6 + i * 0.5, 0.18 + k * 0.32), steel, col, bevel=0.003)
            box(f"CabHandle{i}{k}", 0.02, 0.1, 0.02, (X1 - 0.675, 0.6 + i * 0.5, 0.28 + k * 0.32),
                M.metal("Chrome", "#d6d6d6", 0.15, 0.4, 0.05), col, bevel=0.004)
    # desks behind the board (seen through the glass)
    for i, (dx, dy, rot) in enumerate(((-1.1, 2.2, 0.0), (1.0, 2.0, math.radians(8)), (-0.2, 3.0, math.radians(180)))):
        if i > 0 and clutter < 0.3:
            break
        d, l_ = _desk(col, Vector((dx, dy, 0)), rot, rng, monitors_on, lamp_on=(i == 1), idx=i)
        if l_:
            lights.append(l_)
        chair = box(f"Chair{i}", 0.5, 0.5, 0.08, (dx, dy - 0.6 if rot < 1 else dy + 0.6, 0.48),
                    M.leather("ChairSeat", "#1d1d1f", 0.5, 0.3), col, bevel=0.03, segments=4)
        box(f"ChairBack{i}", 0.48, 0.07, 0.55, (dx, dy - 0.85 if rot < 1 else dy + 0.85, 0.82),
            M.leather("ChairSeat", "#1d1d1f", 0.5, 0.3), col, bevel=0.03, segments=4)
    # a monitor glow light so screens actually light the desks
    if monitors_on:
        for i, (dx, dy) in enumerate(((-1.1, 2.0), (1.0, 1.8))):
            ld = bpy.data.lights.new(f"ScreenGlow{i}", "AREA")
            ld.size = 0.5
            ld.energy = 6
            ld.color = (0.55, 0.7, 1.0)
            o = bpy.data.objects.new(f"ScreenGlow{i}", ld)
            link(o, col)
            o.location = (dx, dy, 1.05)
            o.rotation_euler = (math.radians(-90), 0, 0)

    # ------------------------------------------------------------------ the board
    by = 0.0
    face_y = by - GLASS_T / 2   # front surface of the glass
    if board_kind == "glass":
        glass = M.glass("BoardGlass", "#eef6f2", 0.0, 1.52, smudge=0.5)
        g = box("BoardGlass", BOARD_W, GLASS_T, BOARD_H, (0, by, BOARD_Z), glass, col, bevel=0.002)
        chrome = M.metal("Standoff", "#d9d9d9", 0.12, 0.3, 0.02)
        alu = M.metal("Aluminium", "#b9bcbf", 0.3, 0.3, 0.05, brushed=True)
        for sx in (-1, 1):
            box("BoardPost", 0.05, 0.05, BOARD_Z + BOARD_H / 2 + 0.1, (sx * (BOARD_W / 2 + 0.04), by + 0.04,
                                                                       (BOARD_Z + BOARD_H / 2 + 0.1) / 2), alu, col, bevel=0.004)
            box("BoardFoot", 0.06, 0.62, 0.04, (sx * (BOARD_W / 2 + 0.04), by + 0.04, 0.07), alu, col, bevel=0.004)
            for fy in (-0.26, 0.26):
                cylinder("Caster", 0.035, 0.03, (sx * (BOARD_W / 2 + 0.04), by + 0.04 + fy, 0.035),
                         M.plastic("Caster", "#151515", 0.4), col, 24, rot=(0, math.radians(90), 0))
            for sz in (-1, 1):
                cylinder("Standoff", 0.012, 0.05, (sx * (BOARD_W / 2 - 0.05), by - 0.03, BOARD_Z + sz * (BOARD_H / 2 - 0.05)),
                         chrome, col, 32, bevel=0.002, rot=(math.radians(90), 0, 0))
    else:
        cork = _cork()
        box("Cork", BOARD_W, 0.012, BOARD_H, (0, by, BOARD_Z), cork, col)
        frame = M.metal("CorkFrame", "#b9bcbf", 0.3, 0.3, 0.05, brushed=True)
        for (sx, sz, cx, cz) in ((BOARD_W + 0.04, 0.025, 0, BOARD_Z + BOARD_H / 2), (BOARD_W + 0.04, 0.025, 0, BOARD_Z - BOARD_H / 2),
                                 (0.025, BOARD_H, -BOARD_W / 2, BOARD_Z), (0.025, BOARD_H, BOARD_W / 2, BOARD_Z)):
            box("CorkFrame", sx, 0.03, sz, (cx, by - 0.004, cz), frame, col, bevel=0.003)
        for sx in (-1, 1):
            box("EaselLeg", 0.04, 0.04, BOARD_Z + BOARD_H / 2, (sx * (BOARD_W / 2 - 0.1), by + 0.05, (BOARD_Z + BOARD_H / 2) / 2),
                M.wood("Easel", "pine", 0.3, 0.4, grain_axis="Z"), col, bevel=0.004)
        face_y = by - 0.006

    # hero print, slightly off centre and a little crooked
    meta = ctx.job["polaroid"]
    w_mm, h_mm = meta["card_mm"]
    hero_c = Vector((-0.12, face_y - 0.0012, BOARD_Z + 0.04))
    hero_roll = math.radians(rng.uniform(-5, 5))
    hero = _pin_print(meta, "HeroPrint", col, hero_c, hero_roll, face_y - 0.0012)
    centre = hero.matrix_world @ image_centre_local(meta)
    normal = Vector((0, -1, 0))
    _tape(col, hero_c + Vector((0, -0.002, h_mm / 2000.0 - 0.004)), rng.uniform(-0.3, 0.3), name="HeroTape")

    # other evidence laid out around it
    extras = ctx.job.get("extra_prints", [])
    slots = [(-0.68, 0.32), (0.42, 0.33), (0.72, -0.08), (-0.62, -0.26), (0.18, -0.3), (-0.38, 0.38), (0.75, 0.33)]
    pins = {"hero": hero_c + Vector((0, -0.006, h_mm / 2000.0 - 0.012))}
    for i, meta_e in enumerate(extras[: len(slots)]):
        sx, sz = slots[i]
        c = Vector((sx, face_y - 0.0012, BOARD_Z + sz))
        roll = math.radians(rng.uniform(-8, 8))
        _pin_print(meta_e, f"BoardPrint{i}", col, c, roll, face_y - 0.0012)
        eh = meta_e["card_mm"][1] / 2000.0
        pin = c + Vector((0, -0.006, eh - 0.012))
        pins[f"p{i}"] = pin
        if board_kind == "glass":
            _magnet(col, pin, rng.choice(["#d8d4cc", "#c8342c", "#2f5a8a"]), name=f"Magnet{i}")
        else:
            _magnet(col, pin, "#c8342c", name=f"Pin{i}")
    if board_kind == "glass":
        _magnet(col, pins["hero"], "#c8342c", name="HeroMagnet")
    papers = [("index", (-0.88, -0.05), (0.127, 0.076)), ("sticky", (0.05, 0.42), (0.076, 0.076)),
              ("sticky", (0.88, -0.36), (0.076, 0.076)), ("clipping", (0.45, -0.05), (0.14, 0.2)),
              ("map", (-0.3, -0.36), (0.3, 0.2)), ("index", (0.15, 0.12), (0.127, 0.076)),
              ("sticky", (-0.86, 0.12), (0.076, 0.076))]
    for i, (kind, (px, pz), size) in enumerate(papers):
        if clutter < 0.3 and i > 2:
            break
        c = Vector((px, face_y - 0.0006, BOARD_Z + pz))
        _paper_item(col, kind, c, size, math.radians(rng.uniform(-6, 6)), rng, f"Paper{i}")
        if kind in ("index", "clipping", "map"):
            pins[f"n{i}"] = c + Vector((0, -0.006, size[1] / 2 - 0.01))
            _magnet(col, pins[f"n{i}"], "#d8d4cc", name=f"PaperMagnet{i}")

    # string from the hero to the other evidence (slight sag, wrapped round the magnets)
    if string_on:
        smat = _string_mat(string_hex)
        links = [("hero", "p0"), ("hero", "p1"), ("hero", "p3"), ("p1", "p2"), ("hero", "n3"), ("p0", "p5"),
                 ("n4", "p3"), ("p2", "n3")]
        for i, (a_, b_) in enumerate(links):
            if a_ not in pins or b_ not in pins:
                continue
            a, b = pins[a_], pins[b_]
            cu = bpy.data.curves.new(f"String{i}", "CURVE")
            cu.dimensions = "3D"
            sp = cu.splines.new("POLY")
            steps = 12
            sp.points.add(steps)
            sag = (b - a).length * 0.015
            for k in range(steps + 1):
                t = k / steps
                p = a.lerp(b, t) - Vector((0, 0.003, sag * 4 * t * (1 - t)))
                sp.points[k].co = (p.x, p.y, p.z, 1)
            cu.bevel_depth = 0.0009
            cu.bevel_resolution = 3
            so = bpy.data.objects.new(f"String{i}", cu)
            link(so, col)
            so.data.materials.append(smat)

    # dry-erase marker notes, arrows and circles written straight on the glass
    if notes_on:
        inks = [_marker_ink("MarkerBlack", "#14161c"), _marker_ink("MarkerRed", "#b5161e"),
                _marker_ink("MarkerBlue", "#1a3a8a")]
        rot = (math.radians(90), 0, 0)
        spots = [(-0.12, 0.46), (0.62, 0.48), (-0.7, 0.05), (0.45, 0.17), (0.66, -0.47), (-0.6, -0.47), (0.0, -0.5)]
        for i, (px, pz) in enumerate(spots):
            if clutter < 0.3 and i > 2:
                break
            _text(col, rng.choice(NOTES) if i else "WHO TOOK THIS?", font, rng.uniform(0.035, 0.06),
                  (px, face_y - 0.0003, BOARD_Z + pz), (math.radians(90), math.radians(rng.uniform(-4, 4)), 0),
                  inks[i % 3], name=f"Note{i}")
        # a circle around the hero and an arrow towards it
        # hand-drawn: the loop wobbles, isn't quite closed and overshoots where it started
        ring = []
        ph = rng.uniform(0, 6.28)
        for k in range(61):
            a = ph + k / 60 * 2 * math.pi * 1.08
            wob = 1.0 + 0.05 * math.sin(a * 3.0 + ph) + 0.025 * math.sin(a * 7.0)
            ring.append(Vector((hero_c.x + math.cos(a) * (w_mm / 2000 + 0.03) * wob,
                                face_y - 0.0003, hero_c.z + math.sin(a) * (h_mm / 2000 + 0.025) * wob * (1 + k / 900))))
        _stroke(col, ring, 0.0025, inks[1], "HeroCircle")
        a0 = Vector((0.36, face_y - 0.0003, BOARD_Z + 0.25))
        a1 = Vector((hero_c.x + 0.09, face_y - 0.0003, hero_c.z + 0.07))
        _stroke(col, [a0, a0.lerp(a1, 0.5) + Vector((0, 0, 0.03)), a1], 0.0025, inks[0], "Arrow")
        _stroke(col, [a1 + Vector((0.03, 0, 0.0)), a1, a1 + Vector((0.005, 0, -0.03))], 0.0025, inks[0], "ArrowHead")

    # spotlight picking out the hero print
    if spotlight:
        ld = bpy.data.lights.new("PhotoSpot", "SPOT")
        ld.energy = 55
        ld.spot_size = math.radians(16)
        ld.spot_blend = 0.45
        ld.shadow_soft_size = 0.02
        ld.color = kelvin_rgb(3600)
        sp_o = bpy.data.objects.new("PhotoSpot", ld)
        link(sp_o, col)
        sp_o.location = (hero_c.x + 0.35, -1.6, H - 0.15)
        sp_o.rotation_euler = (hero_c - sp_o.location).to_track_quat("-Z", "Y").to_euler()
        lights.append(sp_o)
        # the track light fitting itself, up near the ceiling
        cylinder("SpotHousing", 0.04, 0.12, tuple(sp_o.location), M.plastic("SpotBlack", "#141414", 0.35, 0.2), col, 32,
                 rot=sp_o.rotation_euler)

    # a soft bounce from the room so the board isn't pitch black with everything off
    ld = bpy.data.lights.new("RoomFill", "AREA")
    ld.size = 2.5
    ld.energy = 25 if not room_lights else 0
    ld.color = (0.75, 0.82, 1.0)
    fill = bpy.data.objects.new("RoomFill", ld)
    link(fill, col)
    fill.location = (-1.2, -2.6, 2.2)
    fill.rotation_euler = (Vector((0, 0, BOARD_Z)) - fill.location).to_track_quat("-Z", "Y").to_euler()

    card_h = h_mm / 1000.0
    view = Vector((-0.22, -1.0, 0.0)).normalized()
    el = 2.0
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    other = pins.get("p1", pins["hero"] + Vector((0.5, 0, 0.2)))
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=card_h * max(0.35, abs(normal.dot(vd))), view_dir=vd,
        rack_point=Vector((0.6, 2.1, 1.05)),            # the glowing monitors behind the glass
        tilt_from=Vector((-0.12, face_y, BOARD_Z + 0.5)),
        pan_from=other + Vector((0, 0, -0.04)),          # pan along the string from another photo
        reveal_target=Vector((0, face_y, BOARD_Z)), min_height=0.3,
    )
    ctx.sun_window = None
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-1.2, -1.5, 0.6)), Vector((1.2, 1.5, 2.4)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
