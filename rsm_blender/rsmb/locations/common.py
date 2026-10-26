"""Shared building blocks for locations: rooms, windows, curtains, outdoor
backdrop and placing the instant prints."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

from .. import materials as M
from ..polaroid_obj import build_card, card_size, image_centre_local
from ..util import add_bevel, add_subsurf, box, link, mesh_object, set_smooth


@dataclass
class Ctx:
    job: dict
    spec: dict
    col: bpy.types.Collection
    rng: random.Random
    quality: dict
    work_dir: str
    lights_on: bool = False
    sun_window: dict | None = None  # filled by a location: dict(centre, normal, bottom, top) for aiming the sun

    @property
    def top_down(self) -> bool:
        """Any shot looks straight down (leaning prints would be seen edge-on, so they lie flat instead)."""
        shots = self.job.get("shots") or [{"move": self.spec["camera"]["move"]}]
        return any(s["move"] == "top_down" for s in shots)

    @property
    def scene_spec(self):
        return self.spec["scene"]


@dataclass
class Room:
    min: Vector
    max: Vector
    windows: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Walls with openings
# ---------------------------------------------------------------------------

def wall(name, col, mat, axis: str, plane: float, span_min, span_max, z0, z1, thickness=0.12, openings=()):
    """Axis-aligned wall. axis='y' → wall lies in the XZ plane at y=plane; 'x' → YZ plane at x=plane.
    openings: list of (centre_along_span, width, bottom_z, top_z). Builds the wall from boxes around holes."""
    pieces = []
    # sort openings along the span
    ops = sorted(openings, key=lambda o: o[0])
    cursor = span_min
    for c, w, b, t in ops:
        lo, hi = c - w / 2, c + w / 2
        if lo > cursor:
            pieces.append((cursor, lo, z0, z1))
        pieces.append((lo, hi, z0, b))     # below
        pieces.append((lo, hi, t, z1))     # above
        cursor = hi
    if cursor < span_max:
        pieces.append((cursor, span_max, z0, z1))
    objs = []
    for i, (a, b_, lo, hi) in enumerate(pieces):
        if b_ - a < 1e-4 or hi - lo < 1e-4:
            continue
        mid = (a + b_) / 2
        if axis == "y":
            o = box(f"{name}_{i}", b_ - a, thickness, hi - lo, (mid, plane, (lo + hi) / 2), mat, col)
        else:
            o = box(f"{name}_{i}", thickness, b_ - a, hi - lo, (plane, mid, (lo + hi) / 2), mat, col)
        objs.append(o)
    return objs


def window(name, col, axis: str, plane: float, centre: float, width: float, bottom: float, top: float,
           inward: int, frame_mat=None, panes=(2, 3), wall_thickness=0.12, sill=True):
    """Painted timber window with mullions, real glass panes and a sill.
    inward: +1/-1 direction (along the wall normal axis) pointing into the room."""
    frame_mat = frame_mat or M.wood(f"{name}_paint", "painted_white", varnish=0.3, wear=0.25, scale=2.0)
    glass_mat = M.glass(f"{name}_glass", "#f7fbfa", 0.0, 1.52, smudge=0.35)
    fw = 0.055   # frame width
    depth = 0.07
    h = top - bottom
    objs = []

    def place(sx_along, sy_depth, sz, along, z, depth_off=0.0):
        if axis == "y":
            return box(f"{name}_f", sx_along, sy_depth, sz, (along, plane + inward * depth_off, z), frame_mat, col,
                       bevel=0.004)
        return box(f"{name}_f", sy_depth, sx_along, sz, (plane + inward * depth_off, along, z), frame_mat, col,
                   bevel=0.004)

    # outer frame
    objs.append(place(width, depth, fw, centre, bottom + fw / 2))
    objs.append(place(width, depth, fw, centre, top - fw / 2))
    objs.append(place(fw, depth, h, centre - width / 2 + fw / 2, (bottom + top) / 2))
    objs.append(place(fw, depth, h, centre + width / 2 - fw / 2, (bottom + top) / 2))
    nx, nz = panes
    mw = 0.028
    for i in range(1, nx):
        a = centre - width / 2 + width * i / nx
        objs.append(place(mw, depth * 0.8, h - 2 * fw, a, (bottom + top) / 2))
    for j in range(1, nz):
        z = bottom + h * j / nz
        objs.append(place(width - 2 * fw, depth * 0.8, mw, centre, z))
    # glass
    if axis == "y":
        g = box(f"{name}_glass", width - 2 * fw, 0.004, h - 2 * fw, (centre, plane, (bottom + top) / 2), glass_mat, col)
    else:
        g = box(f"{name}_glass", 0.004, width - 2 * fw, h - 2 * fw, (plane, centre, (bottom + top) / 2), glass_mat, col)
    g.visible_shadow = False  # let sunlight through without needing caustics
    objs.append(g)
    if sill:
        sd = wall_thickness / 2 + 0.06
        if axis == "y":
            objs.append(box(f"{name}_sill", width + 0.12, sd * 2, 0.035, (centre, plane + inward * sd * 0.6, bottom - 0.017),
                            frame_mat, col, bevel=0.005))
        else:
            objs.append(box(f"{name}_sill", sd * 2, width + 0.12, 0.035, (plane + inward * sd * 0.6, centre, bottom - 0.017),
                            frame_mat, col, bevel=0.005))
    # light portal so the interior converges quickly
    ld = bpy.data.lights.new(f"{name}_portal", "AREA")
    ld.shape = "RECTANGLE"
    ld.size = width
    ld.size_y = h
    ld.cycles.is_portal = True
    portal = bpy.data.objects.new(f"{name}_portal", ld)
    link(portal, col)
    if axis == "y":
        portal.location = (centre, plane + inward * 0.01, (bottom + top) / 2)
        portal.rotation_euler = (math.radians(90) * (-inward), 0, 0) if inward > 0 else (math.radians(90), 0, 0)
        # area lights emit along -Z: aim into the room
        portal.rotation_euler = Vector((0, inward, 0)).to_track_quat("-Z", "Z").to_euler()
    else:
        portal.location = (plane + inward * 0.01, centre, (bottom + top) / 2)
        portal.rotation_euler = Vector((inward, 0, 0)).to_track_quat("-Z", "Z").to_euler()
    return objs


def curtain(name, col, axis, plane, centre, width, bottom, top, inward, color="#d9cdb4", sheer=0.55, folds=9,
            gather=0.6):
    """Hanging fabric with folds (displaced grid). gather <1 bunches it."""
    mat = M.fabric(f"{name}_linen", color, threads_per_m=1800, rough=0.9, sheen=0.5, translucent=sheer)
    nx, nz = 80, 40
    bm = bmesh.new()
    verts = []
    h = top - bottom
    for j in range(nz + 1):
        row = []
        for i in range(nx + 1):
            u, v = i / nx, j / nz
            along = centre + (u - 0.5) * width * gather
            amp = 0.035 * (1.0 + 0.6 * (1 - v))
            off = math.sin(u * folds * 2 * math.pi + 0.7 * math.sin(v * 3.1)) * amp
            z = bottom + v * h
            if axis == "y":
                row.append(bm.verts.new((along, plane + inward * (0.08 + off), z)))
            else:
                row.append(bm.verts.new((plane + inward * (0.08 + off), along, z)))
        verts.append(row)
    for j in range(nz):
        for i in range(nx):
            bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
    o = mesh_object(name, bm, col, smooth=True, mat=mat)
    set_smooth(o)
    sol = o.modifiers.new("Thick", "SOLIDIFY")
    sol.thickness = 0.002
    return o


def outdoor_backdrop(col, centre: Vector, facing: Vector, rng: random.Random, distance=8.0, season="summer",
                     trees: int = 14, hedge: bool = True):
    """Garden beyond a window: lawn, hedge and trees. Usually seen heavily defocused."""
    grass = bpy.data.materials.new("Lawn")
    grass.use_nodes = True
    b = grass.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.06, 0.12, 0.03, 1.0) if season != "winter" else (0.7, 0.72, 0.75, 1.0)
    b.inputs["Roughness"].default_value = 0.9
    gp = box("Lawn", 60, 60, 0.1, (centre.x, centre.y, -0.6), grass, col)
    leaf = bpy.data.materials.new("Foliage")
    leaf.use_nodes = True
    nt = leaf.node_tree
    lb = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 25.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.02, 0.06, 0.015, 1)
    ramp.color_ramp.elements[1].color = (0.18, 0.3, 0.06, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], lb.inputs["Base Color"])
    lb.inputs["Subsurface Weight"].default_value = 0.3
    lb.inputs["Roughness"].default_value = 0.6
    side = facing.cross(Vector((0, 0, 1))).normalized()
    for i in range(trees):
        d = distance + rng.uniform(0, 14)
        lat = rng.uniform(-12, 12)
        p = centre + facing * d + side * lat
        r = rng.uniform(1.4, 3.2)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=r, location=(p.x, p.y, r * 0.8 + rng.uniform(0, 2)))
        t = bpy.context.object
        t.name = f"Tree{i}"
        for c in t.users_collection:
            c.objects.unlink(t)
        col.objects.link(t)
        disp = t.modifiers.new("Leafy", "DISPLACE")
        tex = bpy.data.textures.new(f"TreeTex{i}", "CLOUDS")
        tex.noise_scale = 0.6
        disp.texture = tex
        disp.strength = r * 0.35
        t.data.materials.append(leaf)
        set_smooth(t)
    if not hedge:
        return gp
    # hedge
    hd = box("Hedge", 30, 1.2, 1.6, tuple(centre + facing * (distance * 0.55)) , leaf, col, bevel=0.3)
    hd.location.z = 0.2
    hd.rotation_euler = (0, 0, math.atan2(facing.y, facing.x) + math.pi / 2)
    return gp


# ---------------------------------------------------------------------------
# Instant prints
# ---------------------------------------------------------------------------

# every instant print placed in the set, so camera moves can travel between photos
PLACED_PRINTS: list[dict] = []


def register_print(obj, meta, centre: Vector, normal: Vector, hero: bool = False):
    PLACED_PRINTS.append(dict(name=obj.name, centre=centre.copy(), normal=normal.copy(),
                              height=float(meta["card_mm"][1]) / 1000.0, hero=hero,
                              image=(meta.get("files") or {}).get("color", "")))


_NOT_A_SURFACE = ("Haze", "DustMotes", "Steam", "Portal", "Fairy", "Cobweb", "String")


def surface_z(x: float, y: float, near_z: float, reach: float = 0.15) -> float | None:
    """Height of the highest solid surface under (x, y), searching down from near_z + reach.
    Lets loose objects rest on whatever is really there (a runner, a letter, another print)."""
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    origin = Vector((x, y, near_z + reach))
    down = Vector((0, 0, -1))
    travelled = 0.0
    limit = reach + 0.25
    for _ in range(12):
        hit, loc, _n, _i, obj, _m = scene.ray_cast(dg, origin, down, distance=limit - travelled)
        if not hit:
            return None
        if obj is not None and any(k in obj.name for k in _NOT_A_SURFACE):
            travelled += (origin.z - loc.z) + 1e-4
            origin = loc + down * 1e-4
            continue
        return loc.z
    return None


def _flat_footprint(meta, where: Vector, yaw: float, inset: float = 0.9):
    """Sample points (centre, corners, edge midpoints) of a print lying flat, centred on `where`."""
    w, h = card_size(meta)
    rot = Matrix.Rotation(yaw, 3, "Z")
    pts = []
    for fx, fy in ((0, 0), (-1, -1), (1, -1), (1, 1), (-1, 1), (0, -1), (0, 1), (-1, 0), (1, 0)):
        pts.append(where + rot @ Vector((fx * w / 2 * inset, fy * h / 2 * inset, 0)))
    return pts


def _support_plane(pts, zs, max_tilt_deg: float = 22.0):
    """Plane the print settles on: least-squares fit through the surface heights under it, lifted so no
    point is below it (it rests on the highest bumps), tilt capped to something believable.
    Returns ((x, y, z) at the footprint centre, unit normal)."""
    n_ = len(pts)
    sx = sum(p.x for p in pts) / n_
    sy = sum(p.y for p in pts) / n_
    sz = sum(zs) / n_
    sxx = sum((p.x - sx) ** 2 for p in pts)
    syy = sum((p.y - sy) ** 2 for p in pts)
    sxy = sum((p.x - sx) * (p.y - sy) for p in pts)
    sxz = sum((p.x - sx) * (z - sz) for p, z in zip(pts, zs))
    syz = sum((p.y - sy) * (z - sz) for p, z in zip(pts, zs))
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-12:
        b = c = 0.0
    else:
        b = (sxz * syy - syz * sxy) / det
        c = (syz * sxx - sxz * sxy) / det
    slope = math.hypot(b, c)
    cap = math.tan(math.radians(max_tilt_deg))
    if slope > cap:
        b, c = b * cap / slope, c * cap / slope
    # lift so every sampled point lies on or below the card
    a = sz + max(z - (sz + b * (p.x - sx) + c * (p.y - sy)) for p, z in zip(pts, zs))
    normal = Vector((-b, -c, 1.0)).normalized()
    return (sx, sy, a), normal


def rest_z(x: float, y: float, near: float, reach: float = 0.06) -> float:
    """Height a small prop should stand at: whatever is really under (x, y) (desk mat, runner, table)."""
    bpy.context.view_layer.update()
    z = surface_z(x, y, near, reach)
    return near if z is None else z


def footprint_heights(meta, where: Vector, yaw: float) -> list[float]:
    bpy.context.view_layer.update()
    out = []
    for p in _flat_footprint(meta, where, yaw):
        z = surface_z(p.x, p.y, where.z)
        out.append(where.z if z is None else z)
    return out


def place_card(meta, name, col, where: Vector, yaw: float, mode: str, lean_deg: float = 18.0, lift=0.0005,
               settle: bool = True, register: bool = True):
    """Place a print. mode: leaning | flat. yaw rotates around Z (0 = facing -Y).
    Flat prints settle onto whatever is under them (table, runner, letters, other prints).
    Returns (obj, picture_centre_world, normal_world)."""
    where = where.copy()
    support = None
    if mode == "flat" and settle:
        pts = _flat_footprint(meta, where, yaw)
        zs = footprint_heights(meta, where, yaw)
        support = _support_plane(pts, zs)
        where.z = max(zs)
    obj = build_card(meta, name, col, stand_deg=lean_deg if mode == "leaning" else None)
    if mode == "leaning" and meta.get("frame"):
        # a frame stands on the back edge of its moulding (and its strut): the front edge is in the air
        lift += float(meta["thickness_mm"]) / 1000.0 * math.sin(math.radians(lean_deg))
    if mode == "flat" and support is not None and support[1].z < 0.9999:
        # rest on the highest points underneath, tipping like a real print would
        (cx, cy, cz), n = support
        w, h = card_size(meta)
        base = Euler((math.radians(-90), 0, yaw), "XYZ").to_matrix()
        tilt = Vector((0, 0, 1)).rotation_difference(n).to_matrix()
        rot = tilt @ base
        thick = lift + float(meta.get("thickness_mm", 1.0)) / 1000.0
        centre_world = Vector((cx, cy, cz)) + n * thick
        obj.matrix_world = Matrix.Translation(centre_world - rot @ Vector((0, 0, h / 2))) @ rot.to_4x4()
    elif mode == "flat":
        obj.rotation_euler = Euler((math.radians(-90), 0, yaw), "XYZ")
        obj.location = where + Vector((0, 0, lift + float(meta.get("thickness_mm", 1.0)) / 1000.0))
        # card origin is the bottom edge; when flat it extends along +Y (rotated); centre it on `where`
        w, h = card_size(meta)
        shift = Matrix.Rotation(yaw, 3, "Z") @ Vector((0, -h / 2, 0))
        obj.location += shift
    else:
        obj.rotation_euler = Euler((math.radians(-lean_deg), 0, yaw), "XYZ")
        obj.location = where + Vector((0, 0, lift))
    bpy.context.view_layer.update()
    centre = obj.matrix_world @ image_centre_local(meta)
    normal = (obj.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized()
    if register:  # hidden prints (in a box, under others) are left out so multi-photo moves don't visit them
        register_print(obj, meta, centre, normal, hero=name == "HeroPrint")
    return obj, centre, normal


def scatter_prints(metas, col, centre: Vector, radius: float, rng: random.Random, base_z: float, prefix="Extra",
                   avoid: Vector | None = None, avoid_r: float = 0.0, stack=False):
    """Lay other prints around (or under) the hero, the way they'd really fall: each one rests flat on
    what's below it. Loose prints prefer spots where they can lie flat instead of propping on an edge."""
    objs = []
    z = base_z
    for i, meta in enumerate(metas):
        best = None
        for attempt in range(30):
            if stack:
                p = centre + Vector((rng.uniform(-radius, radius), rng.uniform(-radius, radius), 0))
            else:
                a = rng.uniform(0, 2 * math.pi)
                d = rng.uniform(radius * 0.35, radius)
                p = centre + Vector((math.cos(a) * d, math.sin(a) * d, 0))
            if avoid is not None and (p - avoid).length <= avoid_r:
                continue
            p.z = z if stack else base_z
            yaw = rng.uniform(-0.6, 0.6) if stack else rng.uniform(-math.pi, math.pi)
            if stack:
                best = (p, yaw)
                break
            zs = footprint_heights(meta, p, yaw)
            spread = max(zs) - min(zs)
            if best is None or spread < best[2]:
                best = (p, yaw, spread)
            if spread < 0.0015:  # lies flat here: on the table, the runner, or squarely on another print
                break
        if best is None:
            continue
        o, _, _ = place_card(meta, f"{prefix}{i}", col, best[0], best[1], "flat", settle=not stack)
        objs.append(o)
        if stack:
            z += float(meta.get("thickness_mm", 1.0)) / 1000.0 + 0.0003
    return objs, z


