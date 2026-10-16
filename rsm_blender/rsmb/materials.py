"""Procedural physically based materials.

Everything is built from Blender's procedural textures so no image assets are
needed. Texture coordinates are object space in metres, so patterns keep a
real-world scale (wood grain spacing, fabric thread count, paint texture).
"""
from __future__ import annotations

import bpy

from .util import Nodes, new_material, srgb

_cache: dict[str, bpy.types.Material] = {}


def _principled(n: Nodes, **kw):
    return n.new("ShaderNodeBsdfPrincipled", **kw)


def _output(n: Nodes, shader, displacement=None, volume=None):
    out = n.new("ShaderNodeOutputMaterial", _target="ALL")
    n.link(shader, None, out, "Surface")
    if displacement is not None:
        n.link(displacement, None, out, "Displacement")
    if volume is not None:
        n.link(volume, None, out, "Volume")
    return out


def _coords(n: Nodes, scale=(1, 1, 1), rotation=(0, 0, 0), space="Object", location=(0, 0, 0)):
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping", Scale=scale, Rotation=rotation, Location=location)
    n.link(tc, space, mp, "Vector")
    return mp


def _bump_chain(n: Nodes, layers):
    """layers: list of (height_output, strength, distance). Chains bump nodes."""
    normal = None
    for height, strength, distance in layers:
        b = n.new("ShaderNodeBump", Strength=strength, Distance=distance)
        n.link(height, None, b, "Height")
        if normal is not None:
            n.link(normal, None, b, "Normal")
        normal = b
    return normal


def _dust_layer(n: Nodes, base_color, base_rough, amount: float, scale=1.0):
    """Settled dust on upward-facing surfaces. Returns (color, roughness) sockets."""
    if amount <= 0:
        return base_color, base_rough
    geo = n.new("ShaderNodeNewGeometry")
    sep = n.new("ShaderNodeSeparateXYZ")
    n.link(geo, "Normal", sep, "Vector")
    up = (n.ramp((sep, "Z"), [(0.55, (0, 0, 0)), (0.95, (1, 1, 1))]), "Color")
    mp = _coords(n, scale=(60 * scale, 60 * scale, 60 * scale))
    noise = n.new("ShaderNodeTexNoise", Scale=1.0, Detail=10.0, Roughness=0.7)
    n.link(mp, None, noise, "Vector")
    patch = n.ramp((noise, "Fac"), [(0.42, (0, 0, 0)), (0.75, (1, 1, 1))])
    m = n.math("MULTIPLY", (patch, "Color"), up)
    m2 = n.math("MULTIPLY", m, amount, clamp=True)
    col = n.mix("RGBA", m2, base_color, srgb("#b9b2a6"))
    rough = n.mix("FLOAT", m2, base_rough, 0.95)
    return col, rough


# ---------------------------------------------------------------------------
# Wood
# ---------------------------------------------------------------------------

WOOD_PRESETS = {
    "oak": dict(dark="#6b4a2c", light="#a87b4f", ring=7.0, figure=0.6, fiber=0.35, rough=0.42),
    "walnut": dict(dark="#3a2417", light="#7a5235", ring=6.0, figure=0.8, fiber=0.3, rough=0.38),
    "pine": dict(dark="#9a6a3c", light="#d9b07a", ring=4.5, figure=0.9, fiber=0.25, rough=0.5),
    "mahogany": dict(dark="#4a2216", light="#8a4a2e", ring=9.0, figure=0.5, fiber=0.35, rough=0.35),
    "painted_white": dict(dark="#d8d3c8", light="#efebe2", ring=7.0, figure=0.1, fiber=0.08, rough=0.45),
    "aged_beam": dict(dark="#3d2b1e", light="#6e5238", ring=5.0, figure=1.0, fiber=0.6, rough=0.75),
}


