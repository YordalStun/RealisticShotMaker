"""Detailed props, modelled at real-world scale (metres)."""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from . import materials as M
from .util import (add_bevel, add_subsurf, add_weighted_normals, box, cylinder, cylinder_bm, lathe, link,
                   mesh_object, set_smooth)


def _group(name, col, loc=(0, 0, 0), rot_z=0.0):
    empty = bpy.data.objects.new(name, None)
    empty.location = loc
    empty.rotation_euler = (0, 0, rot_z)
    link(empty, col)
    return empty


def _parent(obj, parent):
    obj.parent = parent
    return obj


# ---------------------------------------------------------------------------
# Writing things
# ---------------------------------------------------------------------------

PENCIL_COLOURS = ["#e2a81f", "#2b4a6b", "#8c2f2f", "#2f5a3a", "#1e1e1e", "#d9d4c4"]


def pencil(name, col, color="#e2a81f", length=0.17, sharpened=True, eraser=True, rng=None):
    """Hexagonal pencil: painted body, ferrule, eraser and a sharpened cone with graphite tip.
    Origin at the blunt end, pointing +Z."""
    rng = rng or random.Random(0)
    root = _group(name, col)
    r_body = 0.0037
    body_len = length * (0.86 if sharpened else 1.0)
    paint = M.plastic(f"{name}_paint", color, rough=0.32, coat=0.4)
    b = mesh_object(f"{name}_body", cylinder_bm(r_body, body_len, 6, True, (0, 0, body_len / 2)), col, mat=paint)
    add_bevel(b, 0.0004, 2, 30)
    _parent(b, root)
    z = body_len
    if sharpened:
        tip_len = length - body_len
        wood = M.wood(f"{name}_wood", "pine", varnish=0.0, wear=0.0, scale=4.0, grain_axis="Z")
        cone = mesh_object(f"{name}_cone", cylinder_bm(r_body * 0.98, tip_len * 0.8, 24, False,
                                                       (0, 0, z + tip_len * 0.4), radius2=0.0011), col, mat=wood)
        set_smooth(cone)
        _parent(cone, root)
        graphite = M.metal(f"{name}_graphite", "#2a2a2c", rough=0.35, smudge=0.1, tarnish=0.0)
        tip = mesh_object(f"{name}_tip", cylinder_bm(0.0011, tip_len * 0.2, 16, True,
                                                     (0, 0, z + tip_len * 0.9), radius2=0.0002), col, mat=graphite)
        set_smooth(tip)
        _parent(tip, root)
    if eraser:
        ferrule = cylinder(f"{name}_ferrule", r_body * 1.04, 0.009, (0, 0, -0.009), M.metal("ferrule", "#b8a26a", 0.3), col, 32)
        _parent(ferrule, root)
        er = cylinder(f"{name}_eraser", r_body * 0.98, 0.007, (0, 0, -0.016), M.plastic("eraser", "#d9897f", 0.7), col, 32,
                      bevel=0.0012)
        _parent(er, root)
    return root


def pencil_pot(name, col, loc, style="ceramic", color="#3f5d6b", n_pencils=5, rng=None, radius=0.036, height=0.098):
    rng = rng or random.Random(1)
    root = _group(name, col, loc)
    if style == "tin":
        mat = M.metal(f"{name}_tin", "#9aa0a3", rough=0.28, smudge=0.5, tarnish=0.35)
    elif style == "glass":
        mat = M.glass(f"{name}_glass", "#e6efe9", 0.02)
    else:
        mat = M.ceramic(f"{name}_glaze", color, rough=0.12, speckle=0.4, crazing=0.4)
    t = 0.004
    prof = [(0.0, 0.0), (radius - 0.003, 0.0), (radius, 0.003), (radius, height - 0.002), (radius - t / 2, height),
            (radius - t, height - 0.002), (radius - t, t + 0.003), (0.0, t)]
    pot = lathe(f"{name}_pot", prof, 64, mat, col)
    add_subsurf(pot, 1, 2)
    _parent(pot, root)
    for i in range(n_pencils):
        ang = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(0, radius * 0.55)
        p = pencil(f"{name}_pencil{i}", col, rng.choice(PENCIL_COLOURS), rng.uniform(0.15, 0.185),
                   sharpened=rng.random() < 0.8, eraser=rng.random() < 0.6, rng=rng)
        p.parent = root
        p.location = (math.cos(ang) * rr, math.sin(ang) * rr, t)
        # lean outwards against the rim
        tilt = rng.uniform(0.08, 0.2)
        p.rotation_euler = Euler((math.sin(ang) * -tilt, math.cos(ang) * tilt, rng.uniform(0, 6.28)), "XYZ")
        if rng.random() < 0.5:  # pointing up or down
            pass
    return root