def aim_sun_through(window_info: dict, subject: Vector, target_elev_deg: float) -> tuple[float, float]:
    """Choose a sun direction that passes through a window and lands on the subject, as close to the
    requested elevation as the window allows. Returns (azimuth_deg_from, elevation_deg)."""
    c = Vector(window_info["centre"])
    bottom, top = window_info["bottom"], window_info["top"]
    # aim through the middle of a pane, never through a glazing bar
    along = window_info.get("along")
    panes = int(window_info.get("panes", 2))
    if along is not None and panes % 2 == 0:
        c = c + Vector(along).normalized() * (window_info.get("width", 1.0) / (2 * panes))
    elif panes % 2 == 1:
        pass  # odd pane count: the centre is already mid-pane
    # avoid horizontal bars too: aim at the middle of a pane row
    horiz = Vector((c.x - subject.x, c.y - subject.y, 0.0))
    dist = horiz.length
    want_z = subject.z + math.tan(math.radians(target_elev_deg)) * dist
    rows = int(window_info.get("rows", 1))
    if rows > 1:
        row_h = (top - bottom) / rows
        centres = [bottom + row_h * (i + 0.5) for i in range(rows)]
        z = min(centres, key=lambda zc: abs(zc - want_z))
        # stay inside that row but as close to the wanted height as possible
        z = max(z - row_h * 0.3, min(z + row_h * 0.3, want_z))
    else:
        z = max(bottom + 0.08, min(top - 0.08, want_z))
    p = Vector((c.x, c.y, z))
    d = (p - subject).normalized()
    az = math.degrees(math.atan2(d.x, d.y)) % 360
    el = math.degrees(math.asin(max(-1, min(1, d.z))))
    return az, el