def wood(name="Wood", preset="oak", varnish=0.6, wear=0.3, dust=0.0, scale=1.0, grain_axis="X", seed=0.0,
         planks: tuple[float, float] | None = None):
    """planks=(length, width) in metres lays the surface out as individual boards with gaps."""
    key = f"wood:{name}:{preset}:{varnish}:{wear}:{dust}:{scale}:{grain_axis}:{seed}:{planks}"
    if key in _cache:
        return _cache[key]
    p = WOOD_PRESETS.get(preset, WOOD_PRESETS["oak"])
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    rot = {"X": (0, 0, 0), "Y": (0, 0, 1.5708), "Z": (0, 1.5708, 0)}[grain_axis]
    s = scale
    base = _coords(n, scale=(1.0 * s, 1.0 * s, 1.0 * s), rotation=rot, location=(seed * 13.1, seed * 7.7, seed * 3.3))
    gaps = None
    plank_rand = None
    if planks:
        length, width = planks
        brick = n.new("ShaderNodeTexBrick", Scale=1.0, _offset=0.37, _offset_frequency=1)
        brick.inputs["Brick Width"].default_value = length
        brick.inputs["Row Height"].default_value = width
        brick.inputs["Mortar Size"].default_value = 0.0012
        brick.inputs["Mortar Smooth"].default_value = 0.3
        brick.inputs["Bias"].default_value = 0.0
        brick.inputs["Color1"].default_value = (0, 0, 0, 1)
        brick.inputs["Color2"].default_value = (1, 1, 1, 1)
        brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
        n.link(base, None, brick, "Vector")
        gaps = (brick, "Fac")
        plank_rand = (brick, "Color")
        # every board gets its own piece of the log
        jump = n.vmath("MULTIPLY", plank_rand, (37.3, 11.7, 23.1))
        base = n.vmath("ADD", base, jump)
    else:
        # solid tops are glued up from boards ~15 cm wide, each cut from a different part of the log, so a big
        # table doesn't show one endless field of parallel rings. No gaps, just the grain changing at each joint.
        glue = n.new("ShaderNodeTexBrick", Scale=1.0, _offset=0.0, _offset_frequency=1)
        glue.inputs["Brick Width"].default_value = 60.0
        glue.inputs["Row Height"].default_value = 0.11 + 0.08 * (seed % 1.0 if seed else 0.5)
        glue.inputs["Mortar Size"].default_value = 0.0
        glue.inputs["Bias"].default_value = 0.0
        glue.inputs["Color1"].default_value = (0, 0, 0, 1)
        glue.inputs["Color2"].default_value = (1, 1, 1, 1)
        # shift so the (60 m apart) end joints never land on an object; only the long joints remain
        n.link(n.vmath("ADD", base, (30.37, 0.0, 0.0)), None, glue, "Vector")
        plank_rand = (glue, "Color")
        base = n.vmath("ADD", base, n.vmath("MULTIPLY", plank_rand, (37.3, 11.7, 23.1)))
    # large-scale warp so growth rings meander
    warp_n = n.new("ShaderNodeTexNoise", Scale=1.1, Detail=5.0, Roughness=0.55)
    n.link(base, None, warp_n, "Vector")
    warp = n.vmath("MULTIPLY", n.vmath("SUBTRACT", (warp_n, "Color"), (0.5, 0.5, 0.5)),
                   (0.0, 0.055 * (0.4 + p["figure"]), 0.055 * (0.4 + p["figure"])))
    # the board is a slice through a log whose axis runs along X, offset so the heart isn't visible:
    # rings become long arches ("cathedrals") instead of parallel stripes
    log_axis = n.vmath("ADD", n.vmath("ADD", base, warp), (0.0, 0.31, 0.17))
    stretch = n.vmath("MULTIPLY", log_axis, (0.045, 1.0, 1.0))
    rings = n.new("ShaderNodeTexWave", _wave_type="RINGS", _rings_direction="SPHERICAL", _wave_profile="SAW",
                  Scale=p["ring"] * 2.2, Distortion=1.5 + 2.5 * p["figure"], Detail=4.0)
    rings.inputs["Detail Scale"].default_value = 1.4
    rings.inputs["Detail Roughness"].default_value = 0.6
    n.link(stretch, None, rings, "Vector")
    # latewood bands are sharper, so push the saw profile through a curve
    ring_curve = n.ramp((rings, "Fac"), [(0.0, (0, 0, 0)), (0.55, (0.1, 0.1, 0.1)), (0.86, (0.72, 0.72, 0.72)),
                                         (1.0, (0.42, 0.42, 0.42))])
    # fine fibres / pores
    fib_map = n.vmath("MULTIPLY", base, (6.0, 420.0, 420.0))
    fibres = n.new("ShaderNodeTexNoise", Scale=1.0, Detail=4.0, Roughness=0.6)
    n.link(fib_map, None, fibres, "Vector")
    pores = n.ramp((fibres, "Fac"), [(0.35, (1, 1, 1)), (0.62, (0, 0, 0))])
    # colour
    col = n.ramp((ring_curve, "Color"), [(0.0, srgb(p["light"])), (1.0, srgb(p["dark"]))])
    big_var = n.new("ShaderNodeTexNoise", Scale=0.8, Detail=3.0)
    n.link(base, None, big_var, "Vector")
    col2 = n.mix("RGBA", 0.25, (col, "Color"), (big_var, "Color"), blend="OVERLAY")
    if plank_rand is not None:
        # boards differ in tone (glued-up tops only a little); the gaps between loose boards are dark
        spread = ((0.78, 0.74, 0.7), (1.12, 1.08, 1.04)) if gaps is not None else ((0.9, 0.88, 0.86), (1.06, 1.05, 1.03))
        tone = n.ramp(plank_rand, [(0.0, spread[0]), (1.0, spread[1])])
        col2 = n.mix("RGBA", 1.0, col2, (tone, "Color"), blend="MULTIPLY")
        if gaps is not None:
            col2 = n.mix("RGBA", gaps, col2, srgb("#140c06"))   # brick Fac is 1 in the gaps
    col3 = n.mix("RGBA", n.math("MULTIPLY", (pores, "Color"), p["fiber"]), col2, srgb(p["dark"]), blend="MULTIPLY")
    # wear: lighter, matte patches where hands rest
    wear_n = n.new("ShaderNodeTexNoise", Scale=2.5, Detail=8.0, Roughness=0.65)
    n.link(base, None, wear_n, "Vector")
    wear_m = n.ramp((wear_n, "Fac"), [(0.55 - 0.15 * wear, (0, 0, 0)), (0.75, (1, 1, 1))])
    wear_fac = n.math("MULTIPLY", (wear_m, "Color"), wear * 0.6)
    col4 = n.mix("RGBA", wear_fac, col3, srgb(p["light"]), blend="SCREEN")
    rough = n.math("ADD", n.math("MULTIPLY", (ring_curve, "Color"), 0.08), p["rough"])
    rough2 = n.math("ADD", rough, n.math("MULTIPLY", wear_fac, 0.25))
    col_d, rough_d = _dust_layer(n, col4, rough2, dust)
    # micro scratches in the varnish
    scr_map = n.vmath("MULTIPLY", base, (1.0, 1.0, 1.0))
    scr = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="DIAGONAL", Scale=180.0,
                Distortion=30.0, Detail=2.0)
    n.link(scr_map, None, scr, "Vector")
    scr_r = n.ramp((scr, "Fac"), [(0.0, (0, 0, 0)), (0.03, (1, 1, 1)), (0.06, (0, 0, 0))])
    scr_mask = n.new("ShaderNodeTexNoise", Scale=4.0, Detail=2.0)
    n.link(base, None, scr_mask, "Vector")
    scr_f = n.math("MULTIPLY", (scr_r, "Color"), n.math("GREATER_THAN", (scr_mask, "Fac"), 0.55))
    coat_rough = n.math("ADD", 0.05 + 0.1 * wear, n.math("MULTIPLY", scr_f, 0.4))
    bsdf = _principled(n, Roughness=0.4)
    n.link(col_d, None, bsdf, "Base Color")
    n.link(rough_d, None, bsdf, "Roughness")
    bsdf.inputs["Coat Weight"].default_value = varnish
    n.link(coat_rough, None, bsdf, "Coat Roughness")
    bsdf.inputs["Coat IOR"].default_value = 1.5
    layers = [((ring_curve, "Color"), 0.12, 0.0008), ((pores, "Color"), 0.25, 0.00015), (scr_f, 0.08, 0.0001)]
    if gaps is not None:
        layers.append((n.math("SUBTRACT", 1.0, gaps), 1.0, 0.002))  # gaps sit lower
    normal = _bump_chain(n, layers)
    n.link(normal, None, bsdf, "Normal")
    coat_normal = _bump_chain(n, [(scr_f, 0.15, 0.00005), ((big_var, "Fac"), 0.02, 0.002)])
    n.link(coat_normal, None, bsdf, "Coat Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


# ---------------------------------------------------------------------------
# Painted / plaster surfaces
# ---------------------------------------------------------------------------

def plaster(name="Plaster", color="#d9cfbf", rough=0.85, bump=1.0, stains=0.2, dust=0.0):
    key = f"plaster:{name}:{color}:{rough}:{bump}:{stains}:{dust}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    big = n.new("ShaderNodeTexNoise", Scale=1.5, Detail=8, Roughness=0.6)
    n.link(mp, None, big, "Vector")
    fine = n.new("ShaderNodeTexNoise", Scale=900.0, Detail=4, Roughness=0.7)
    n.link(mp, None, fine, "Vector")
    trowel = n.new("ShaderNodeTexNoise", Scale=12.0, Detail=10, Roughness=0.7, Distortion=1.5)
    n.link(mp, None, trowel, "Vector")
    base = srgb(color)
    col = n.mix("RGBA", 0.08, base, (big, "Color"), blend="OVERLAY")
    stain_r = n.ramp((big, "Fac"), [(0.55, (0, 0, 0)), (0.85, (1, 1, 1))])
    col2 = n.mix("RGBA", n.math("MULTIPLY", (stain_r, "Color"), stains * 0.5), col, srgb("#a99a83"),
                 blend="MULTIPLY")
    col_d, rough_d = _dust_layer(n, col2, rough, dust)
    bsdf = _principled(n)
    n.link(col_d, None, bsdf, "Base Color")
    n.link(rough_d, None, bsdf, "Roughness")
    normal = _bump_chain(n, [((trowel, "Fac"), 0.15 * bump, 0.002), ((fine, "Fac"), 0.25 * bump, 0.0003)])
    n.link(normal, None, bsdf, "Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


# ---------------------------------------------------------------------------
# Ceramics, metals, glass, plastics
# ---------------------------------------------------------------------------

def ceramic(name="Ceramic", color="#6f8c80", rough=0.06, speckle=0.3, crazing=0.0, dust=0.0):
    key = f"ceramic:{name}:{color}:{rough}:{speckle}:{crazing}:{dust}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    pool = n.new("ShaderNodeTexNoise", Scale=18.0, Detail=6, Roughness=0.5)
    n.link(mp, None, pool, "Vector")
    col = n.mix("RGBA", 0.12, srgb(color), (pool, "Color"), blend="OVERLAY")
    spk = n.new("ShaderNodeTexVoronoi", Scale=900.0)
    n.link(mp, None, spk, "Vector")
    spk_r = n.ramp((spk, "Distance"), [(0.0, (1, 1, 1)), (0.12, (0, 0, 0))])
    col2 = n.mix("RGBA", n.math("MULTIPLY", (spk_r, "Color"), speckle), col, srgb("#3b2f28"))
    col_d, rough_d = _dust_layer(n, col2, rough, dust)
    bsdf = _principled(n)
    n.link(col_d, None, bsdf, "Base Color")
    n.link(rough_d, None, bsdf, "Roughness")
    bsdf.inputs["Coat Weight"].default_value = 1.0
    bsdf.inputs["Coat Roughness"].default_value = 0.02
    bsdf.inputs["Subsurface Weight"].default_value = 0.05
    layers = [((pool, "Fac"), 0.05, 0.001)]
    if crazing > 0:
        cr = n.new("ShaderNodeTexVoronoi", Scale=120.0, _feature="DISTANCE_TO_EDGE")
        n.link(mp, None, cr, "Vector")
        cr_r = n.ramp((cr, "Distance"), [(0.0, (1, 1, 1)), (0.02, (0, 0, 0))])
        layers.append(((cr_r, "Color"), 0.2 * crazing, 0.0001))
    normal = _bump_chain(n, layers)
    n.link(normal, None, bsdf, "Coat Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


def metal(name="Metal", color="#c9a25e", rough=0.25, smudge=0.4, tarnish=0.2, brushed=False):
    key = f"metal:{name}:{color}:{rough}:{smudge}:{tarnish}:{brushed}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    sm = n.new("ShaderNodeTexNoise", Scale=9.0, Detail=12, Roughness=0.7)
    n.link(mp, None, sm, "Vector")
    tar = n.new("ShaderNodeTexNoise", Scale=4.0, Detail=10, Roughness=0.65)
    n.link(mp, None, tar, "Vector")
    tar_r = n.ramp((tar, "Fac"), [(0.5, (0, 0, 0)), (0.8, (1, 1, 1))])
    col = n.mix("RGBA", n.math("MULTIPLY", (tar_r, "Color"), tarnish), srgb(color), srgb("#3d3324"))
    r = n.math("ADD", rough, n.math("MULTIPLY", n.math("SUBTRACT", (sm, "Fac"), 0.45), smudge))
    bsdf = _principled(n, Metallic=1.0)
    n.link(col, None, bsdf, "Base Color")
    n.link(r, None, bsdf, "Roughness")
    if brushed:
        bsdf.inputs["Anisotropic"].default_value = 0.7
        br_map = n.vmath("MULTIPLY", mp, (1.0, 2000.0, 1.0))
        br = n.new("ShaderNodeTexNoise", Scale=1.0, Detail=2)
        n.link(br_map, None, br, "Vector")
        normal = _bump_chain(n, [((br, "Fac"), 0.05, 0.0001)])
        n.link(normal, None, bsdf, "Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


def glass(name="Glass", tint="#ffffff", rough=0.0, ior=1.52, smudge=0.15, thin=False):
    key = f"glass:{name}:{tint}:{rough}:{ior}:{smudge}:{thin}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    sm = n.new("ShaderNodeTexNoise", Scale=14.0, Detail=10, Roughness=0.7)
    n.link(mp, None, sm, "Vector")
    smr = n.ramp((sm, "Fac"), [(0.55, (0, 0, 0)), (0.8, (1, 1, 1))])
    r = n.math("ADD", rough, n.math("MULTIPLY", (smr, "Color"), smudge * 0.2))
    bsdf = _principled(n, IOR=ior)
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["Base Color"].default_value = srgb(tint)
    n.link(r, None, bsdf, "Roughness")
    if thin:
        # window panes: thin sheet so it doesn't refract the whole view
        try:
            bsdf.inputs["Thin Film Thickness"].default_value = 0.0
        except KeyError:
            pass
    _output(n, bsdf)
    _cache[key] = mat
    return mat


def plastic(name="Plastic", color="#202020", rough=0.35, coat=0.0):
    key = f"plastic:{name}:{color}:{rough}:{coat}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    no = n.new("ShaderNodeTexNoise", Scale=300.0, Detail=3)
    n.link(mp, None, no, "Vector")
    bsdf = _principled(n, Roughness=rough)
    bsdf.inputs["Base Color"].default_value = srgb(color)
    bsdf.inputs["Coat Weight"].default_value = coat
    normal = _bump_chain(n, [((no, "Fac"), 0.03, 0.0002)])
    n.link(normal, None, bsdf, "Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


# ---------------------------------------------------------------------------
# Paper, card, fabric, leather
# ---------------------------------------------------------------------------

def paper(name="Paper", color="#efe7d6", rough=0.72, age=0.3, ink_lines=False, line_color="#3a4a7a"):
    key = f"paper:{name}:{color}:{rough}:{age}:{ink_lines}:{line_color}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    fib = n.new("ShaderNodeTexNoise", Scale=700.0, Detail=6, Roughness=0.7)
    n.link(mp, None, fib, "Vector")
    blot = n.new("ShaderNodeTexNoise", Scale=12.0, Detail=8, Roughness=0.6)
    n.link(mp, None, blot, "Vector")
    blot_r = n.ramp((blot, "Fac"), [(0.4, (0, 0, 0)), (0.85, (1, 1, 1))])
    col = n.mix("RGBA", n.math("MULTIPLY", (blot_r, "Color"), age * 0.6), srgb(color), srgb("#d8c08c"),
                blend="MULTIPLY")
    if ink_lines:
        # handwriting impression: wavy horizontal strokes
        wav = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="Y", Scale=110.0,
                    Distortion=18.0, Detail=3.0)
        n.link(mp, None, wav, "Vector")
        wr = n.ramp((wav, "Fac"), [(0.0, (1, 1, 1)), (0.06, (0, 0, 0)), (0.94, (0, 0, 0)), (1.0, (1, 1, 1))])
        brk = n.new("ShaderNodeTexNoise", Scale=180.0, Detail=2)
        n.link(mp, None, brk, "Vector")
        mask = n.math("MULTIPLY", (wr, "Color"), n.math("GREATER_THAN", (brk, "Fac"), 0.47))
        col = n.mix("RGBA", n.math("MULTIPLY", mask, 0.85), col, srgb(line_color))
    bsdf = _principled(n, Roughness=rough)
    n.link(col, None, bsdf, "Base Color")
    bsdf.inputs["Subsurface Weight"].default_value = 0.08
    bsdf.inputs["Subsurface Radius"].default_value = (0.002, 0.0015, 0.001)
    normal = _bump_chain(n, [((fib, "Fac"), 0.12, 0.0002), ((blot, "Fac"), 0.03, 0.002)])
    n.link(normal, None, bsdf, "Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


def fabric(name="Fabric", color="#cbbfa8", threads_per_m=1400.0, rough=0.85, sheen=0.6, translucent=0.0,
           pattern="plain", pattern_color="#b8463c", pattern_scale=12.0):
    key = f"fabric:{name}:{color}:{threads_per_m}:{rough}:{sheen}:{translucent}:{pattern}:{pattern_color}:{pattern_scale}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    wx = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="X", Scale=threads_per_m / 6.28,
               Distortion=0.6, Detail=1.0)
    wy = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="Y", Scale=threads_per_m / 6.28,
               Distortion=0.6, Detail=1.0)
    n.link(mp, None, wx, "Vector")
    n.link(mp, None, wy, "Vector")
    weave = n.math("MULTIPLY", (wx, "Fac"), (wy, "Fac"))
    slub = n.new("ShaderNodeTexNoise", Scale=60.0, Detail=4)
    n.link(mp, None, slub, "Vector")
    base = srgb(color)
    col = n.mix("RGBA", 0.15, base, (slub, "Color"), blend="OVERLAY")
    if pattern == "gingham":
        gx = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="X", Scale=pattern_scale, _wave_profile="SIN")
        gy = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="Y", Scale=pattern_scale, _wave_profile="SIN")
        n.link(mp, None, gx, "Vector")
        n.link(mp, None, gy, "Vector")
        sx = n.math("GREATER_THAN", (gx, "Fac"), 0.5)
        sy = n.math("GREATER_THAN", (gy, "Fac"), 0.5)
        both = n.math("ADD", sx, sy)
        fac = n.math("MULTIPLY", both, 0.5)
        col = n.mix("RGBA", fac, col, srgb(pattern_color))
    elif pattern == "stripe":
        gx = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="X", Scale=pattern_scale, _wave_profile="SIN")
        n.link(mp, None, gx, "Vector")
        col = n.mix("RGBA", n.math("GREATER_THAN", (gx, "Fac"), 0.75), col, srgb(pattern_color))
    col2 = n.mix("RGBA", n.math("MULTIPLY", weave, 0.25), col, (0.0, 0.0, 0.0, 1.0), blend="MULTIPLY")
    bsdf = _principled(n, Roughness=rough)
    n.link(col2, None, bsdf, "Base Color")
    bsdf.inputs["Sheen Weight"].default_value = sheen
    bsdf.inputs["Sheen Roughness"].default_value = 0.4
    normal = _bump_chain(n, [(weave, 0.35, 0.0004), ((slub, "Fac"), 0.05, 0.001)])
    n.link(normal, None, bsdf, "Normal")
    shader = bsdf
    if translucent > 0:
        tr = n.new("ShaderNodeBsdfTranslucent")
        n.link(col2, None, tr, "Color")
        mx = n.new("ShaderNodeMixShader", Fac=translucent)
        n.link(bsdf, None, mx, 1)
        n.link(tr, None, mx, 2)
        shader = mx
    _output(n, shader)
    _cache[key] = mat
    return mat