def fountain_pen(name, col, loc, rot_z=0.0, color="#1d2a3a"):
    root = _group(name, col, loc, rot_z)
    lacquer = M.plastic(f"{name}_lacquer", color, rough=0.12, coat=1.0)
    gold = M.metal(f"{name}_gold", "#d4b06a", rough=0.15, smudge=0.2, tarnish=0.05)
    body = lathe(f"{name}_body", [(0.0, 0.0), (0.0045, 0.002), (0.0062, 0.02), (0.0065, 0.07), (0.006, 0.088),
                                  (0.0052, 0.09)], 48, lacquer, col)
    cap = lathe(f"{name}_cap", [(0.0068, 0.0), (0.0071, 0.004), (0.0071, 0.058), (0.0058, 0.066), (0.0, 0.068)],
                48, lacquer, col, loc=(0, 0, 0.082))
    ring = cylinder(f"{name}_ring", 0.0073, 0.003, (0, 0, 0.085), gold, col, 48)
    clip = box(f"{name}_clip", 0.0016, 0.003, 0.045, (0, 0.0076, 0.118), gold, col, bevel=0.0005)
    for o in (body, cap, ring, clip):
        _parent(o, root)
    root.rotation_euler = (math.radians(90), 0, rot_z)
    root.location = (loc[0], loc[1], loc[2] + 0.0068)
    return root


# ---------------------------------------------------------------------------
# Tableware
# ---------------------------------------------------------------------------

def mug(name, col, loc, rot_z=0.0, color="#6c8a7e", coffee=0.75, stain=True):
    root = _group(name, col, loc, rot_z)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.05, speckle=0.25, crazing=0.2)
    r, h, t = 0.041, 0.095, 0.0045
    prof = [(0.0, 0.0), (r - 0.006, 0.0), (r - 0.002, 0.002), (r, 0.008), (r + 0.001, h - 0.003),
            (r - 0.0015, h), (r - t, h - 0.003), (r - t, t + 0.004), (0.0, t)]
    body = lathe(f"{name}_body", prof, 72, glaze, col)
    add_subsurf(body, 1, 2)
    _parent(body, root)
    # handle: a bent tube
    curve = bpy.data.curves.new(f"{name}_handle", "CURVE")
    curve.dimensions = "3D"
    sp = curve.splines.new("BEZIER")
    sp.bezier_points.add(2)
    pts = [(r - 0.002, 0, h * 0.78), (r + 0.026, 0, h * 0.55), (r - 0.002, 0, h * 0.24)]
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    curve.bevel_depth = 0.0062
    curve.bevel_resolution = 6
    curve.resolution_u = 24
    handle = bpy.data.objects.new(f"{name}_handle", curve)
    link(handle, col)
    handle.data.materials.append(glaze)
    handle.scale = (1.0, 0.75, 1.0)
    _parent(handle, root)
    if coffee > 0:
        liquid = bpy.data.materials.new(f"{name}_coffee")
        liquid.use_nodes = True
        bsdf = liquid.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.02, 0.008, 0.003, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.02
        bsdf.inputs["Coat Weight"].default_value = 0.0
        z = t + (h - t) * coffee
        disc = mesh_object(f"{name}_coffee", cylinder_bm(r - t - 0.0002, 0.001, 64, True, (0, 0, z)), col, mat=liquid)
        set_smooth(disc)
        _parent(disc, root)
        if stain:
            # dried drip line inside the rim above the coffee
            ring = mesh_object(f"{name}_stainring", cylinder_bm(r - t - 0.0001, 0.003, 64, False, (0, 0, z + 0.004)), col,
                               mat=M.paper(f"{name}_stain", "#6a4a2a", rough=0.6, age=0.0))
            _parent(ring, root)
    return root