def animate_flicker(light_obj, base_energy: float, amount: float, fps: float, frame_start: int, frame_end: int,
                    seed: int = 1, speed: float = 1.0):
    """Keyframe a light's energy with layered noise: candles, fires, old bulbs."""
    from ..camera_rig import Noise1D
    n1, n2, n3 = Noise1D(seed), Noise1D(seed + 1), Noise1D(seed + 2)
    ld = light_obj.data
    for f in range(frame_start, frame_end + 1):
        t = (f - frame_start) / fps * speed
        v = 1.0 + amount * (0.55 * n1(t * 1.3) + 0.3 * n2(t * 4.7) + 0.15 * n3(t * 11.0))
        ld.energy = max(0.0, base_energy * v)
        ld.keyframe_insert("energy", frame=f)


def wallpaper(name="Wallpaper", base="#c9b99a", ink="#a8936e", stripe_scale=9.0):
    """Faded striped wallpaper with a small repeating motif."""
    from ..util import Nodes, new_material, srgb
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    n.link(tc, "Object", mp, "Vector")
    stripes = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="X", Scale=stripe_scale,
                    Distortion=0.0)
    n.link(mp, None, stripes, "Vector")
    st = n.ramp((stripes, "Fac"), [(0.0, (0, 0, 0)), (0.45, (0, 0, 0)), (0.5, (1, 1, 1)), (0.6, (0, 0, 0))])
    motif = n.new("ShaderNodeTexVoronoi", Scale=34.0, _feature="F1")
    n.link(mp, None, motif, "Vector")
    dots = n.ramp((motif, "Distance"), [(0.0, (1, 1, 1)), (0.18, (0, 0, 0))])
    pat = n.math("MAXIMUM", (st, "Color"), n.math("MULTIPLY", (dots, "Color"), 0.8))
    age = n.new("ShaderNodeTexNoise", Scale=3.0, Detail=6.0)
    n.link(mp, None, age, "Vector")
    col = n.mix("RGBA", pat, srgb(base), srgb(ink))
    col2 = n.mix("RGBA", 0.12, col, (age, "Color"), blend="OVERLAY")
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.75)
    n.link(col2, None, b, "Base Color")
    fine = n.new("ShaderNodeTexNoise", Scale=500.0, Detail=3)
    n.link(mp, None, fine, "Vector")
    bump = n.new("ShaderNodeBump", Strength=0.08, Distance=0.0003)
    n.link(fine, "Fac", bump, "Height")
    n.link(bump, None, b, "Normal")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    return mat