def leather(name="Leather", color="#5a3a26", rough=0.5, wear=0.3):
    key = f"leather:{name}:{color}:{rough}:{wear}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    mp = _coords(n)
    vor = n.new("ShaderNodeTexVoronoi", Scale=400.0)
    n.link(mp, None, vor, "Vector")
    big = n.new("ShaderNodeTexNoise", Scale=6.0, Detail=8)
    n.link(mp, None, big, "Vector")
    wr = n.ramp((big, "Fac"), [(0.5, (0, 0, 0)), (0.8, (1, 1, 1))])
    col = n.mix("RGBA", n.math("MULTIPLY", (wr, "Color"), wear), srgb(color), srgb("#8a6a4c"))
    bsdf = _principled(n, Roughness=rough)
    n.link(col, None, bsdf, "Base Color")
    normal = _bump_chain(n, [((vor, "Distance"), 0.2, 0.0003)])
    n.link(normal, None, bsdf, "Normal")
    _output(n, bsdf)
    _cache[key] = mat
    return mat


# ---------------------------------------------------------------------------
# Light emitters
# ---------------------------------------------------------------------------

def emitter(name="Bulb", kelvin=2700.0, strength=40.0):
    key = f"emit:{name}:{kelvin}:{strength}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    bb = n.new("ShaderNodeBlackbody", Temperature=kelvin)
    em = n.new("ShaderNodeEmission", Strength=strength)
    n.link(bb, None, em, "Color")
    _output(n, em)
    _cache[key] = mat
    return mat