def drinking_glass(name, col, loc, water=0.6):
    root = _group(name, col, loc)
    g = M.glass(f"{name}_glass", "#f2f6f4", 0.0, 1.5, smudge=0.3)
    r, h, t = 0.033, 0.11, 0.0022
    prof = [(0.0, 0.0), (r - 0.002, 0.0), (r, 0.004), (r + 0.004, h), (r + 0.004 - t, h), (r - t, 0.008),
            (0.0, 0.007)]
    body = lathe(f"{name}_body", prof, 72, g, col)
    _parent(body, root)
    if water > 0:
        wm = M.glass(f"{name}_water", "#f4fbff", 0.0, 1.333, smudge=0.0)
        wz = 0.007 + (h - 0.012) * water
        rw = r - t + 0.004 * (wz / h)
        wprof = [(0.0, 0.0075), (r - t - 0.0002, 0.0085), (rw - 0.0002, wz), (0.0, wz)]
        w = lathe(f"{name}_water", wprof, 64, wm, col)
        _parent(w, root)
    return root


# ---------------------------------------------------------------------------
# Books and paper
# ---------------------------------------------------------------------------

BOOK_COLOURS = ["#6b2e2e", "#2f4a5a", "#8a7a52", "#3d4a30", "#5a3a5a", "#2c2c38", "#7a4a2a", "#a39b85"]


def book(name, col, loc, size=(0.16, 0.24, 0.03), color="#6b2e2e", rot=(0, 0, 0), rng=None, hard=True):
    """Hardback: two boards, rounded spine and a page block. Lies flat; origin at its bottom centre.
    size = (depth along X [spine at -X], length along Y, thickness)."""
    rng = rng or random.Random(2)
    w, l, th = size
    root = _group(name, col, loc)
    root.rotation_euler = rot
    cover = M.fabric(f"{name}_cloth", color, threads_per_m=2600, rough=0.75, sheen=0.25) if rng.random() < 0.6 \
        else M.leather(f"{name}_leather", color, rough=0.5, wear=0.5)
    pages = M.paper(f"{name}_pages", "#e9dfc8", rough=0.85, age=0.6)
    board = 0.0025 if hard else 0.0006
    over = 0.003 if hard else 0.0
    for zc in (board / 2, th - board / 2):
        b = box(f"{name}_board", w, l, board, (0, 0, zc), cover, col, bevel=0.0008)
        _parent(b, root)
    block = box(f"{name}_pages", w - over - 0.002, l - 2 * over, th - 2 * board, (over / 2, 0, th / 2), pages, col,
                bevel=0.0012)
    # page edges: fine lines via a stretched wave bump is in the paper noise already
    _parent(block, root)
    spine = mesh_object(f"{name}_spine", cylinder_bm(th / 2, l, 32, True, (0, 0, 0)), col, mat=cover)
    spine.rotation_euler = (math.radians(90), 0, 0)
    spine.location = (-w / 2 + th * 0.18, 0, th / 2)
    spine.scale = (0.45, 1.0, 1.0)
    set_smooth(spine)
    _parent(spine, root)
    return root


def book_stack(name, col, loc, count=3, rng=None, rot_z=0.0):
    rng = rng or random.Random(3)
    root = _group(name, col, loc, rot_z)
    z = 0.0
    for i in range(count):
        w = rng.uniform(0.14, 0.2)
        l = rng.uniform(0.2, 0.27)
        th = rng.uniform(0.018, 0.045)
        b = book(f"{name}_{i}", col, (rng.uniform(-0.008, 0.008), rng.uniform(-0.01, 0.01), z), (w, l, th),
                 rng.choice(BOOK_COLOURS), (0, 0, rng.uniform(-0.12, 0.12)), rng)
        b.parent = root
        z += th
    return root


def envelope(name, col, loc, rot_z=0.0, size=(0.162, 0.114), color="#e8dcc0", handwriting=True):
    root = _group(name, col, loc, rot_z)
    mat = M.paper(f"{name}_paper", color, rough=0.75, age=0.6, ink_lines=handwriting)
    b = box(f"{name}_body", size[0], size[1], 0.0008, (0, 0, 0.0004), mat, col, bevel=0.0002)
    _parent(b, root)
    # flap
    bm = bmesh.new()
    a = bm.verts.new((-size[0] / 2, size[1] / 2 - 0.001, 0.0009))
    b2 = bm.verts.new((size[0] / 2, size[1] / 2 - 0.001, 0.0009))
    c = bm.verts.new((0, size[1] / 2 - size[1] * 0.45, 0.0011))
    bm.faces.new((a, c, b2))
    flap = mesh_object(f"{name}_flap", bm, col, mat=M.paper(f"{name}_flap", color, 0.75, 0.7))
    _parent(flap, root)
    return root


