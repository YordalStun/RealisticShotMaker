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


def _dielectric(name, ior, tint, absorb, density, rough=0.0, smudge=0.0):
    """Clear glass or water: refraction, a whisper of surface grime and a coloured body (the green of
    soda-lime glass, the blue of a deep glass of water) that only shows where the light goes through a lot of it."""
    from .util import Nodes, new_material, srgb
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    b = n.new("ShaderNodeBsdfPrincipled", IOR=ior, Roughness=rough)
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Base Color"].default_value = srgb(tint)
    if smudge > 0:
        tc = n.new("ShaderNodeTexCoord")
        sm = n.new("ShaderNodeTexNoise", Scale=180.0, Detail=6.0, Roughness=0.6)
        n.link(tc, "Object", sm, "Vector")
        smr = n.ramp((sm, "Fac"), [(0.58, (0, 0, 0)), (0.78, (1, 1, 1))])
        n.link(n.math("ADD", rough, n.math("MULTIPLY", (smr, "Color"), smudge * 0.12)), None, b, "Roughness")
    vol = n.new("ShaderNodeVolumeAbsorption", Density=density)
    vol.inputs["Color"].default_value = srgb(absorb)
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    n.link(vol, None, out, "Volume")
    return mat


def _outward(obj):
    """Point every face outward. Refractive solids must: with flipped normals Cycles swaps inside and
    outside, and the glass turns into a chrome mirror of total internal reflection."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def drinking_glass(name, col, loc, water=0.6):
    """A plain tumbler: tapered, a thick base, a rounded rim, and water that meets the glass (a thin air gap
    between them reads as a silvery skin, so the water slightly overlaps the wall) with a meniscus at the edge."""
    root = _group(name, col, loc)
    g = _dielectric(f"{name}_glassmat", 1.52, "#fbfdfc", "#b9dcc8", 2.5, smudge=0.35)
    rb, rt, h, t, base = 0.0305, 0.0355, 0.108, 0.0021, 0.0065

    def outer(z):
        return rb + (rt - rb) * z / h

    prof = [(0.0, 0.0011), (rb - 0.006, 0.0)]
    for k in range(5):                                  # rounded outer foot
        a = math.radians(-90 + 90 * k / 4)
        prof.append((rb - 0.0025 + 0.0025 * math.cos(a), 0.0025 + 0.0025 * math.sin(a)))
    prof.append((outer(h - t / 2), h - t / 2))
    for k in range(1, 8):                               # rounded rim
        a = math.radians(180 * k / 7)
        cx = outer(h - t / 2) - t / 2
        prof.append((cx + (t / 2) * math.cos(a), h - t / 2 + (t / 2) * math.sin(a)))
    prof.append((outer(base + 0.003) - t, base + 0.003))
    for k in range(1, 5):                               # soft inside corner
        a = math.radians(-90 * k / 4)
        prof.append((outer(base) - t - 0.003 + 0.003 * math.cos(a), base + 0.003 + 0.003 * math.sin(a)))
    prof.append((0.0, base + 0.0008))                    # slightly domed floor
    body = _outward(lathe(f"{name}_body", prof, 96, g, col))
    _parent(body, root)
    if water > 0:
        wm = _dielectric(f"{name}_watermat", 1.333, "#ffffff", "#9fd2e6", 1.2)
        wz = base + (h - base - 0.012) * water
        ov = 0.00012                                    # into the glass wall: no air gap

        def inner(z):
            return outer(z) - t + ov
        wprof = [(0.0, base + 0.0008 - ov)]
        for k in range(1, 5):
            a = math.radians(-90 + 90 * k / 4)
            wprof.append((outer(base) - t - 0.003 + (0.003 + ov) * math.cos(a), base + 0.003 + (0.003 + ov) * math.sin(a)))
        # meniscus: the water climbs the glass by about a millimetre
        wprof.append((inner(wz + 0.0011), wz + 0.0011))
        for k in range(1, 6):
            u = k / 5
            rr = inner(wz) - 0.0025 * u
            wprof.append((rr, wz + 0.0011 * (1 - u) ** 2))
        wprof.append((0.0, wz))
        w = _outward(lathe(f"{name}_water", wprof, 96, wm, col))
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


# ---------------------------------------------------------------------------
# Kitchen and living room
# ---------------------------------------------------------------------------

def teapot(name, col, loc, rot_z=0.0, color="#e8e2d4"):
    root = _group(name, col, loc, rot_z)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.04, speckle=0.2, crazing=0.5)
    body = lathe(f"{name}_body", [(0.0, 0.0), (0.045, 0.0), (0.06, 0.008), (0.078, 0.04), (0.082, 0.065),
                                  (0.072, 0.1), (0.05, 0.118), (0.044, 0.12), (0.042, 0.115), (0.0, 0.112)], 72,
                 glaze, col)
    add_subsurf(body, 1, 2)
    _parent(body, root)
    lid = lathe(f"{name}_lid", [(0.0, 0.0), (0.046, 0.0), (0.044, 0.006), (0.03, 0.016), (0.01, 0.02),
                                (0.012, 0.03), (0.0, 0.034)], 48, glaze, col, loc=(0, 0, 0.116))
    _parent(lid, root)
    for kind, pts, depth in (("spout", [(0.07, 0, 0.045), (0.11, 0, 0.07), (0.13, 0, 0.11)], 0.012),
                             ("handle", [(-0.07, 0, 0.1), (-0.115, 0, 0.075), (-0.07, 0, 0.03)], 0.007)):
        curve = bpy.data.curves.new(f"{name}_{kind}", "CURVE")
        curve.dimensions = "3D"
        sp = curve.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for bp, co in zip(sp.bezier_points, pts):
            bp.co = co
            bp.handle_left_type = bp.handle_right_type = "AUTO"
        curve.bevel_depth = depth
        curve.bevel_resolution = 6
        if kind == "spout":
            sp.bezier_points[-1].radius = 0.55
        o = bpy.data.objects.new(f"{name}_{kind}", curve)
        link(o, col)
        o.data.materials.append(glaze)
        _parent(o, root)
    return root


def cup_and_saucer(name, col, loc, rot_z=0.0, color="#f0ece2", tea=0.7):
    root = _group(name, col, loc, rot_z)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.03, speckle=0.1, crazing=0.3)
    saucer = lathe(f"{name}_saucer", [(0.0, 0.0), (0.04, 0.0), (0.05, 0.004), (0.07, 0.012), (0.074, 0.016),
                                      (0.071, 0.017), (0.05, 0.009), (0.0, 0.007)], 72, glaze, col)
    _parent(saucer, root)
    cup = lathe(f"{name}_cup", [(0.0, 0.0), (0.024, 0.0), (0.028, 0.004), (0.042, 0.03), (0.046, 0.058),
                                (0.044, 0.06), (0.041, 0.057), (0.026, 0.008), (0.0, 0.007)], 72, glaze, col,
                loc=(0, 0, 0.008))
    add_subsurf(cup, 1, 2)
    _parent(cup, root)
    if tea > 0:
        liquid = bpy.data.materials.new(f"{name}_tea")
        liquid.use_nodes = True
        b = liquid.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (0.16, 0.05, 0.01, 1.0)
        b.inputs["Roughness"].default_value = 0.02
        z = 0.008 + 0.007 + 0.045 * tea
        disc = mesh_object(f"{name}_tea", cylinder_bm(0.026 + 0.015 * tea, 0.001, 64, True, (0, 0, z)), col,
                           mat=liquid)
        set_smooth(disc)
        _parent(disc, root)
    return root


def fruit_bowl(name, col, loc, rng=None, color="#3f5d6b"):
    rng = rng or random.Random(9)
    root = _group(name, col, loc)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.1, speckle=0.5)
    bowl = lathe(f"{name}_bowl", [(0.0, 0.0), (0.05, 0.0), (0.06, 0.01), (0.12, 0.06), (0.13, 0.07),
                                  (0.124, 0.071), (0.115, 0.064), (0.055, 0.016), (0.0, 0.014)], 72, glaze, col)
    add_subsurf(bowl, 1, 2)
    _parent(bowl, root)
    fruit_mats = {
        "apple": ("#9b2a1c", 0.35), "green_apple": ("#8aa83a", 0.35), "orange": ("#e07a1c", 0.55),
        "lemon": ("#e8c53a", 0.45),
    }
    for i in range(7):
        kind = rng.choice(list(fruit_mats))
        hexc, rough = fruit_mats[kind]
        m = bpy.data.materials.get(f"Fruit_{kind}")
        if m is None:
            m = bpy.data.materials.new(f"Fruit_{kind}")
            m.use_nodes = True
            b = m.node_tree.nodes.get("Principled BSDF")
            from .util import srgb
            b.inputs["Base Color"].default_value = srgb(hexc)
            b.inputs["Roughness"].default_value = rough
            b.inputs["Subsurface Weight"].default_value = 0.25
            b.inputs["Subsurface Radius"].default_value = (0.006, 0.003, 0.002)
            b.inputs["Coat Weight"].default_value = 0.4 if "apple" in kind else 0.0
        r = 0.034 if kind != "lemon" else 0.03
        ang = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, 0.06) if i else 0.0
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=40, ring_count=20,
                                             location=(math.cos(ang) * d, math.sin(ang) * d, 0.03 + r * 0.9 + (0.02 if i > 4 else 0)))
        f = bpy.context.object
        for c in f.users_collection:
            c.objects.unlink(f)
        col.objects.link(f)
        f.name = f"{name}_{kind}{i}"
        f.scale = (1.0, 1.0, 0.9 if "apple" in kind else (1.25 if kind == "lemon" else 0.95))
        f.rotation_euler = (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0, 6.28))
        f.data.materials.append(m)
        set_smooth(f)
        f.parent = root
    return root


def jar(name, col, loc, fill_color="#7a1c2a", label=True):
    root = _group(name, col, loc)
    g = M.glass(f"{name}_glass", "#f4f8f6", 0.0, 1.5, smudge=0.3)
    # a jar is a shell of glass (a solid lump of glass refracts like a paperweight)
    body = _outward(lathe(f"{name}_glass", [(0.0, 0.0), (0.03, 0.0), (0.034, 0.006), (0.034, 0.08), (0.028, 0.09),
                                            (0.028, 0.1), (0.0255, 0.1), (0.0255, 0.091), (0.0315, 0.0805),
                                            (0.0315, 0.0075), (0.028, 0.004), (0.0, 0.004)], 64, g, col))
    _parent(body, root)
    jam = M.ceramic(f"{name}_jam", fill_color, rough=0.15, speckle=0.0)
    fill = lathe(f"{name}_fill", [(0.0, 0.0039), (0.0281, 0.0039), (0.0316, 0.0074), (0.0316, 0.06), (0.0, 0.062)],
                 64, jam, col)
    _parent(fill, root)
    lid = cylinder(f"{name}_lid", 0.031, 0.014, (0, 0, 0.1), M.fabric(f"{name}_gingham", "#f2efe6", 1600, 0.85, 0.3,
                                                                      pattern="gingham", pattern_color="#b8463c",
                                                                      pattern_scale=60.0), col, 48, bevel=0.002)
    _parent(lid, root)
    if label:
        lab = cylinder(f"{name}_label", 0.0345, 0.035, (0, 0, 0.03), M.paper(f"{name}_paper", "#efe6cf", 0.7, 0.4,
                                                                             ink_lines=True, line_color="#2a2a40"),
                       col, 64)
        _parent(lab, root)
    return root


def vase_with_stems(name, col, loc, rng=None, color="#b9c4c9"):
    rng = rng or random.Random(10)
    root = _group(name, col, loc)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.2, speckle=0.4, crazing=0.4)
    v = lathe(f"{name}_vase", [(0.0, 0.0), (0.035, 0.0), (0.05, 0.04), (0.045, 0.1), (0.022, 0.15), (0.024, 0.17),
                               (0.02, 0.17), (0.018, 0.15), (0.0, 0.15)], 64, glaze, col)
    add_subsurf(v, 1, 2)
    _parent(v, root)
    stem_mat = bpy.data.materials.new(f"{name}_stem")
    stem_mat.use_nodes = True
    sb = stem_mat.node_tree.nodes.get("Principled BSDF")
    sb.inputs["Base Color"].default_value = (0.08, 0.15, 0.04, 1)
    sb.inputs["Roughness"].default_value = 0.6
    bloom = bpy.data.materials.new(f"{name}_flower")
    bloom.use_nodes = True
    bb = bloom.node_tree.nodes.get("Principled BSDF")
    bb.inputs["Base Color"].default_value = (0.9, 0.85, 0.7, 1)
    bb.inputs["Subsurface Weight"].default_value = 0.5
    bb.inputs["Roughness"].default_value = 0.5
    for i in range(7):
        ang = rng.uniform(0, 2 * math.pi)
        tilt = rng.uniform(0.1, 0.45)
        L = rng.uniform(0.18, 0.3)
        curve = bpy.data.curves.new(f"{name}_stem{i}", "CURVE")
        curve.dimensions = "3D"
        sp = curve.splines.new("BEZIER")
        sp.bezier_points.add(1)
        top = (math.cos(ang) * math.sin(tilt) * L, math.sin(ang) * math.sin(tilt) * L, 0.12 + math.cos(tilt) * L)
        sp.bezier_points[0].co = (0, 0, 0.1)
        sp.bezier_points[1].co = top
        for bp in sp.bezier_points:
            bp.handle_left_type = bp.handle_right_type = "AUTO"
        curve.bevel_depth = 0.0016
        st = bpy.data.objects.new(f"{name}_stem{i}", curve)
        link(st, col)
        st.data.materials.append(stem_mat)
        _parent(st, root)
        # small flower head (cluster of spheres)
        for k in range(6):
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.006,
                                                  location=(top[0] + rng.uniform(-0.01, 0.01),
                                                            top[1] + rng.uniform(-0.01, 0.01),
                                                            top[2] + rng.uniform(-0.006, 0.008)))
            fh = bpy.context.object
            for c in fh.users_collection:
                c.objects.unlink(fh)
            col.objects.link(fh)
            fh.data.materials.append(bloom)
            fh.parent = root
    return root


def alarm_clock(name, col, loc, rot_z=0.0, color="#8c2f2f"):
    """Twin-bell wind-up alarm clock."""
    root = _group(name, col, loc, rot_z)
    paint = M.metal(f"{name}_paint", color, rough=0.25, smudge=0.3, tarnish=0.1)
    chrome = M.metal(f"{name}_chrome", "#d8d8d8", rough=0.12, smudge=0.4, tarnish=0.05)
    body = cylinder(f"{name}_body", 0.048, 0.03, (0, 0, 0), paint, col, 64, bevel=0.004)
    body.rotation_euler = (math.radians(90), 0, 0)
    body.location = (0, 0.015, 0.058)
    _parent(body, root)
    face = cylinder(f"{name}_face", 0.042, 0.002, (0, -0.016, 0.058), M.paper(f"{name}_dial", "#f2ecdc", 0.5, 0.2), col, 64)
    face.rotation_euler = (math.radians(90), 0, 0)
    _parent(face, root)
    glass = cylinder(f"{name}_glass", 0.044, 0.004, (0, -0.019, 0.058), M.glass(f"{name}_crystal", "#ffffff", 0.0), col, 64)
    glass.rotation_euler = (math.radians(90), 0, 0)
    _parent(glass, root)
    for i in range(12):  # hour marks
        a = i / 12 * 2 * math.pi
        mk = box(f"{name}_mark{i}", 0.002, 0.0008, 0.006, (math.sin(a) * 0.035, -0.0172, 0.058 + math.cos(a) * 0.035),
                 M.plastic("ink", "#1a1a1a", 0.6), col)
        mk.rotation_euler = (0, -a, 0)
        _parent(mk, root)
    for i, (L, a) in enumerate(((0.024, 1.1), (0.034, 4.1))):
        hand = box(f"{name}_hand{i}", 0.0018, 0.0006, L, (math.sin(a) * L / 2, -0.0178, 0.058 + math.cos(a) * L / 2),
                   M.plastic("hand", "#111111", 0.4), col)
        hand.rotation_euler = (0, -a, 0)
        _parent(hand, root)
    for sx in (-1, 1):
        bell = lathe(f"{name}_bell", [(0.0, 0.0), (0.026, 0.0), (0.024, 0.012), (0.012, 0.022), (0.0, 0.024)], 48,
                     chrome, col, loc=(sx * 0.03, 0.015, 0.1))
        bell.rotation_euler = (0, sx * math.radians(-25), 0)
        _parent(bell, root)
        leg = cylinder(f"{name}_leg", 0.004, 0.02, (sx * 0.03, 0.015, 0.0), chrome, col, 16)
        leg.rotation_euler = (0, sx * math.radians(20), 0)
        _parent(leg, root)
    return root


def carriage_clock(name, col, loc, rot_z=0.0):
    root = _group(name, col, loc, rot_z)
    brass = M.metal(f"{name}_brass", "#caa45a", rough=0.18, smudge=0.4, tarnish=0.3)
    glassm = M.glass(f"{name}_glass", "#ffffff", 0.0)
    base = box(f"{name}_base", 0.085, 0.07, 0.012, (0, 0, 0.006), brass, col, bevel=0.002)
    top = box(f"{name}_top", 0.085, 0.07, 0.012, (0, 0, 0.122), brass, col, bevel=0.002)
    for o in (base, top):
        _parent(o, root)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = cylinder(f"{name}_pillar", 0.004, 0.11, (sx * 0.037, sy * 0.029, 0.012), brass, col, 16)
            _parent(p, root)
    g = box(f"{name}_glass", 0.072, 0.058, 0.108, (0, 0, 0.066), glassm, col)
    _parent(g, root)
    dial = box(f"{name}_dial", 0.05, 0.002, 0.05, (0, -0.02, 0.07), M.paper(f"{name}_dial", "#f3eedf", 0.45, 0.2), col)
    _parent(dial, root)
    handle = bpy.data.curves.new(f"{name}_handle", "CURVE")
    handle.dimensions = "3D"
    sp = handle.splines.new("BEZIER")
    sp.bezier_points.add(2)
    for bp, co in zip(sp.bezier_points, [(-0.03, 0, 0.128), (0, 0, 0.15), (0.03, 0, 0.128)]):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    handle.bevel_depth = 0.0025
    ho = bpy.data.objects.new(f"{name}_handle", handle)
    link(ho, col)
    ho.data.materials.append(brass)
    _parent(ho, root)
    return root


def old_trunk(name, col, loc, rot_z=0.0, size=(0.9, 0.5, 0.45), lid_open_deg=105.0):
    """Wooden travel trunk with leather straps and brass corners. Opening faces +Y... lid hinged at the back."""
    w, d, h = size
    root = _group(name, col, loc, rot_z)
    wood = M.wood(f"{name}_wood", "aged_beam", varnish=0.2, wear=0.8, dust=0.4, scale=1.5, grain_axis="X",
                  planks=(0.6, 0.11))
    inner = M.paper(f"{name}_lining", "#9c8a6a", rough=0.85, age=0.8)
    brass = M.metal(f"{name}_brass", "#a8853f", rough=0.4, smudge=0.6, tarnish=0.7)
    strap = M.leather(f"{name}_strap", "#4a2c1a", 0.55, 0.7)
    t = 0.015
    parts = [(w, d, t, (0, 0, t / 2)), (w, t, h, (0, -d / 2 + t / 2, h / 2)), (w, t, h, (0, d / 2 - t / 2, h / 2)),
             (t, d, h, (-w / 2 + t / 2, 0, h / 2)), (t, d, h, (w / 2 - t / 2, 0, h / 2))]
    for i, (sx, sy, sz, c) in enumerate(parts):
        b = box(f"{name}_side{i}", sx, sy, sz, c, wood, col, bevel=0.003)
        _parent(b, root)
    lining = box(f"{name}_lining", w - 2 * t - 0.002, d - 2 * t - 0.002, 0.002, (0, 0, t + 0.001), inner, col)
    _parent(lining, root)
    # lid hinged at the back edge
    hinge = bpy.data.objects.new(f"{name}_hinge", None)
    link(hinge, col)
    hinge.parent = root
    hinge.location = (0, d / 2, h)
    hinge.rotation_euler = (math.radians(lid_open_deg), 0, 0)
    lid = box(f"{name}_lid", w + 0.01, d + 0.01, 0.06, (0, -d / 2, 0.03), wood, col, bevel=0.004)
    lid.parent = hinge
    lid_in = box(f"{name}_lidlining", w - 0.03, d - 0.03, 0.002, (0, -d / 2, -0.001), inner, col)
    lid_in.parent = hinge
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = box(f"{name}_corner", 0.05, 0.05, 0.05, (sx * (w / 2 - 0.02), sy * (d / 2 - 0.02), 0.025), brass, col,
                    bevel=0.006)
            _parent(c, root)
    for sx in (-0.25, 0.25):
        s = box(f"{name}_strap", 0.04, 0.004, h - 0.02, (sx * w, -d / 2 - 0.002, h / 2), strap, col, bevel=0.001)
        _parent(s, root)
    return root


def letter_bundle(name, col, loc, rot_z=0.0, count=12, rng=None, string_color="#8a6a4a"):
    """A stack of old envelopes tied crosswise with string, as people keep letters."""
    rng = rng or random.Random(6)
    root = _group(name, col, loc, rot_z)
    tones = ["#e8dcc0", "#efe8d8", "#d9c9a8", "#c9b9a0", "#e2d2b0", "#d4c6ad"]
    z = 0.0
    w, h = 0.162, 0.114
    for i in range(count):
        e = envelope(f"{name}_{i}", col, (rng.uniform(-0.004, 0.004), rng.uniform(-0.004, 0.004), z),
                     rng.uniform(-0.05, 0.05), color=rng.choice(tones), handwriting=(i == count - 1))
        e.parent = root
        z += 0.0013
    twine = M.fabric(f"{name}_twine", string_color, threads_per_m=3000, rough=0.9, sheen=0.4)
    t = 0.0016
    # one loop along the length and one across, wrapping over the top and down the sides
    for (sx, sy) in ((w + 0.004, t), (t, h + 0.004)):
        top = box(f"{name}_twineTop", sx, sy, t, (0, 0, z + t / 2), twine, col)
        _parent(top, root)
    for (dx, dy, sx, sy) in ((w / 2 + 0.002, 0, t, t), (-w / 2 - 0.002, 0, t, t), (0, h / 2 + 0.002, t, t),
                             (0, -h / 2 - 0.002, t, t)):
        side = box(f"{name}_twineSide", sx, sy, z, (dx, dy, z / 2), twine, col)
        _parent(side, root)
    # a small knot where the strings cross
    knot = cylinder(f"{name}_knot", 0.004, 0.003, (0.0, 0.0, z + t), twine, col, 16, bevel=0.001)
    _parent(knot, root)
    return root, z + t


# ---------------------------------------------------------------------------
# Small things that make a place feel lived in
# ---------------------------------------------------------------------------

def _wire(name, col, pts, radius, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for k, p in enumerate(pts):
        sp.points[k].co = (p[0], p[1], p[2], 1)
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    o = bpy.data.objects.new(name, cu)
    link(o, col)
    o.data.materials.append(mat)
    return o


def paperclip(name, col, loc, rot_z=0.0, rusty=False):
    """A Gem paperclip lying flat: three nested loops of steel wire."""
    root = _group(name, col, loc, rot_z)
    steel = M.metal("ClipSteel", "#9a8a72" if rusty else "#c9ccd0", rough=0.25 if not rusty else 0.6, smudge=0.3,
                    tarnish=0.8 if rusty else 0.1)
    r = 0.0005
    L, W = 0.033, 0.0085

    def arc(cx, cy, rad, a0, a1, n=10):
        return [(cx + rad * math.cos(a0 + (a1 - a0) * i / n), cy + rad * math.sin(a0 + (a1 - a0) * i / n), r)
                for i in range(n + 1)]
    pts = [(L * 0.62, -W * 0.18, r), (-L / 2 + W / 2, -W / 2, r)] + arc(-L / 2 + W / 2, 0, W / 2, -math.pi / 2,
                                                                       -3 * math.pi / 2)[1:]
    pts += [(L / 2 - W * 0.4, W / 2, r)] + arc(L / 2 - W * 0.4, W * 0.08, W * 0.42, math.pi / 2, -math.pi / 2)[1:]
    pts += [(-L / 2 + W * 0.85, -W * 0.34, r)] + arc(-L / 2 + W * 0.85, W * 0.0, W * 0.34, -math.pi / 2,
                                                     -3 * math.pi / 2)[1:]
    pts += [(L * 0.3, W * 0.34, r)]
    w = _wire(f"{name}_wire", col, pts, r, steel)
    w.parent = root
    return root


def notebook(name, col, loc, rot_z=0.0, color="#2c3e50", size=(0.148, 0.21, 0.012), band=True):
    """A hardback notebook with rounded corners, page block and an elastic band."""
    root = _group(name, col, loc, rot_z)
    w, d, t = size
    cover = M.leather(f"{name}_cover", color, rough=0.6, wear=0.4)
    pages = M.paper(f"{name}_pages", "#efe8d6", rough=0.8, age=0.3)
    c = box(f"{name}_cover", w, d, t, (0, 0, t / 2), cover, col, bevel=0.0015, segments=3)
    _parent(c, root)
    p = box(f"{name}_pageblock", w - 0.004, d - 0.006, t - 0.0035, (0.002, 0, t / 2), pages, col, bevel=0.0006)
    _parent(p, root)
    if band:
        b = box(f"{name}_band", 0.006, d + 0.0012, t + 0.0012, (w / 2 - 0.018, 0, t / 2),
                M.fabric(f"{name}_elastic", "#1b1b1b", threads_per_m=4000, rough=0.7, sheen=0.3), col, bevel=0.0005)
        _parent(b, root)
    rib = box(f"{name}_ribbon", 0.004, 0.06, 0.0004, (0.02, -d / 2 - 0.025, 0.0002),
              M.fabric(f"{name}_ribbon", "#8c2f2f", threads_per_m=5000, rough=0.4, sheen=0.9), col)
    _parent(rib, root)
    return root


STAMP_COLOURS = ["#b8333a", "#2f5a8a", "#3f7a4a", "#c99a2e", "#6a3c7a"]


def postage_stamps(name, col, loc, count=4, rng=None):
    """A few used stamps, slightly curled, perforated edges."""
    rng = rng or random.Random(3)
    root = _group(name, col, loc)
    for i in range(count):
        colr = rng.choice(STAMP_COLOURS)
        sw, sh = rng.choice([(0.022, 0.026), (0.026, 0.022), (0.02, 0.024)])
        frame = M.paper("StampPaper", "#f1ebdc", rough=0.7, age=0.4)
        s = box(f"{name}_{i}", sw, sh, 0.00012, (rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03),
                                                0.00006 + i * 0.00015), frame, col)
        s.rotation_euler = (0, 0, rng.uniform(-0.5, 0.5))
        _parent(s, root)
        ink = box(f"{name}_{i}_ink", sw * 0.78, sh * 0.78, 0.00005, (0, 0, 0.00009),
                  M.paper(f"StampInk{colr}", colr, rough=0.6, age=0.5), col)
        _parent(ink, s)
        # perforation: a ring of tiny bites along each edge
        bites = M.paper("StampBite", "#d9cfb8", rough=0.8, age=0.3)
        for k in range(8):
            for ex, ey, ox, oy in ((-sw / 2, -sh / 2, sw / 7, 0), (-sw / 2, sh / 2, sw / 7, 0)):
                bt = cylinder(f"{name}_{i}_b", 0.0006, 0.00016, (ex + ox * k, ey + oy * k, -0.00002), bites, col, 8)
                _parent(bt, s)
    return root


def matchbox(name, col, loc, rot_z=0.0, label="#c2412f", open_frac=0.4, rng=None):
    """A safety-match box with its drawer half out, a few matches and one spent one beside it."""
    rng = rng or random.Random(5)
    root = _group(name, col, loc, rot_z)
    w, d, h = 0.053, 0.036, 0.016
    card = M.paper(f"{name}_card", label, rough=0.7, age=0.5)
    strike = M.paper(f"{name}_strike", "#4a2a1e", rough=0.95, age=0.2)
    inner = M.paper(f"{name}_tray", "#d9c49b", rough=0.8, age=0.4)
    sleeve = box(f"{name}_sleeve", w, d, h, (0, 0, h / 2), card, col, bevel=0.0004)
    _parent(sleeve, root)
    for sy in (-1, 1):
        s = box(f"{name}_strip", w * 0.9, 0.0004, h * 0.7, (0, sy * d / 2, h / 2), strike, col)
        _parent(s, root)
    tray_x = w * open_frac
    tray = box(f"{name}_tray", w - 0.002, d - 0.002, h - 0.002, (tray_x, 0, h / 2), inner, col, bevel=0.0003)
    _parent(tray, root)
    wood = M.wood(f"{name}_matchwood", "pine", varnish=0.0, wear=0.0, scale=8.0, grain_axis="X")
    head = M.plastic(f"{name}_head", "#8a1e1a", rough=0.6)
    burnt = M.plastic(f"{name}_burnt", "#141210", rough=0.8)
    for i in range(6):
        y = -d / 2 + 0.006 + i * 0.0045
        m = box(f"{name}_match", 0.046, 0.0022, 0.0022, (tray_x + 0.001, y, h - 0.003), wood, col)
        m.rotation_euler = (0, 0, rng.uniform(-0.04, 0.04))
        _parent(m, root)
        hd = box(f"{name}_mhead", 0.004, 0.0032, 0.003, (tray_x + 0.025, y, h - 0.003), head, col, bevel=0.0012)
        _parent(hd, root)
    spent = box(f"{name}_spent", 0.03, 0.0022, 0.0022, (-0.05, 0.03, 0.0011), wood, col)
    spent.rotation_euler = (0, 0, rng.uniform(0.3, 1.2))
    _parent(spent, root)
    char = box(f"{name}_char", 0.012, 0.0024, 0.0024, (0.017, 0, 0), burnt, col, bevel=0.0009)
    _parent(char, spent)
    return root


def tea_towel(name, col, loc, rot_z=0.0, color="#f0ebdf", stripe="#3f5d8a"):
    """A folded linen tea towel with a woven stripe, its folds slightly soft."""
    root = _group(name, col, loc, rot_z)
    cloth = M.fabric(f"{name}_linen", color, threads_per_m=2200, rough=0.9, sheen=0.5, pattern="stripe",
                     pattern_color=stripe, pattern_scale=8.0)
    for i in range(3):
        f = box(f"{name}_fold{i}", 0.24 - i * 0.003, 0.16 - i * 0.002, 0.0028, (i * 0.0015, i * 0.001,
                                                                                 0.0014 + i * 0.0026),
                cloth, col, bevel=0.0012, segments=3)
        _parent(f, root)
    return root


def sugar_bowl(name, col, loc, rot_z=0.0, color="#e8e2d4", spoon=True):
    """Lidded sugar bowl with a teaspoon handle poking out from under the lid."""
    root = _group(name, col, loc, rot_z)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.04, speckle=0.15, crazing=0.35)
    bowl = lathe(f"{name}_bowl", [(0.0, 0.0), (0.028, 0.0), (0.03, 0.004), (0.045, 0.03), (0.046, 0.052),
                                  (0.043, 0.054), (0.041, 0.05), (0.028, 0.009), (0.0, 0.008)], 64, glaze, col)
    add_subsurf(bowl, 1, 2)
    _parent(bowl, root)
    lid = lathe(f"{name}_lid", [(0.0, 0.074), (0.007, 0.073), (0.008, 0.068), (0.012, 0.064), (0.045, 0.057),
                                (0.047, 0.054), (0.04, 0.053), (0.0, 0.06)], 64, glaze, col)
    lid.rotation_euler = (math.radians(4), 0, 0)
    _parent(lid, root)
    if spoon:
        sp = box(f"{name}_spoon", 0.006, 0.075, 0.0016, (0.0, 0.05, 0.068), M.metal("Spoon", "#cfd1d3", 0.2, 0.4, 0.2),
                 col, bevel=0.0007)
        sp.rotation_euler = (math.radians(-22), 0, 0)
        _parent(sp, root)
    return root


def newspaper(name, col, loc, rot_z=0.0):
    """A folded newspaper: thick folded stack of newsprint with columns of type."""
    root = _group(name, col, loc, rot_z)
    paper = M.paper(f"{name}_news", "#e6e0d0", rough=0.85, age=0.5, ink_lines=True, line_color="#3a3a3a")
    for i in range(4):
        sheet = box(f"{name}_sheet{i}", 0.29 - i * 0.002, 0.2, 0.0015, (i * 0.0008, 0, 0.00075 + i * 0.0015), paper, col,
                    bevel=0.0007)
        sheet.rotation_euler = (0, 0, (i - 1.5) * 0.008)
        _parent(sheet, root)
    head = box(f"{name}_masthead", 0.2, 0.025, 0.0002, (0.0, 0.07, 0.0062), M.plastic("Masthead", "#1d1d1d", 0.6), col)
    _parent(head, root)
    pic = box(f"{name}_photo", 0.08, 0.06, 0.0002, (-0.07, 0.0, 0.0062), M.plastic("NewsPhoto", "#5c5a56", 0.7), col)
    _parent(pic, root)
    return root


def teddy_bear(name, col, loc, rot_z=0.0, color="#8a6440"):
    """A well-loved sitting teddy bear: plush body, head, ears, limbs, button eyes, worn paw pads."""
    root = _group(name, col, loc, rot_z)
    plush = M.fabric(f"{name}_plush", color, threads_per_m=600, rough=0.95, sheen=1.0)
    pad = M.fabric(f"{name}_pads", "#d4b48a", threads_per_m=1600, rough=0.9, sheen=0.4)
    eye = M.plastic(f"{name}_eye", "#0c0b0a", rough=0.1, coat=1.0)

    def blob(nm, r, loc_, scale=(1, 1, 1), mat=plush):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=16, location=loc_)
        o = bpy.context.object
        o.name = f"{name}_{nm}"
        o.scale = scale
        o.data.materials.append(mat)
        set_smooth(o)
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
        o.parent = root
        return o
    blob("body", 0.07, (0, 0, 0.075), (0.9, 0.8, 1.05))
    blob("head", 0.055, (0, -0.01, 0.18))
    blob("muzzle", 0.025, (0, -0.058, 0.17), (1.0, 0.8, 0.8), pad)
    blob("nose", 0.008, (0, -0.078, 0.178), (1.3, 0.8, 0.8), eye)
    for s in (-1, 1):
        blob("ear", 0.02, (s * 0.042, 0.0, 0.225), (1, 0.6, 1))
        blob("eye", 0.0055, (s * 0.022, -0.05, 0.195), mat=eye)
        arm = blob("arm", 0.025, (s * 0.07, -0.02, 0.09), (0.8, 0.8, 1.6))
        arm.rotation_euler = (math.radians(-25), s * math.radians(20), 0)
        leg = blob("leg", 0.03, (s * 0.045, -0.06, 0.03), (0.9, 1.6, 0.85))
        blob("foot", 0.022, (s * 0.045, -0.105, 0.032), (1.0, 0.4, 1.1), pad)
    return root


def rolled_rug(name, col, loc, rot_z=0.0, length=1.2, radius=0.09, color="#7a3a2c"):
    """A rolled-up rug tied with string, lying on the floor: you can see the spiral at the ends."""
    root = _group(name, col, loc, rot_z)
    wool = M.fabric(f"{name}_wool", color, threads_per_m=500, rough=0.95, sheen=0.4, pattern="gingham",
                    pattern_color="#c9a66b", pattern_scale=4.0)
    roll = cylinder(f"{name}_roll", radius, length, (0, -length / 2, radius), wool, col, 48,
                    rot=(math.radians(-90), 0, 0))
    roll.location = (0, -length / 2, radius)
    _parent(roll, root)
    edge = M.fabric(f"{name}_edge", "#3a2018", threads_per_m=500, rough=0.95, sheen=0.3)
    for k in range(4):  # spiral layers visible at the ends
        for y in (-length / 2 - 0.0015, length / 2 + 0.0015):
            ring = cylinder(f"{name}_layer{k}", radius * (1 - k * 0.22), 0.002, (0, y, radius), edge if k % 2 else wool,
                            col, 32, rot=(math.radians(-90), 0, 0))
            _parent(ring, root)
    twine = M.fabric(f"{name}_twine", "#a5865c", threads_per_m=2500, rough=0.9, sheen=0.4)
    for y in (-length * 0.3, length * 0.3):
        t = cylinder(f"{name}_tie", radius + 0.003, 0.006, (0, y, radius), twine, col, 32, rot=(math.radians(-90), 0, 0))
        _parent(t, root)
    return root


def tissue_box(name, col, loc, rot_z=0.0, color="#9db4c0"):
    """A box of tissues with one pulled half out, soft and crumpled."""
    root = _group(name, col, loc, rot_z)
    card = M.plastic(f"{name}_card", color, rough=0.5, coat=0.2)
    b = box(f"{name}_box", 0.12, 0.12, 0.13, (0, 0, 0.065), card, col, bevel=0.003)
    _parent(b, root)
    slot = box(f"{name}_slot", 0.07, 0.025, 0.002, (0, 0, 0.13), M.plastic("TissueSlot", "#e9eef0", 0.6), col,
               bevel=0.0008)
    _parent(slot, root)
    tissue = M.fabric(f"{name}_tissue", "#fbfaf6", threads_per_m=100, rough=1.0, sheen=0.2, translucent=0.4)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=12, y_segments=12, size=0.045)
    rng = random.Random(9)
    for v in bm.verts:
        v.co.z = 0.04 * (1 - (abs(v.co.x) / 0.045) ** 2) + rng.uniform(-0.004, 0.004)
        v.co.y *= 0.4 + 0.6 * (v.co.z / 0.04)
    t = mesh_object(f"{name}_tissue", bm, col, mat=tissue)
    t.location = (0, 0, 0.13)
    t.rotation_euler = (math.radians(90), 0, 0)
    sol = t.modifiers.new("Thick", "SOLIDIFY")
    sol.thickness = 0.0004
    add_subsurf(t, 1, 2)
    set_smooth(t)
    _parent(t, root)
    return root


def ring_dish(name, col, loc, rot_z=0.0, color="#e9e3d6"):
    """A little china trinket dish with a gold ring and a pair of earrings in it."""
    root = _group(name, col, loc, rot_z)
    glaze = M.ceramic(f"{name}_glaze", color, rough=0.03, speckle=0.1, crazing=0.2)
    dish = lathe(f"{name}_dish", [(0.0, 0.0), (0.025, 0.0), (0.028, 0.003), (0.045, 0.013), (0.047, 0.016),
                                  (0.044, 0.016), (0.026, 0.006), (0.0, 0.005)], 64, glaze, col)
    _parent(dish, root)
    gold = M.metal(f"{name}_gold", "#d4a94e", rough=0.12, smudge=0.2, tarnish=0.05)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0095, minor_radius=0.0013, major_segments=48, minor_segments=12,
                                     location=(0.008, 0.004, 0.0072))
    ring = bpy.context.object
    ring.name = f"{name}_ring"
    ring.rotation_euler = (math.radians(12), 0, 0)
    ring.data.materials.append(gold)
    set_smooth(ring)
    for c in ring.users_collection:
        c.objects.unlink(ring)
    col.objects.link(ring)
    _parent(ring, root)
    pearl = M.ceramic(f"{name}_pearl", "#f2ece0", rough=0.15, speckle=0.0)
    for k in range(2):
        e = cylinder(f"{name}_earring{k}", 0.003, 0.006, (-0.012 + k * 0.007, -0.008, 0.0055), pearl, col, 16)
        _parent(e, root)
    return root


def paper_coffee_cup(name, col, loc, rot_z=0.0, sleeve="#8a6a4a", lid=True):
    """A takeaway coffee cup: tapered paper cup, card sleeve, plastic lid."""
    root = _group(name, col, loc, rot_z)
    cup = lathe(f"{name}_cup", [(0.0, 0.0), (0.028, 0.0), (0.029, 0.002), (0.04, 0.11), (0.0405, 0.112),
                                (0.039, 0.112), (0.0, 0.11)], 48, M.paper(f"{name}_paper", "#f1efe9", 0.6, 0.1), col)
    _parent(cup, root)
    sl = lathe(f"{name}_sleeve", [(0.0325, 0.03), (0.0375, 0.075), (0.0365, 0.075), (0.0315, 0.03)], 48,
               M.paper(f"{name}_sleevecard", sleeve, 0.85, 0.3), col)
    _parent(sl, root)
    if lid:
        l_ = lathe(f"{name}_lid", [(0.0, 0.122), (0.03, 0.122), (0.036, 0.12), (0.042, 0.116), (0.042, 0.11),
                                   (0.039, 0.109), (0.0, 0.109)], 48, M.plastic(f"{name}_lid", "#1c1c1c", 0.3), col)
        _parent(l_, root)
    return root


def evidence_bag(name, col, loc, rot_z=0.0, rng=None):
    """A clear plastic evidence bag with a red seal strip and a white write-on panel."""
    rng = rng or random.Random(11)
    root = _group(name, col, loc, rot_z)
    plastic = M.glass(f"{name}_poly", "#f6f6f2", rough=0.25, ior=1.45, smudge=0.6, thin=True)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=10, y_segments=14, size=1.0)
    for v in bm.verts:
        v.co.x *= 0.115
        v.co.y *= 0.155
        v.co.z = 0.004 + rng.uniform(-0.0015, 0.0015)
    bag = mesh_object(f"{name}_bag", bm, col, mat=plastic)
    add_subsurf(bag, 1, 2)
    set_smooth(bag)
    _parent(bag, root)
    seal = box(f"{name}_seal", 0.23, 0.012, 0.0006, (0, 0.14, 0.0045), M.plastic(f"{name}_red", "#b0201c", 0.4), col)
    _parent(seal, root)
    panel = box(f"{name}_panel", 0.15, 0.09, 0.0003, (0, -0.08, 0.0042),
                M.paper(f"{name}_panel", "#f4f2ea", 0.7, 0.1, ink_lines=True, line_color="#2a2a40"), col)
    _parent(panel, root)
    inside = box(f"{name}_item", 0.06, 0.035, 0.008, (0.02, 0.05, 0.002),
                 M.metal(f"{name}_item", "#6b6b6b", 0.35, 0.5, 0.3), col, bevel=0.002)
    inside.rotation_euler = (0, 0, rng.uniform(-0.6, 0.6))
    _parent(inside, root)
    return root


def manila_folder(name, col, loc, rot_z=0.0, papers=3, rng=None):
    """A manila case file with a few sheets poking out and a typed label."""
    rng = rng or random.Random(13)
    root = _group(name, col, loc, rot_z)
    manila = M.paper(f"{name}_manila", "#d8bf86", 0.8, 0.5)
    f = box(f"{name}_folder", 0.235, 0.31, 0.0025, (0, 0, 0.00125), manila, col, bevel=0.0006)
    _parent(f, root)
    tab = box(f"{name}_tab", 0.08, 0.018, 0.0012, (0.06, 0.163, 0.0006), manila, col, bevel=0.0004)
    _parent(tab, root)
    label = box(f"{name}_label", 0.07, 0.012, 0.0002, (0.06, 0.163, 0.0013),
                M.paper(f"{name}_label", "#f2f0e8", 0.7, 0.2, ink_lines=True, line_color="#222222"), col)
    _parent(label, root)
    sheet = M.paper(f"{name}_sheets", "#f0ece0", 0.75, 0.3, ink_lines=True, line_color="#333333")
    for i in range(papers):
        s = box(f"{name}_sheet{i}", 0.21, 0.297, 0.0003, (rng.uniform(-0.01, 0.03), rng.uniform(-0.03, 0.01),
                                                          0.0027 + i * 0.0004), sheet, col)
        s.rotation_euler = (0, 0, rng.uniform(-0.12, 0.12))
        _parent(s, root)
    return root


# ---------------------------------------------------------------------------
# Second round: things with a story
# ---------------------------------------------------------------------------

def _torus(name, col, major, minor, loc, rot=(0, 0, 0), mat=None, seg=(32, 10)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=seg[0],
                                     minor_segments=seg[1], location=loc)
    o = bpy.context.object
    o.name = name
    o.rotation_euler = rot
    if mat is not None:
        o.data.materials.append(mat)
    set_smooth(o)
    for c in o.users_collection:
        c.objects.unlink(o)
    col.objects.link(o)
    return o


def film_camera(name, col, loc, rot_z=0.0):
    """A 1970s 35mm SLR: leatherette body, chrome top plate, prism hump, a fast standard lens."""
    root = _group(name, col, loc, rot_z)
    chrome = M.metal(f"{name}_chrome", "#c8c9ca", rough=0.18, smudge=0.5, tarnish=0.1)
    black = M.metal(f"{name}_black", "#161616", rough=0.35, smudge=0.4, tarnish=0.0)
    skin = M.leather(f"{name}_skin", "#121212", rough=0.75, wear=0.5)
    glass = M.glass(f"{name}_glass", "#cfd8ff", 0.0, 1.6, smudge=0.2)
    w, d, h = 0.142, 0.036, 0.062
    for o in (box(f"{name}_body", w, d, h, (0, 0, h / 2), skin, col, bevel=0.004),
              box(f"{name}_top", w - 0.004, d + 0.002, 0.018, (0, 0, h + 0.009), chrome, col, bevel=0.003),
              box(f"{name}_base", w - 0.004, d + 0.002, 0.006, (0, 0, 0.003), chrome, col, bevel=0.002)):
        _parent(o, root)
    prism = box(f"{name}_prism", 0.05, 0.042, 0.03, (0, 0.002, h + 0.03), chrome, col, bevel=0.004)
    prism.scale = (1.0, 1.0, 1.0)
    bm = bmesh.new()
    bm.from_mesh(prism.data)
    for v in bm.verts:   # taper the hump
        if v.co.z > 0:
            v.co.x *= 0.62
            v.co.y *= 0.75
    bm.to_mesh(prism.data)
    bm.free()
    _parent(prism, root)
    for x, r_, hh in ((-0.05, 0.011, 0.007), (0.045, 0.013, 0.006), (0.058, 0.004, 0.012)):
        k = cylinder(f"{name}_dial", r_, hh, (x, 0, h + 0.018), chrome, col, 32, bevel=0.001)
        _parent(k, root)
    lever = box(f"{name}_lever", 0.035, 0.008, 0.002, (0.052, 0.012, h + 0.026), chrome, col, bevel=0.0008)
    lever.rotation_euler = (0, 0, math.radians(25))
    _parent(lever, root)
    # lens: mount ring, focus barrel, aperture ring, front element
    zc = h / 2 + 0.002
    for i, (r_, ln, m) in enumerate(((0.027, 0.006, chrome), (0.028, 0.022, black), (0.026, 0.008, chrome),
                                     (0.0275, 0.012, black))):
        y0 = -d / 2 - sum(x[1] for x in ((0.027, 0.006), (0.028, 0.022), (0.026, 0.008), (0.0275, 0.012))[:i])
        c = cylinder(f"{name}_lens{i}", r_, ln, (0, y0, zc), m, col, 48, bevel=0.0008,
                     rot=(math.radians(90), 0, 0))
        _parent(c, root)
    front = -d / 2 - 0.048
    el = cylinder(f"{name}_element", 0.019, 0.002, (0, front + 0.001, zc), glass, col, 48,
                  rot=(math.radians(90), 0, 0))
    _parent(el, root)
    return root


def film_canister(name, col, loc, rot_z=0.0, label="#e3b23c", band="#b2312a"):
    """A 35mm film cassette: printed label, steel caps, a tongue of film out of the felt slot."""
    root = _group(name, col, loc, rot_z)
    steel = M.metal(f"{name}_steel", "#a9abad", 0.3, 0.4, 0.1)
    lab = M.plastic(f"{name}_label", label, 0.4, 0.3)
    for o in (cylinder(f"{name}_shell", 0.0125, 0.046, (0, 0, 0.0035), lab, col, 32),
              cylinder(f"{name}_band", 0.01255, 0.012, (0, 0, 0.02), M.plastic(f"{name}_band", band, 0.4, 0.3), col, 32),
              cylinder(f"{name}_capb", 0.0128, 0.0035, (0, 0, 0.0), steel, col, 32, bevel=0.0006),
              cylinder(f"{name}_capt", 0.0128, 0.0035, (0, 0, 0.0495), steel, col, 32, bevel=0.0006),
              cylinder(f"{name}_spool", 0.004, 0.006, (0, 0, 0.053), steel, col, 16)):
        _parent(o, root)
    tongue = box(f"{name}_tongue", 0.0006, 0.022, 0.034, (0.0105, -0.012, 0.0265),
                 M.plastic(f"{name}_film", "#5a2c16", 0.15, 0.6), col)
    _parent(tongue, root)
    return root


def pocket_watch(name, col, loc, rot_z=0.0, rng=None):
    """A gold pocket watch lying face up, its chain trailing off in a loose curl."""
    rng = rng or random.Random(17)
    root = _group(name, col, loc, rot_z)
    gold = M.metal(f"{name}_gold", "#c9a24e", rough=0.15, smudge=0.5, tarnish=0.3)
    case = lathe(f"{name}_case", [(0.0, 0.0), (0.019, 0.0), (0.0235, 0.003), (0.024, 0.006), (0.0225, 0.0095),
                                  (0.0, 0.0095)], 64, gold, col)
    _parent(case, root)
    dial = cylinder(f"{name}_dial", 0.0205, 0.0004, (0, 0, 0.0092), M.ceramic(f"{name}_enamel", "#f2ecdc", 0.1, 0.1,
                                                                            0.3), col, 64)
    _parent(dial, root)
    ink = M.metal(f"{name}_hands", "#1c1c22", 0.3, 0.1, 0.0)
    for k in range(12):   # hour marks
        a = k * math.pi / 6
        mk = box(f"{name}_mark", 0.0008, 0.0026, 0.0002, (math.sin(a) * 0.0175, math.cos(a) * 0.0175, 0.0097), ink, col)
        mk.rotation_euler = (0, 0, -a)
        _parent(mk, root)
    for ln, ang in ((0.011, rng.uniform(0, 6.28)), (0.016, rng.uniform(0, 6.28))):
        hd = box(f"{name}_hand", 0.0009, ln, 0.0003, (math.sin(ang) * ln / 2, math.cos(ang) * ln / 2, 0.0099), ink, col)
        hd.rotation_euler = (0, 0, -ang)
        _parent(hd, root)
    crystal = lathe(f"{name}_crystal", [(0.0, 0.0115), (0.012, 0.0108), (0.0205, 0.0095), (0.0, 0.0095)], 64,
                    M.glass(f"{name}_crystal", "#ffffff", 0.0, 1.5, 0.3), col)
    _parent(crystal, root)
    crown = cylinder(f"{name}_crown", 0.003, 0.005, (0, 0.024, 0.005), gold, col, 24, rot=(math.radians(-90), 0, 0))
    _parent(crown, root)
    bow = _torus(f"{name}_bow", col, 0.006, 0.0011, (0, 0.033, 0.0012), mat=gold)
    _parent(bow, root)
    # chain: links along a lazy curve on the surface
    pts = []
    a = 0.0
    p = Vector((0, 0.04, 0.0012))
    for i in range(26):
        a += rng.uniform(-0.25, 0.3)
        p = p + Vector((math.sin(a) * 0.0055, math.cos(a) * 0.0055, 0))
        pts.append((p.copy(), a))
    for i, (q, ang) in enumerate(pts):
        lk = _torus(f"{name}_link", col, 0.0024, 0.0005, q, rot=(math.radians(90) if i % 2 else 0, 0, -ang), mat=gold,
                    seg=(12, 6))
        _parent(lk, root)
    return root


def ink_bottle(name, col, loc, rot_z=0.0, ink="#14183a"):
    """A squat glass ink bottle, ink line on the inside, a black screw cap."""
    root = _group(name, col, loc, rot_z)
    glass = M.glass(f"{name}_glass", "#eef3ee", 0.02, 1.5, 0.4)
    btl = _outward(lathe(f"{name}_bottle", [(0.0, 0.0), (0.03, 0.0), (0.032, 0.004), (0.032, 0.036), (0.026, 0.044),
                                   (0.013, 0.048), (0.013, 0.056), (0.0115, 0.056), (0.0115, 0.049), (0.024, 0.043),
                                   (0.029, 0.036), (0.029, 0.006), (0.0, 0.006)], 64, glass, col))
    _parent(btl, root)
    fill = _outward(lathe(f"{name}_ink", [(0.0, 0.0059), (0.0291, 0.0059), (0.0291, 0.022), (0.0, 0.022)], 64,
                          M.glass(f"{name}_inkliquid", ink, 0.05, 1.34, 0.0), col))
    _parent(fill, root)
    cap = cylinder(f"{name}_cap", 0.015, 0.014, (0, 0, 0.05), M.plastic(f"{name}_cap", "#121212", 0.35, 0.2), col, 48,
                   bevel=0.001)
    _parent(cap, root)
    lab = lathe(f"{name}_label", [(0.03215, 0.012), (0.03215, 0.028)], 64,
                M.paper(f"{name}_label", "#e8dcbc", 0.6, 0.5, ink_lines=True, line_color="#3a2a1a"), col, smooth=True)
    _parent(lab, root)
    return root


def sealed_letter(name, col, loc, rot_z=0.0, wax="#7a1218"):
    """An envelope face down, closed with a blob of sealing wax pressed with a seal."""
    root = envelope(name, col, loc, rot_z)
    wax_m = M.plastic(f"{name}_wax", wax, rough=0.35, coat=0.6)
    blob = lathe(f"{name}_wax", [(0.0, 0.0), (0.012, 0.0), (0.0135, 0.0012), (0.012, 0.0024), (0.0085, 0.0028),
                                 (0.0085, 0.0022), (0.0, 0.0022)], 40, wax_m, col)
    rng = random.Random(len(name))
    for v in blob.data.vertices:
        r_ = math.hypot(v.co.x, v.co.y)
        if r_ > 0.0105:
            k = 1 + rng.uniform(-0.12, 0.18)
            v.co.x *= k
            v.co.y *= k
    blob.location = (0.0, -0.02, 0.0012)
    _parent(blob, root)
    return root


def radio(name, col, loc, rot_z=0.0, wood="walnut"):
    """A 1950s mantel radio: veneered cabinet, cloth speaker grille, glass dial, two bakelite knobs."""
    root = _group(name, col, loc, rot_z)
    veneer = M.wood(f"{name}_veneer", wood, varnish=0.8, wear=0.3, scale=3.0, grain_axis="X")
    cab = box(f"{name}_cabinet", 0.32, 0.15, 0.19, (0, 0, 0.095), veneer, col, bevel=0.018, segments=4)
    _parent(cab, root)
    grille = box(f"{name}_grille", 0.15, 0.004, 0.12, (-0.065, -0.074, 0.1),
                 M.fabric(f"{name}_cloth", "#b39b72", threads_per_m=1200, rough=0.9, sheen=0.6, pattern="gingham",
                          pattern_color="#8a7550", pattern_scale=40.0), col, bevel=0.002)
    _parent(grille, root)
    dial = box(f"{name}_dial", 0.11, 0.004, 0.05, (0.085, -0.074, 0.125), M.paper(f"{name}_dialface", "#e9dcb4", 0.4,
                                                                                    0.4, ink_lines=True,
                                                                                    line_color="#2a2a2a"), col)
    _parent(dial, root)
    gl = box(f"{name}_dialglass", 0.112, 0.002, 0.052, (0.085, -0.0775, 0.125), M.glass(f"{name}_glass", "#ffffff", 0.0,
                                                                                        1.5, 0.3), col)
    _parent(gl, root)
    bak = M.plastic(f"{name}_bakelite", "#3a2414", 0.25, 0.6)
    for x in (0.055, 0.115):
        k = cylinder(f"{name}_knob", 0.012, 0.014, (x, -0.074, 0.055), bak, col, 32, bevel=0.003,
                     rot=(math.radians(90), 0, 0))
        _parent(k, root)
    return root


def kettle(name, col, loc, rot_z=0.0, color="#e8e2d4"):
    """An enamel stovetop kettle with a black knob and a wire-and-wood handle."""
    root = _group(name, col, loc, rot_z)
    enamel = M.ceramic(f"{name}_enamel", color, rough=0.12, speckle=0.15, crazing=0.0)
    body = lathe(f"{name}_body", [(0.0, 0.0), (0.085, 0.0), (0.095, 0.01), (0.097, 0.06), (0.085, 0.12),
                                  (0.05, 0.15), (0.045, 0.155), (0.0, 0.155)], 64, enamel, col)
    add_subsurf(body, 1, 2)
    _parent(body, root)
    knob = cylinder(f"{name}_knob", 0.012, 0.016, (0, 0, 0.155), M.plastic(f"{name}_knob", "#141414", 0.3), col, 24,
                    bevel=0.004)
    _parent(knob, root)
    spout = cylinder(f"{name}_spout", 0.014, 0.12, (0.07, 0, 0.04), enamel, col, 24, radius2=0.008)
    spout.rotation_euler = (0, math.radians(52), 0)
    _parent(spout, root)
    steel = M.metal(f"{name}_wire", "#bfc1c3", 0.3, 0.3, 0.1)
    pts = [(-0.055 + 0.11 * k / 16, 0, 0.14 + 0.09 * math.sin(math.pi * k / 16)) for k in range(17)]
    wire = _curve(f"{name}_handle", col, pts, 0.0022, steel)
    _parent(wire, root)
    grip = cylinder(f"{name}_grip", 0.009, 0.06, (-0.03, 0, 0.228), M.wood(f"{name}_grip", "walnut", 0.6, 0.3), col, 24,
                    rot=(0, math.radians(90), 0))
    _parent(grip, root)
    return root


def _curve(name, col, pts, radius, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for k, p in enumerate(pts):
        sp.points[k].co = (p[0], p[1], p[2], 1)
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    o = bpy.data.objects.new(name, cu)
    link(o, col)
    o.data.materials.append(mat)
    return o


def hurricane_lantern(name, col, loc, rot_z=0.0, lit=False):
    """A paraffin hurricane lantern: rusty tank, glass globe, wire guard and bail handle. Returns (root, light)."""
    root = _group(name, col, loc, rot_z)
    tin = M.metal(f"{name}_tin", "#6d5a46", rough=0.6, smudge=0.6, tarnish=0.9)
    tank = lathe(f"{name}_tank", [(0.0, 0.0), (0.07, 0.0), (0.075, 0.02), (0.065, 0.05), (0.03, 0.06), (0.0, 0.06)],
                 48, tin, col)
    _parent(tank, root)
    globe = lathe(f"{name}_globe", [(0.03, 0.06), (0.055, 0.1), (0.06, 0.14), (0.045, 0.19), (0.032, 0.21)], 48,
                  M.glass(f"{name}_globe", "#f4f0e4", 0.04, 1.5, 0.9), col)
    sol = globe.modifiers.new("Thick", "SOLIDIFY")
    sol.thickness = 0.002
    _parent(globe, root)
    top = lathe(f"{name}_top", [(0.0, 0.25), (0.045, 0.235), (0.05, 0.215), (0.03, 0.205), (0.0, 0.205)], 48, tin, col)
    _parent(top, root)
    for k in range(4):   # wire guard
        a = k * math.pi / 2 + 0.4
        pts = [(math.cos(a) * r_, math.sin(a) * r_, z) for r_, z in ((0.04, 0.06), (0.066, 0.1), (0.07, 0.14),
                                                                      (0.055, 0.19), (0.04, 0.215))]
        _parent(_curve(f"{name}_guard{k}", col, pts, 0.0016, tin), root)
    bail = [(math.cos(t) * 0.075, 0, 0.25 + math.sin(t) * 0.07) for t in [math.pi * i / 16 for i in range(17)]]
    _parent(_curve(f"{name}_bail", col, bail, 0.0018, tin), root)
    light = None
    if lit:
        fl = lathe(f"{name}_flame", [(0.0, 0.085), (0.007, 0.095), (0.006, 0.11), (0.0, 0.13)], 24,
                   M.flame(f"{name}_flame", 14.0), col)
        _parent(fl, root)
        ld = bpy.data.lights.new(f"{name}_light", "POINT")
        ld.energy = 3.5
        ld.shadow_soft_size = 0.01
        from .world import kelvin_rgb
        ld.color = kelvin_rgb(1900)
        light = bpy.data.objects.new(f"{name}_light", ld)
        link(light, col)
        light.location = (0, 0, 0.105)
        _parent(light, root)
    return root, light


def wristwatch(name, col, loc, rot_z=0.0):
    """A man's watch lying face up, leather strap open."""
    root = _group(name, col, loc, rot_z)
    steel = M.metal(f"{name}_steel", "#c9cacb", 0.2, 0.4, 0.05)
    case = cylinder(f"{name}_case", 0.018, 0.009, (0, 0, 0.003), steel, col, 48, bevel=0.0015)
    _parent(case, root)
    face = cylinder(f"{name}_face", 0.0155, 0.0004, (0, 0, 0.0121), M.ceramic(f"{name}_face", "#efe9dc", 0.1, 0.0, 0.0),
                    col, 48)
    _parent(face, root)
    gl = lathe(f"{name}_glass", [(0.0, 0.0135), (0.0158, 0.0122), (0.0, 0.0122)], 48,
               M.glass(f"{name}_glass", "#ffffff", 0.0, 1.5, 0.3), col)
    _parent(gl, root)
    ink = M.metal(f"{name}_hands", "#1c1c22", 0.3, 0.1, 0.0)
    for ln, ang in ((0.008, 1.1), (0.012, 4.0)):
        hd = box(f"{name}_hand", 0.0008, ln, 0.0002, (math.sin(ang) * ln / 2, math.cos(ang) * ln / 2, 0.0126), ink, col)
        hd.rotation_euler = (0, 0, -ang)
        _parent(hd, root)
    strap = M.leather(f"{name}_strap", "#4a2c1a", 0.55, 0.6)
    for s, ln in ((1, 0.075), (-1, 0.11)):
        st = box(f"{name}_strap", 0.019, ln, 0.0028, (0, s * (0.017 + ln / 2), 0.0016), strap, col, bevel=0.0009)
        _parent(st, root)
    buckle = _torus(f"{name}_buckle", col, 0.009, 0.0009, (0, 0.093, 0.002), mat=steel, seg=(24, 8))
    buckle.scale = (1.15, 0.7, 1)
    _parent(buckle, root)
    return root


def loupe(name, col, loc, rot_z=0.0):
    """A clear photographer's loupe standing on a print."""
    root = _group(name, col, loc, rot_z)
    clear = M.glass(f"{name}_body", "#f6f6f6", 0.08, 1.49, 0.3)
    body = lathe(f"{name}_body", [(0.019, 0.0), (0.021, 0.0), (0.017, 0.032), (0.015, 0.032)], 48, clear, col)
    _parent(body, root)
    lens = cylinder(f"{name}_lens", 0.016, 0.004, (0, 0, 0.03), M.glass(f"{name}_lens", "#ffffff", 0.0, 1.55, 0.1),
                    col, 48)
    _parent(lens, root)
    rim = cylinder(f"{name}_rim", 0.0172, 0.006, (0, 0, 0.031), M.plastic(f"{name}_rim", "#141414", 0.3), col, 48)
    _parent(rim, root)
    return root