def frosted_bulb(name="FrostedBulb", kelvin=2700.0, strength=30.0):
    key = f"frost:{name}:{kelvin}:{strength}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    bb = n.new("ShaderNodeBlackbody", Temperature=kelvin)
    em = n.new("ShaderNodeEmission", Strength=strength)
    n.link(bb, None, em, "Color")
    gl = n.new("ShaderNodeBsdfPrincipled", Roughness=0.3)
    gl.inputs["Transmission Weight"].default_value = 1.0
    add = n.new("ShaderNodeAddShader")
    n.link(em, None, add, 0)
    n.link(gl, None, add, 1)
    _output(n, add)
    _cache[key] = mat
    return mat


def lampshade(name="Lampshade", color="#e6d6b8", glow=0.6):
    return fabric(name, color, threads_per_m=900.0, rough=0.95, sheen=0.3, translucent=glow)


def flame(name="Flame", strength=12.0):
    key = f"flame:{name}:{strength}"
    if key in _cache:
        return _cache[key]
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    geo = n.new("ShaderNodeNewGeometry")
    sep = n.new("ShaderNodeSeparateXYZ")
    tc = n.new("ShaderNodeTexCoord")
    n.link(tc, "Generated", sep, "Vector")
    grad = n.ramp((sep, "Z"), [(0.0, srgb("#3a5cff")), (0.18, srgb("#ff8a1f")), (0.55, srgb("#ffd27a")),
                               (1.0, srgb("#fff2d0"))])
    em = n.new("ShaderNodeEmission", Strength=strength)
    n.link(grad, "Color", em, "Color")
    lw = n.new("ShaderNodeLayerWeight", Blend=0.4)
    tr = n.new("ShaderNodeBsdfTransparent")
    mx = n.new("ShaderNodeMixShader")
    n.link((lw, "Facing"), None, mx, "Fac")
    n.link(em, None, mx, 1)
    n.link(tr, None, mx, 2)
    _output(n, mx)
    _cache[key] = mat
    return mat