# ---------------------------------------------------------------------------
# Location options
# ---------------------------------------------------------------------------

def opt(ctx: "Ctx", key: str, default=None):
    return ctx.job.get("location_options", {}).get(key, default)


def switched_on(ctx: "Ctx", key: str, default="auto") -> bool:
    """'auto' follows the time of day (lamps come on in the evening), 'on'/'off' force it."""
    v = opt(ctx, key, default)
    if v in (True, "on"):
        return True
    if v in (False, "off"):
        return False
    return ctx.lights_on


# ---------------------------------------------------------------------------
# Small details used by several sets
# ---------------------------------------------------------------------------

def steam(col, base: Vector, height=0.22, radius=0.03, name="Steam"):
    """A wisp of rising steam: a volume whose density is animated noise drifting upwards."""
    from ..util import Nodes, new_material
    bpy.ops.mesh.primitive_cylinder_add(radius=radius * 2.2, depth=height, location=(base.x, base.y, base.z + height / 2))
    o = bpy.context.object
    o.name = name
    for c in o.users_collection:
        c.objects.unlink(o)
    col.objects.link(o)
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    # rising: subtract time from Z so the pattern drifts up
    val = n.new("ShaderNodeValue")
    drv = val.outputs[0].driver_add("default_value")
    drv.driver.expression = "frame / 24.0 * 0.06"
    sep = n.new("ShaderNodeSeparateXYZ")
    n.link(tc, "Object", sep, "Vector")
    z = n.math("SUBTRACT", (sep, "Z"), val)
    comb = n.new("ShaderNodeCombineXYZ")
    n.link(sep, "X", comb, "X")
    n.link(sep, "Y", comb, "Y")
    n.link(z, None, comb, "Z")
    noise = n.new("ShaderNodeTexNoise", Scale=22.0, Detail=6.0, Roughness=0.6, Distortion=1.2, _noise_dimensions="4D")
    n.link(comb, None, noise, "Vector")
    n.link(n.math("MULTIPLY", val, 8.0), None, noise, "W")
    wisps = n.ramp((noise, "Fac"), [(0.52, (0, 0, 0)), (0.7, (1, 1, 1))])
    # fade towards the edges of the cylinder and towards the top
    grad = n.new("ShaderNodeTexGradient", _gradient_type="SPHERICAL")
    gmap = n.new("ShaderNodeMapping", Scale=(1.0 / (radius * 2.2), 1.0 / (radius * 2.2), 1.0 / (height * 0.6)))
    n.link(tc, "Object", gmap, "Vector")
    n.link(gmap, None, grad, "Vector")
    dens = n.math("MULTIPLY", n.math("MULTIPLY", (wisps, "Color"), (grad, "Fac")), 3.0)
    vol = n.new("ShaderNodeVolumePrincipled", Anisotropy=0.4)
    vol.inputs["Color"].default_value = (0.95, 0.95, 0.95, 1)
    n.link(dens, None, vol, "Density")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(vol, None, out, "Volume")
    o.data.materials.append(mat)
    o.visible_shadow = False
    return o