def letter_pile(name, col, loc, count=4, rng=None):
    rng = rng or random.Random(4)
    root = _group(name, col, loc)
    for i in range(count):
        e = envelope(f"{name}_{i}", col, (rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), i * 0.0012),
                     rng.uniform(-0.4, 0.4), color=rng.choice(["#e8dcc0", "#efe8d8", "#d9c9a8", "#c9b9a0"]))
        e.parent = root
    return root


# ---------------------------------------------------------------------------
# Lighting props
# ---------------------------------------------------------------------------

def bankers_lamp(name, col, loc, rot_z=0.0, on=True, kelvin=2600.0, power=6.0):
    """Brass banker's lamp with a green cased-glass shade. Returns (root, light_obj)."""
    root = _group(name, col, loc, rot_z)
    brass = M.metal(f"{name}_brass", "#c39a52", rough=0.22, smudge=0.6, tarnish=0.35)
    base = lathe(f"{name}_base", [(0.0, 0.0), (0.075, 0.0), (0.078, 0.004), (0.07, 0.014), (0.03, 0.022),
                                  (0.012, 0.03), (0.0, 0.03)], 64, brass, col)
    _parent(base, root)
    stem = cylinder(f"{name}_stem", 0.0065, 0.26, (0, 0, 0.03), brass, col, 32)
    _parent(stem, root)
    arm = cylinder(f"{name}_arm", 0.005, 0.12, (0, 0.0, 0.27), brass, col, 24)
    arm.rotation_euler = (math.radians(-90), 0, 0)
    arm.location = (0, -0.0, 0.285)
    _parent(arm, root)
    # shade: half cylinder, green glass outside, white opal inside
    shade_mat = bpy.data.materials.new(f"{name}_shade")
    shade_mat.use_nodes = True
    nt = shade_mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.02, 0.16, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.04
    bsdf.inputs["Transmission Weight"].default_value = 0.35
    bsdf.inputs["Coat Weight"].default_value = 1.0
    bm = bmesh.new()
    seg = 40
    L = 0.24
    R = 0.07
    rows = []
    for j in range(2):
        y = -L / 2 + j * L
        rows.append([bm.verts.new((R * math.cos(math.pi * i / seg), y, R * math.sin(math.pi * i / seg) * 0.75))
                     for i in range(seg + 1)])
    for i in range(seg):
        bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
    shade = mesh_object(f"{name}_shade", bm, col, mat=shade_mat)
    sol = shade.modifiers.new("Thick", "SOLIDIFY")
    sol.thickness = 0.003
    add_subsurf(shade, 1, 2)
    set_smooth(shade)
    shade.location = (0, -0.0, 0.29)
    shade.rotation_euler = (0, 0, math.radians(90))
    _parent(shade, root)
    light = None
    if on:
        bulb = mesh_object(f"{name}_bulb", cylinder_bm(0.011, 0.11, 24, True, (0, 0, 0)), col,
                           mat=M.frosted_bulb(f"{name}_bulbmat", kelvin, 25.0))
        bulb.rotation_euler = (0, math.radians(90), math.radians(90))
        bulb.location = (0, 0, 0.3)
        set_smooth(bulb)
        _parent(bulb, root)
        ld = bpy.data.lights.new(f"{name}_light", "AREA")
        ld.shape = "RECTANGLE"
        ld.size = 0.11
        ld.size_y = 0.02
        ld.energy = power
        from .world import kelvin_rgb
        ld.color = kelvin_rgb(kelvin)
        light = bpy.data.objects.new(f"{name}_light", ld)
        link(light, col)
        light.location = (0, 0, 0.292)
        light.rotation_euler = (0, 0, math.radians(90))
        _parent(light, root)
    return root, light