def image_material(name, color_path, rough_path=None, height_path=None, bump_strength=0.4,
                   bump_distance=0.0004, alpha=True, coat=0.0, back_path=None):
    """Material driven by baked texture maps (used for the instant prints)."""
    mat = new_material(name)
    mat.blend_method = "HASHED" if hasattr(mat, "blend_method") else None
    n = Nodes(mat.node_tree)
    uv = n.new("ShaderNodeTexCoord")
    tex = n.new("ShaderNodeTexImage", _interpolation="Cubic")
    tex.image = bpy.data.images.load(color_path, check_existing=True)
    tex.image.colorspace_settings.name = "sRGB"
    tex.image.alpha_mode = "STRAIGHT"
    n.link(uv, "UV", tex, "Vector")
    bsdf = _principled(n)
    n.link(tex, "Color", bsdf, "Base Color")
    if alpha:
        n.link(tex, "Alpha", bsdf, "Alpha")
    if rough_path:
        rt = n.new("ShaderNodeTexImage", _interpolation="Cubic")
        rt.image = bpy.data.images.load(rough_path, check_existing=True)
        rt.image.colorspace_settings.name = "Non-Color"
        n.link(uv, "UV", rt, "Vector")
        n.link(rt, "Color", bsdf, "Roughness")
    if height_path:
        ht = n.new("ShaderNodeTexImage", _interpolation="Cubic")
        ht.image = bpy.data.images.load(height_path, check_existing=True)
        ht.image.colorspace_settings.name = "Non-Color"
        n.link(uv, "UV", ht, "Vector")
        b = n.new("ShaderNodeBump", Strength=bump_strength, Distance=bump_distance)
        n.link(ht, "Color", b, "Height")
        n.link(b, None, bsdf, "Normal")
    if coat > 0:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.03
    _output(n, bsdf)
    return mat