def crumbs(col, centre: Vector, radius: float, count: int, rng, color="#c08a4a", size=(0.0008, 0.003), name="Crumb"):
    """Scattered irregular bits (bread crumbs, sugar grains, eraser rubbings)."""
    from ..util import srgb
    mat = bpy.data.materials.get(f"{name}Mat")
    if mat is None:
        mat = bpy.data.materials.new(f"{name}Mat")
        mat.use_nodes = True
        b = mat.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = srgb(color)
        b.inputs["Roughness"].default_value = 0.8
        b.inputs["Subsurface Weight"].default_value = 0.2
    bm = bmesh.new()
    for _ in range(count):
        a = rng.uniform(0, 2 * math.pi)
        d = radius * math.sqrt(rng.random())
        s = rng.uniform(*size)
        ret = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=s)
        for v in ret["verts"]:
            v.co.x *= rng.uniform(0.6, 1.4)
            v.co.z *= rng.uniform(0.4, 0.9)
            v.co += Vector((centre.x + math.cos(a) * d, centre.y + math.sin(a) * d, centre.z + s * 0.5))
    return mesh_object(name, bm, col, mat=mat)


def drink_ring(col, centre: Vector, radius: float, color="#5a3418", name="Ring", strength=0.6):
    """A dried coffee/tea ring on a table: a very thin, translucent ring decal."""
    from ..util import Nodes, new_material, srgb
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    grad = n.new("ShaderNodeTexGradient", _gradient_type="SPHERICAL")
    n.link(tc, "Object", grad, "Vector")
    wob = n.new("ShaderNodeTexNoise", Scale=6.0, Detail=4.0)
    n.link(tc, "Object", wob, "Vector")
    g2 = n.math("ADD", (grad, "Fac"), n.math("MULTIPLY", n.math("SUBTRACT", (wob, "Fac"), 0.5), 0.12))
    ring = n.ramp(g2, [(0.0, (0, 0, 0)), (0.06, (1, 1, 1)), (0.11, (0.15, 0.15, 0.15)), (0.9, (0.08, 0.08, 0.08)),
                       (1.0, (0, 0, 0))])
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.35)
    b.inputs["Base Color"].default_value = srgb(color)
    n.link(n.math("MULTIPLY", (ring, "Color"), strength), None, b, "Alpha")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    bpy.ops.mesh.primitive_circle_add(vertices=64, radius=radius, fill_type="NGON",
                                      location=(centre.x, centre.y, centre.z + 0.0002))
    o = bpy.context.object
    o.name = name
    for c in o.users_collection:
        c.objects.unlink(o)
    col.objects.link(o)
    o.data.materials.append(mat)
    o.visible_shadow = False
    return o