def candle(name, col, loc, height=0.12, radius=0.018, lit=True, color="#efe6d2"):
    root = _group(name, col, loc)
    wax = bpy.data.materials.new(f"{name}_wax")
    wax.use_nodes = True
    b = wax.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.85, 0.8, 0.68, 1.0)
    b.inputs["Subsurface Weight"].default_value = 1.0
    b.inputs["Subsurface Radius"].default_value = (0.02, 0.012, 0.006)
    b.inputs["Roughness"].default_value = 0.35
    body = lathe(f"{name}_body", [(0.0, 0.0), (radius, 0.0), (radius, height - 0.004), (radius - 0.003, height),
                                  (radius - 0.006, height - 0.004), (0.0, height - 0.006)], 48, wax, col)
    _parent(body, root)
    light = None
    if lit:
        wick = cylinder(f"{name}_wick", 0.0007, 0.01, (0, 0, height - 0.006), M.plastic("wick", "#111111", 0.8), col, 8)
        _parent(wick, root)
        fl = lathe(f"{name}_flame", [(0.0, 0.0), (0.0035, 0.004), (0.0038, 0.01), (0.0015, 0.022), (0.0, 0.03)], 24,
                   M.flame(f"{name}_flamemat", 18.0), col, loc=(0, 0, height + 0.002))
        fl.visible_shadow = False
        _parent(fl, root)
        ld = bpy.data.lights.new(f"{name}_light", "POINT")
        ld.energy = 0.9
        ld.shadow_soft_size = 0.006
        from .world import kelvin_rgb
        ld.color = kelvin_rgb(1850)
        light = bpy.data.objects.new(f"{name}_light", ld)
        link(light, col)
        light.location = (0, 0, height + 0.014)
        _parent(light, root)
    return root, light


# ---------------------------------------------------------------------------
# Frames and small decor
# ---------------------------------------------------------------------------

def picture_frame(name, col, loc, rot_z, image_path, size=(0.15, 0.2), border=0.018, wood_preset="walnut",
                  lean=12.0, glass=True):
    """Standing frame with a strut. The photo shows through real glass. Origin at the front bottom edge."""
    root = _group(name, col, loc, rot_z)
    w, h = size
    fw = M.wood(f"{name}_wood", wood_preset, varnish=0.7, wear=0.4, scale=3.0, grain_axis="Z")
    depth = 0.018
    inner = bpy.data.objects.new(f"{name}_tilt", None)
    link(inner, col)
    inner.parent = root
    inner.rotation_euler = (math.radians(lean), 0, 0)
    pieces = [
        (w, border, depth, (0, 0, border / 2)),
        (w, border, depth, (0, 0, h - border / 2)),
        (border, h, depth, (-w / 2 + border / 2, 0, h / 2)),
        (border, h, depth, (w / 2 - border / 2, 0, h / 2)),
    ]
    for i, (sx, sz, sy, c) in enumerate(pieces):
        b = box(f"{name}_side{i}", sx, sy, sz, (c[0], 0, c[2]), fw, col, bevel=0.003, segments=4)
        b.rotation_euler = (0, 0, 0)
        b.parent = inner
    # photo
    me = bpy.data.meshes.new(f"{name}_photo")
    pw, ph = w - 2 * border + 0.004, h - 2 * border + 0.004
    me.from_pydata([(-pw / 2, 0, border - 0.002), (pw / 2, 0, border - 0.002), (pw / 2, 0, border - 0.002 + ph),
                    (-pw / 2, 0, border - 0.002 + ph)], [], [(0, 1, 2, 3)])
    me.uv_layers.new(name="UVMap")
    for li, uvc in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        me.uv_layers[0].data[li].uv = uvc
    photo = bpy.data.objects.new(f"{name}_photo", me)
    link(photo, col)
    photo.location = (0, 0.002, 0)
    photo.parent = inner
    if image_path:
        pm = M.image_material(f"{name}_photomat", image_path, alpha=False)
        bsdf = next(nd for nd in pm.node_tree.nodes if nd.bl_idname == "ShaderNodeBsdfPrincipled")
        bsdf.inputs["Roughness"].default_value = 0.5
        photo.data.materials.append(pm)
    if glass:
        gm = M.glass(f"{name}_glass", "#ffffff", 0.0, 1.52, smudge=0.4)
        g = box(f"{name}_glass", w - 2 * border + 0.004, 0.0015, h - 2 * border + 0.004, (0, -0.003, h / 2), gm, col)
        g.parent = inner
    back = box(f"{name}_back", w - 0.004, 0.003, h - 0.004, (0, 0.0075, h / 2), M.paper(f"{name}_card", "#4a3a2a", 0.8, 0.3), col)
    back.parent = inner
    strut = box(f"{name}_strut", 0.03, 0.003, h * 0.7, (0, 0.04, h * 0.33), M.paper(f"{name}_card2", "#4a3a2a", 0.8, 0.3), col)
    strut.rotation_euler = (math.radians(-25), 0, 0)
    strut.parent = root
    return root


