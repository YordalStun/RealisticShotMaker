"""Sky, sun, moon, interior haze and floating dust."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from .util import Nodes, link, new_material, srgb

# time of day → sun elevation (deg), colour temperature (K), sky strength, sun strength, exposure (stops)
TIME_PRESETS = {
    "morning": dict(elev=16.0, kelvin=4600.0, sky=0.3, sun=7.0, exposure=0.0),
    "midday": dict(elev=52.0, kelvin=5600.0, sky=0.5, sun=6.0, exposure=-0.6),
    "golden": dict(elev=6.5, kelvin=3300.0, sky=0.16, sun=6.5, exposure=0.3),
    "evening": dict(elev=-2.0, kelvin=3000.0, sky=0.06, sun=0.0, exposure=1.2),
    "night": dict(elev=-25.0, kelvin=4100.0, sky=0.0, sun=0.0, exposure=1.8),
}


def kelvin_rgb(k: float):
    """Approximate blackbody colour (linear RGB, normalised)."""
    t = k / 100.0
    if t <= 66:
        r = 255
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255
    c = [max(0, min(255, v)) / 255.0 for v in (r, g, b)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    m = max(lin)
    return tuple(v / m for v in lin)


def setup_sky(time_of_day: str, weather: str, sun_azimuth_deg: float, scene=None):
    """Nishita sky in the world + a matching sun lamp. Returns (sun_obj or None, info dict).

    sun_azimuth_deg: compass direction the sunlight comes FROM (0 = +Y, 90 = +X).
    """
    scene = scene or bpy.context.scene
    tp = dict(TIME_PRESETS.get(time_of_day, TIME_PRESETS["golden"]))
    world = bpy.data.worlds.new("RSM_World")
    scene.world = world
    world.use_nodes = True
    n = Nodes(world.node_tree)
    out = n.new("ShaderNodeOutputWorld")
    elev = tp["elev"]
    hazy = weather == "hazy"
    overcast = weather == "overcast"
    if time_of_day == "night":
        bg = n.new("ShaderNodeBackground", Strength=0.012)
        bg.inputs["Color"].default_value = srgb("#2a3a5c")
        n.link(bg, None, out, "Surface")
    else:
        sky = n.new("ShaderNodeTexSky", _sky_type="NISHITA")
        sky.sun_disc = False
        sky.sun_elevation = math.radians(max(elev, 0.5))
        sky.sun_rotation = math.radians(sun_azimuth_deg)
        sky.altitude = 50.0
        sky.air_density = 1.0
        sky.dust_density = 4.0 if hazy else (2.0 if overcast else 1.2)
        sky.ozone_density = 1.0
        strength = tp["sky"]
        bg = n.new("ShaderNodeBackground", Strength=strength)
        if overcast:
            # flatten the sky to a bright, even grey dome
            mix = n.mix("RGBA", 0.85, (sky, "Color"), srgb("#c9ccd0"))
            n.link(mix, None, bg, "Color")
            bg.inputs["Strength"].default_value = strength * 2.2
        else:
            n.link(sky, "Color", bg, "Color")
        n.link(bg, None, out, "Surface")

    sun = None
    if tp["sun"] > 0 and not overcast:
        ld = bpy.data.lights.new("Sun", "SUN")
        ld.energy = tp["sun"] * (0.55 if hazy else 1.0)
        ld.color = kelvin_rgb(tp["kelvin"] - (300 if hazy else 0))
        ld.angle = math.radians(2.5 if hazy else 0.6)
        try:
            ld.cycles.cast_shadow = True
        except AttributeError:
            pass
        sun = bpy.data.objects.new("Sun", ld)
        link(sun)
        az = math.radians(sun_azimuth_deg)
        el = math.radians(elev)
        # direction the light travels (from sky into the room)
        d_from = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
        sun.rotation_mode = "QUATERNION"
        sun.rotation_quaternion = (-d_from).to_track_quat("-Z", "Y")
    if time_of_day == "night":
        ld = bpy.data.lights.new("Moon", "SUN")
        ld.energy = 0.08
        ld.color = kelvin_rgb(7500)
        ld.angle = math.radians(0.6)
        moon = bpy.data.objects.new("Moon", ld)
        link(moon)
        az = math.radians(sun_azimuth_deg + 25)
        el = math.radians(28)
        d_from = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
        moon.rotation_mode = "QUATERNION"
        moon.rotation_quaternion = (-d_from).to_track_quat("-Z", "Y")
    return sun, tp


def sun_direction(sun_obj) -> Vector:
    """Direction the sunlight travels."""
    return (sun_obj.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()


def add_haze(bounds_min, bounds_max, density: float, anisotropy: float = 0.55, color="#fff6ea", col=None):
    """Volumetric haze filling the room so sun shafts become visible."""
    if density <= 0:
        return None
    size = Vector(bounds_max) - Vector(bounds_min)
    centre = (Vector(bounds_max) + Vector(bounds_min)) / 2
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    obj = bpy.context.object
    obj.name = "Haze"
    obj.scale = size
    if col is not None:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        col.objects.link(obj)
    mat = new_material("Haze")
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise", Scale=1.2, Detail=4.0)
    n.link(tc, "Object", noise, "Vector")
    dens = n.math("MULTIPLY", n.math("ADD", (noise, "Fac"), 0.4), density)
    vol = n.new("ShaderNodeVolumePrincipled", Anisotropy=anisotropy)
    vol.inputs["Color"].default_value = srgb(color)
    n.link(dens, None, vol, "Density")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(vol, None, out, "Volume")
    obj.data.materials.append(mat)
    obj.visible_shadow = False
    try:
        obj.visible_diffuse = True
    except AttributeError:
        pass
    return obj


def add_dust_motes(bounds_min, bounds_max, count: int, seed: int = 1, col=None, drift: float = 1.0):
    """Floating dust specks made with Geometry Nodes. They drift slowly with scene time and
    are only visible where light hits them, exactly like real dust."""
    if count <= 0:
        return None
    mn, mx = Vector(bounds_min), Vector(bounds_max)
    size = mx - mn
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(mn + mx) / 2)
    obj = bpy.context.object
    obj.name = "DustMotes"
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if col is not None:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        col.objects.link(obj)
    mod = obj.modifiers.new("Dust", "NODES")
    tree = bpy.data.node_groups.new("RSM_Dust", "GeometryNodeTree")
    mod.node_group = tree
    try:
        tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    except AttributeError:
        tree.inputs.new("NodeSocketGeometry", "Geometry")
        tree.outputs.new("NodeSocketGeometry", "Geometry")
    N = tree.nodes
    L = tree.links
    gin = N.new("NodeGroupInput")
    gout = N.new("NodeGroupOutput")
    # distribute in the volume of the box: mesh-to-volume -> distribute points
    m2v = N.new("GeometryNodeMeshToVolume")
    m2v.inputs["Density"].default_value = 1.0
    try:
        m2v.resolution_mode = "VOXEL_SIZE"
        m2v.inputs["Voxel Size"].default_value = max(size) / 40
    except (KeyError, AttributeError, TypeError):
        pass
    dist = N.new("GeometryNodeDistributePointsInVolume")
    dist.mode = "DENSITY_RANDOM"
    vol = max(1e-6, size.x * size.y * size.z)
    dist.inputs["Density"].default_value = count / vol
    dist.inputs["Seed"].default_value = seed
    L.new(gin.outputs[0], m2v.inputs["Mesh"])
    L.new(m2v.outputs[0], dist.inputs["Volume"])
    # animated drift: offset = noise(position * s + time) - 0.5, plus slow settling
    time = N.new("GeometryNodeInputSceneTime")
    pos = N.new("GeometryNodeInputPosition")
    scale_t = N.new("ShaderNodeMath")
    scale_t.operation = "MULTIPLY"
    scale_t.inputs[1].default_value = 0.035 * drift
    L.new(time.outputs["Seconds"], scale_t.inputs[0])
    comb = N.new("ShaderNodeCombineXYZ")
    L.new(scale_t.outputs[0], comb.inputs["Z"])
    addv = N.new("ShaderNodeVectorMath")
    addv.operation = "ADD"
    sc = N.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    sc.inputs["Scale"].default_value = 3.0
    L.new(pos.outputs[0], sc.inputs[0])
    L.new(sc.outputs[0], addv.inputs[0])
    L.new(comb.outputs[0], addv.inputs[1])
    noise = N.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 2.0
    L.new(addv.outputs[0], noise.inputs["Vector"])
    centre = N.new("ShaderNodeVectorMath")
    centre.operation = "SUBTRACT"
    centre.inputs[1].default_value = (0.5, 0.5, 0.5)
    L.new(noise.outputs["Color"], centre.inputs[0])
    amp = N.new("ShaderNodeVectorMath")
    amp.operation = "SCALE"
    amp.inputs["Scale"].default_value = 0.12 * drift
    L.new(centre.outputs[0], amp.inputs[0])
    # gentle sinking with time
    sink = N.new("ShaderNodeMath")
    sink.operation = "MULTIPLY"
    sink.inputs[1].default_value = -0.0025 * drift
    L.new(time.outputs["Seconds"], sink.inputs[0])
    sinkv = N.new("ShaderNodeCombineXYZ")
    L.new(sink.outputs[0], sinkv.inputs["Z"])
    tot = N.new("ShaderNodeVectorMath")
    tot.operation = "ADD"
    L.new(amp.outputs[0], tot.inputs[0])
    L.new(sinkv.outputs[0], tot.inputs[1])
    setp = N.new("GeometryNodeSetPosition")
    L.new(dist.outputs["Points"], setp.inputs["Geometry"])
    L.new(tot.outputs[0], setp.inputs["Offset"])
    # instance tiny irregular specks
    ico = N.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Radius"].default_value = 1.0
    ico.inputs["Subdivisions"].default_value = 1
    rnd_scale = N.new("FunctionNodeRandomValue")
    rnd_scale.data_type = "FLOAT"
    rnd_scale.inputs["Min"].default_value = 0.00012
    rnd_scale.inputs["Max"].default_value = 0.0005
    rnd_scale.inputs["Seed"].default_value = seed + 3
    rnd_rot = N.new("FunctionNodeRandomValue")
    rnd_rot.data_type = "FLOAT_VECTOR"
    rnd_rot.inputs["Max"].default_value = (6.28, 6.28, 6.28)
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(setp.outputs[0], inst.inputs["Points"])
    L.new(ico.outputs["Mesh"], inst.inputs["Instance"])
    L.new(rnd_scale.outputs[1], inst.inputs["Scale"])
    L.new(rnd_rot.outputs[0], inst.inputs["Rotation"])
    setm = N.new("GeometryNodeSetMaterial")
    mat = new_material("DustSpeck")
    mn_ = Nodes(mat.node_tree)
    b = mn_.new("ShaderNodeBsdfPrincipled", Roughness=0.9)
    b.inputs["Base Color"].default_value = (0.8, 0.78, 0.74, 1.0)
    b.inputs["Subsurface Weight"].default_value = 0.0
    tr = mn_.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (0.9, 0.88, 0.84, 1.0)
    mx = mn_.new("ShaderNodeMixShader", Fac=0.5)
    mn_.link(b, None, mx, 1)
    mn_.link(tr, None, mx, 2)
    o = mn_.new("ShaderNodeOutputMaterial")
    mn_.link(mx, None, o, "Surface")
    setm.inputs["Material"].default_value = mat
    L.new(inst.outputs[0], setm.inputs["Geometry"])
    L.new(setm.outputs[0], gout.inputs[0])
    obj.visible_shadow = False
    return obj