def cobweb_strands(col, anchors_pairs, rng, name="Cobweb"):
    """Sagging silk threads between pairs of points; they glint when backlit."""
    mat = bpy.data.materials.get("CobwebSilk")
    if mat is None:
        mat = bpy.data.materials.new("CobwebSilk")
        mat.use_nodes = True
        b = mat.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = (0.85, 0.85, 0.85, 1)
        b.inputs["Roughness"].default_value = 0.25
        b.inputs["Transmission Weight"].default_value = 0.6
        b.inputs["Alpha"].default_value = 0.7
    objs = []
    for i, (a, b2) in enumerate(anchors_pairs):
        curve = bpy.data.curves.new(f"{name}{i}", "CURVE")
        curve.dimensions = "3D"
        sp = curve.splines.new("POLY")
        steps = 16
        sp.points.add(steps)
        sag = (b2 - a).length * rng.uniform(0.05, 0.15)
        for k in range(steps + 1):
            t = k / steps
            p = a.lerp(b2, t) - Vector((0, 0, sag * 4 * t * (1 - t)))
            sp.points[k].co = (p.x, p.y, p.z, 1)
        curve.bevel_depth = 0.00012
        o = bpy.data.objects.new(f"{name}{i}", curve)
        link(o, col)
        o.data.materials.append(mat)
        o.visible_shadow = False
        objs.append(o)
    return objs


def fairy_lights(col, points: list, count: int, rng, kelvin=2400.0, strength=30.0, name="FairyLights", sag=0.03):
    """A string of tiny warm bulbs following a polyline (with sag between points)."""
    from .. import materials as M
    from ..util import cylinder_bm
    wire = bpy.data.curves.new(f"{name}Wire", "CURVE")
    wire.dimensions = "3D"
    sp = wire.splines.new("POLY")
    pts = []
    for i in range(len(points) - 1):
        a, b2 = points[i], points[i + 1]
        for k in range(12):
            t = k / 12
            pts.append(a.lerp(b2, t) - Vector((0, 0, sag * 4 * t * (1 - t))))
    pts.append(points[-1])
    sp.points.add(len(pts) - 1)
    for k, p in enumerate(pts):
        sp.points[k].co = (p.x, p.y, p.z, 1)
    wire.bevel_depth = 0.0006
    wo = bpy.data.objects.new(f"{name}Wire", wire)
    link(wo, col)
    wo.data.materials.append(M.plastic("FairyWire", "#1d2a1a", 0.5))
    bulb_mat = M.emitter(f"{name}Bulb", kelvin, strength)
    bm = bmesh.new()
    total = len(pts) - 1
    for i in range(count):
        p = pts[int(i / count * total)]
        ret = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.0032)
        for v in ret["verts"]:
            v.co.z *= 1.5
            v.co += p - Vector((0, 0, 0.004))
    return mesh_object(f"{name}Bulbs", bm, col, mat=bulb_mat)