def reading_glasses(name, col, loc, rot_z=0.0):
    root = _group(name, col, loc, rot_z)
    frame_mat = M.plastic(f"{name}_tortoise", "#3a2416", rough=0.15, coat=1.0)
    lens_mat = M.glass(f"{name}_lens", "#ffffff", 0.0, 1.5, smudge=0.6)
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.024, minor_radius=0.0024, major_segments=48, minor_segments=10,
                                         location=(sx * 0.031, 0, 0.022))
        rim = bpy.context.object
        rim.name = f"{name}_rim"
        rim.rotation_euler = (math.radians(80), 0, 0)
        rim.scale = (1.0, 0.82, 1.0)
        rim.data.materials.append(frame_mat)
        set_smooth(rim)
        for c in rim.users_collection:
            c.objects.unlink(rim)
        col.objects.link(rim)
        rim.parent = root
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.024, segments=48, ring_count=24,
                                             location=(sx * 0.031, 0, 0.022))
        lens = bpy.context.object
        lens.name = f"{name}_lens"
        lens.rotation_euler = (math.radians(80), 0, 0)
        lens.scale = (1.0, 0.82, 0.08)
        lens.data.materials.append(lens_mat)
        set_smooth(lens)
        for c in lens.users_collection:
            c.objects.unlink(lens)
        col.objects.link(lens)
        lens.parent = root
        # folded temple arm
        arm = box(f"{name}_arm", 0.11, 0.003, 0.004, (sx * 0.0, 0.012 + (0.006 if sx > 0 else 0), 0.01), frame_mat, col,
                  bevel=0.0012)
        arm.parent = root
    bridge = box(f"{name}_bridge", 0.016, 0.003, 0.004, (0, 0, 0.034), frame_mat, col, bevel=0.0012)
    bridge.parent = root
    return root


def potted_plant(name, col, loc, rng=None, leaves=14, pot_color="#b5653d"):
    """Small succulent/echeveria-like rosette in a terracotta pot."""
    rng = rng or random.Random(5)
    root = _group(name, col, loc)
    terracotta = M.ceramic(f"{name}_pot", pot_color, rough=0.75, speckle=0.6)
    pot = lathe(f"{name}_pot", [(0.0, 0.0), (0.035, 0.0), (0.045, 0.07), (0.05, 0.072), (0.05, 0.085),
                                (0.044, 0.085), (0.04, 0.06), (0.0, 0.006)], 48, terracotta, col)
    _parent(pot, root)
    soil = cylinder(f"{name}_soil", 0.041, 0.004, (0, 0, 0.074), M.plastic("soil", "#2a1d14", 0.95), col, 40)
    _parent(soil, root)
    leaf_mat = bpy.data.materials.new(f"{name}_leaf")
    leaf_mat.use_nodes = True
    lb = leaf_mat.node_tree.nodes.get("Principled BSDF")
    lb.inputs["Base Color"].default_value = (0.12, 0.25, 0.14, 1.0)
    lb.inputs["Subsurface Weight"].default_value = 0.4
    lb.inputs["Subsurface Radius"].default_value = (0.004, 0.008, 0.003)
    lb.inputs["Roughness"].default_value = 0.4
    lb.inputs["Coat Weight"].default_value = 0.3
    for i in range(leaves):
        ang = i * 2.39996
        ring = i / leaves
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=16, ring_count=10)
        lf = bpy.context.object
        for c in lf.users_collection:
            c.objects.unlink(lf)
        col.objects.link(lf)
        lf.name = f"{name}_leaf{i}"
        size = 0.03 * (1 - ring * 0.55)
        lf.scale = (size * 0.45, size, size * 0.18)
        r = 0.03 * (1 - ring * 0.8)
        lf.location = (math.cos(ang) * r, math.sin(ang) * r, 0.08 + ring * 0.025)
        lf.rotation_euler = (math.radians(40 + ring * 30) * 0, math.radians(-25 - ring * 40), ang)
        lf.rotation_mode = "ZYX"
        lf.rotation_euler = (0, math.radians(-30 - 35 * ring), ang)
        lf.data.materials.append(leaf_mat)
        set_smooth(lf)
        lf.parent = root
    return root