def hang_card(meta, name, col, top: Vector, yaw: float = 0.0, roll: float = 0.0, sway: float = 0.0):
    """Hang a print by the middle of its top edge (pegged on a line, pinned to a wall). It faces -Y
    rotated by yaw; roll turns it in its own plane, sway tips the bottom towards/away from the wall."""
    obj = build_card(meta, name, col)
    w, h = card_size(meta)
    rot = Matrix.Rotation(yaw, 3, "Z") @ Matrix.Rotation(roll, 3, "Y") @ Matrix.Rotation(sway, 3, "X")
    obj.matrix_world = Matrix.Translation(top - rot @ Vector((0, 0, h))) @ rot.to_4x4()
    bpy.context.view_layer.update()
    centre = obj.matrix_world @ image_centre_local(meta)
    normal = (obj.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized()
    register_print(obj, meta, centre, normal, hero=name == "HeroPrint")
    return obj, centre, normal


def clothes_peg(name, col, at: Vector, yaw: float = 0.0, roll: float = 0.0):
    """A wooden clothes peg clipped over a line: two prongs and a steel spring."""
    from ..util import cylinder
    root = bpy.data.objects.new(name, None)
    link(root, col)
    root.location = at
    root.rotation_euler = (0, roll, yaw)
    wood = M.wood("PegWood", "pine", varnish=0.0, wear=0.3, scale=6.0, grain_axis="Z")
    steel = M.metal("PegSpring", "#b9bcbf", 0.3, 0.3, 0.2)
    for k, dy in enumerate((-0.0035, 0.0035)):
        prong = box(f"{name}_prong{k}", 0.0095, 0.0045, 0.072, (0, dy, -0.012), wood, col, bevel=0.0012)
        prong.parent = root
    spring = cylinder(f"{name}_spring", 0.0045, 0.009, (-0.0045, 0, 0.0), steel, col, 16)
    spring.rotation_euler = (0, math.radians(90), 0)
    spring.parent = root
    return root


def sagging_line(name, col, a: Vector, b: Vector, sag: float, radius: float = 0.0012, mat=None, steps: int = 40):
    """A twine/wire line hanging between two points. Returns a function giving the point at 0..1."""
    def at(t):
        return a.lerp(b, t) - Vector((0, 0, sag * 4 * t * (1 - t)))
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(steps)
    for k in range(steps + 1):
        p = at(k / steps)
        sp.points[k].co = (p.x, p.y, p.z, 1)
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    o = bpy.data.objects.new(name, cu)
    link(o, col)
    o.data.materials.append(mat or M.fabric("Twine", "#9a7b55", threads_per_m=2500, rough=0.9, sheen=0.4))
    return at


def hand_font(ctx: "Ctx", prefer=("Caveat.ttf", "ShadowsIntoLight.ttf")):
    """One of the bundled handwriting fonts as a Blender font (None if they're missing)."""
    import os
    fdir = ctx.job["paths"].get("fonts") or os.path.join(os.path.dirname(__file__), "..", "..", "..", "rsm", "assets",
                                                          "fonts")
    for fname in prefer:
        fp = os.path.join(fdir, fname)
        if os.path.exists(fp):
            return bpy.data.fonts.load(fp, check_existing=True)
    return None


def text_obj(col, body, font, size, loc, rot, mat, name="Writing", align="CENTER"):
    """Handwriting as very thin extruded text (ink sits on the paper, catches a little light)."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if font:
        cu.font = font
    cu.size = size
    cu.align_x = align
    cu.extrude = 0.00005
    o = bpy.data.objects.new(name, cu)
    link(o, col)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    return o


def _group(name: str) -> str:
    return name.split("_")[0]


def make_room_for_frame(anchors):
    """A picture frame is much bigger and deeper than an instant print, and the sets dress props around a
    print's footprint. Move the frame off walls and big furniture it cuts into, and take away the small props
    it would go through (a real set dresser would move them)."""
    from mathutils.bvhtree import BVHTree
    hero = bpy.data.objects.get("HeroPrint")
    if hero is None or not hero.get("rsm_frame"):
        return
    skip = ("Haze", "Dust", "Mote", "Steam", "Portal", "Cobweb", "Fairy", "Glow", "Sky", "Mood")
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()

    def tree(o):
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        t = BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
        ev.to_mesh_clear()
        return t

    def bbox(objs):
        pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
        return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))

    family = [hero] + list(hero.children)
    others = [o for o in bpy.data.objects if o.type == "MESH" and o not in family and not o.hide_render
              and not any(w in o.name for w in skip)]
    groups: dict[str, list] = {}
    for o in others:
        groups.setdefault(_group(o.name), []).append(o)
    trees = {o.name: tree(o) for o in others}
    normal = (hero.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized()
    flat = abs(normal.z) > 0.7
    lo, _ = bbox(family)

    def hits():
        bpy.context.view_layer.update()
        ft = [tree(o) for o in family]
        out = set()
        for o in others:
            if o.name not in trees:
                continue
            if any(t.overlap(trees[o.name]) for t in ft):
                out.add(o)
        return out

    def big(o):
        mn, mx = bbox(groups[_group(o.name)])
        return (mx - mn).length > 0.32 or any(w in o.name for w in ("Wall", "Floor", "Table", "Desk", "Trunk", "Mirror",
                                                                     "Chimney", "Shelf", "Mantel", "Shoebox"))

    moved = Vector()
    for _ in range(40):
        h = [o for o in hits() if big(o)]
        # the surface it stands or lies on doesn't count
        h = [o for o in h if bbox([o])[1].z > lo.z + moved.z + 0.004]
        if not h or moved.length > 0.2:
            break
        if flat:
            mn, mx = bbox(h)
            away = hero.matrix_world.translation - (mn + mx) / 2
            away.z = 0
        else:
            away = Vector((normal.x, normal.y, 0))
        step = away.normalized() * 0.006 if away.length > 1e-6 else Vector((0, 0, 0.003))
        hero.location += step
        moved += step
    gone = set()
    for o in hits():
        if not big(o):
            gone.add(_group(o.name))
    for g in gone:
        for o in groups.get(g, []):
            for c in list(o.children):
                bpy.data.objects.remove(c, do_unlink=True)
            bpy.data.objects.remove(o, do_unlink=True)
    PLACED_PRINTS[:] = [p for p in PLACED_PRINTS if bpy.data.objects.get(p["name"]) is not None]
    if flat and gone:
        # whatever it was resting on may be gone: let it down onto what's left
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        mn, mx = bbox(family)
        gap = None
        for i in range(5):
            for j in range(5):
                x = mn.x + (mx.x - mn.x) * (0.1 + 0.8 * i / 4)
                y = mn.y + (mx.y - mn.y) * (0.1 + 0.8 * j / 4)
                ok, loc, _, _, _, _ = bpy.context.scene.ray_cast(dg, Vector((x, y, mn.z - 0.0005)), Vector((0, 0, -1)),
                                                                 distance=0.2)
                if ok:
                    d = mn.z - loc.z
                    gap = d if gap is None else min(gap, d)
        if gap is not None and gap > 0.001:
            step = Vector((0, 0, -(gap - 0.0003)))
            hero.location += step
            moved += step
    if moved.length > 0:
        anchors.subject = anchors.subject + moved
        for p in PLACED_PRINTS:
            if p["name"] == hero.name:
                p["centre"] = p["centre"] + moved
    if gone:
        log_removed = sorted(gone)
        print(f"rsm: made room for the frame (moved {moved.length * 1000:.0f} mm, cleared {', '.join(log_removed)})")


def frame_size_m(meta) -> tuple[float, float, float]:
    """Outer width, height and depth of a framed photo (metres)."""
    w, h = card_size(meta)
    return w, h, float(meta.get("thickness_mm", 20.0)) / 1000.0


def keep_off_wall(obj, wall_face_y: float, margin: float = 0.003) -> float:
    """Slide an object (and everything parented to it) out from a wall facing -Y so nothing goes into it.
    Returns how far it moved."""
    bpy.context.view_layer.update()
    ys = [(o.matrix_world @ Vector(c)).y for o in [obj] + list(obj.children_recursive) if o.type == "MESH"
          for c in o.bound_box]
    over = max(ys) - (wall_face_y - margin)
    if over > 0:
        obj.matrix_world = Matrix.Translation(Vector((0, -over, 0))) @ obj.matrix_world
        bpy.context.view_layer.update()
        for p in PLACED_PRINTS:
            if p["name"] == obj.name:
                p["centre"] = p["centre"] - Vector((0, over, 0))
    return max(0.0, over)


def hang_frame(meta, name, col, centre: Vector, wall_face_y: float, roll_deg: float = 0.0, tilt_deg: float = 1.5,
               register: bool = True):
    """Hang a framed photo on a wall that faces -Y (its surface at wall_face_y), centred on centre.x/centre.z.
    Hung on a wire, a frame leans out a touch at the top and is rarely perfectly level."""
    obj = build_card(meta, name, col)
    w, h, d = frame_size_m(meta)
    rot = Matrix.Rotation(math.radians(roll_deg), 3, "Y") @ Matrix.Rotation(math.radians(tilt_deg), 3, "X")
    # the bottom of the back rests on the wall; the top stands off it on the wire
    front_centre = Vector((centre.x, wall_face_y - d - 0.002, centre.z))
    obj.matrix_world = Matrix.Translation(front_centre - rot @ Vector((0, 0, h / 2))) @ rot.to_4x4()
    keep_off_wall(obj, wall_face_y, 0.0015)
    pic = obj.matrix_world @ image_centre_local(meta)
    normal = (obj.matrix_world.to_3x3() @ Vector((0, -1, 0))).normalized()
    if register:
        register_print(obj, meta, pic, normal, hero=name == "HeroPrint")
    return obj, pic, normal
