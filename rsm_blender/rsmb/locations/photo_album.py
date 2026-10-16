"""Photo album: an old family album lying open on a dining table, prints held in by photo corners with
handwritten captions underneath. A few loose prints have slipped out beside it.

Built for several photos: the camera can travel across the pages from print to print.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from .. import materials as M
from .. import props as P
from ..camera_rig import Anchors
from ..polaroid_obj import card_size
from ..util import box, cylinder, mesh_object, set_smooth
from .common import (Ctx, Room, curtain, hand_font, opt, outdoor_backdrop, place_card, scatter_prints, surface_z,
                     switched_on, text_obj, wall, window)

TABLE_Z = 0.76
CAPTIONS = ["Summer '79", "Grandma's garden", "Blackpool, 1983", "Our first car!", "Christmas Eve",
            "Auntie May & Dad", "The old house", "Camping, Wales", "Sunday dinner", "Jenny, aged 6",
            "Before the wedding", "Lake District '86", "The gang", "Birthday tea", "Snow day!"]


def _page_block(name, col, x0: float, x1: float, y0: float, y1: float, z: float, thick: float, gutter_x: float,
                mat, edge_mat, steps=28):
    """The stack of pages on one side of the spine. The top sheet curves down into the gutter like a real
    bound album; away from the spine it is flat, which is where the prints are mounted."""
    bm = bmesh.new()
    nx = steps
    top, bot = [], []
    for side in (0, 1):
        y = y0 if side == 0 else y1
        trow, brow = [], []
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            d = abs(x - gutter_x)
            h = thick * (1 - math.exp(-d / 0.022))  # dips into the gutter
            h += 0.0012 * math.sin(min(1.0, d / 0.3) * math.pi) * 0.3  # the faintest lift across the page
            trow.append(bm.verts.new((x, y, z + max(0.0008, h))))
            brow.append(bm.verts.new((x, y, z)))
        top.append(trow)
        bot.append(brow)
    for i in range(nx):
        bm.faces.new((top[0][i], top[0][i + 1], top[1][i + 1], top[1][i]))           # page surface
        bm.faces.new((bot[0][i], bot[1][i], bot[1][i + 1], bot[0][i + 1]))           # underside
        bm.faces.new((bot[0][i], bot[0][i + 1], top[0][i + 1], top[0][i]))           # page edges (front)
        bm.faces.new((bot[1][i + 1], bot[1][i], top[1][i], top[1][i + 1]))           # page edges (back)
    for j in (0, nx):
        a, b, c, d = bot[0][j], bot[1][j], top[1][j], top[0][j]
        bm.faces.new((a, b, c, d) if j == 0 else (d, c, b, a))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_object(name, bm, col, mat=mat)
    o.data.materials.append(edge_mat)
    # page edges get the paper-edge material (slightly striated, yellowed)
    for poly in o.data.polygons:
        if abs(poly.normal.y) > 0.7 or abs(poly.normal.x) > 0.95:
            poly.material_index = 1
    return o


def _page_edge_material():
    from ..util import Nodes, new_material, srgb
    mat = new_material("AlbumPageEdges")
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    wave = n.new("ShaderNodeTexWave", _wave_type="BANDS", _bands_direction="Z", Scale=900.0, Distortion=2.0,
                 Detail=3.0)
    n.link(tc, "Object", wave, "Vector")
    c = n.mix("RGBA", (wave, "Fac"), srgb("#cfc3a4"), srgb("#e6dcc2"))
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.8)
    n.link(c, None, b, "Base Color")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    return mat


def _corner(name, col, at: Vector, sx: int, sy: int, mat, size=0.013, z=0.0):
    """A gummed photo corner: a little paper triangle pocket folded over one corner of a print."""
    bm = bmesh.new()
    t = 0.00035
    pts = [(0.0021 * sx, 0.0021 * sy), (-size * sx, 0.0021 * sy), (0.0021 * sx, -size * sy)]
    lo = [bm.verts.new((at.x + px, at.y + py, z)) for px, py in pts]
    hi = [bm.verts.new((at.x + px, at.y + py, z + t)) for px, py in pts]
    bm.faces.new(hi)
    bm.faces.new(list(reversed(lo)))
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_object(name, bm, col, mat=mat)


def _mount(ctx, col, meta, name, centre: Vector, yaw: float, corner_mat, caption, font, ink, z_hint):
    """Mount a print on the page with four photo corners and write its caption underneath."""
    obj, c, n = place_card(meta, name, col, centre, yaw, "flat")
    w, h = card_size(meta)
    rot = Matrix.Rotation(yaw, 3, "Z")
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = centre + rot @ Vector((sx * w / 2, sy * h / 2, 0))
            z = surface_z(p.x - sx * 0.003, p.y - sy * 0.003, z_hint + 0.02) or z_hint
            corner = _corner(f"{name}Corner", col, Vector((0, 0, 0)), sx, sy, corner_mat, z=0.0)
            corner.matrix_world = Matrix.Translation(Vector((p.x, p.y, z + 0.00005))) @ rot.to_4x4()
    if caption and font is not None:
        under = centre + rot @ Vector((0, -h / 2 - 0.013, 0))
        z = surface_z(under.x, under.y, z_hint + 0.02) or z_hint
        text_obj(col, caption, font, 0.0105, (under.x, under.y, z + 0.0001), (0, 0, yaw + ctx.rng.uniform(-0.03, 0.03)),
                 ink, name=f"{name}Caption")
    return obj, c, n


def build(ctx: Ctx):
    col, rng = ctx.col, ctx.rng
    s = ctx.scene_spec
    clutter = float(s.get("clutter", 0.7))
    pages_kind = opt(ctx, "pages", "black")
    captions_on = bool(opt(ctx, "captions", True))

    X0, X1, Y0, Y1, H = -2.3, 2.3, -2.3, 2.0, 2.5
    walls = M.plaster("DiningWalls", "#d6cdb8", rough=0.85, bump=0.8, stains=0.2)
    floor = M.wood("DiningFloor", "oak", varnish=0.45, wear=0.6, dust=0.05, grain_axis="X", planks=(1.3, 0.13))
    box("Floor", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, -0.025), floor, col)
    box("Ceiling", X1 - X0, Y1 - Y0, 0.05, (0, (Y0 + Y1) / 2, H + 0.025), M.plaster("DCeil", "#efe9dd", 0.9, 0.4, 0.1),
        col)
    win = dict(c=-0.35, w=1.3, b=0.9, t=2.15)
    wall("BackWall", col, walls, "y", Y1, X0, X1, 0, H, openings=[(win["c"], win["w"], win["b"], win["t"])])
    window("AlbumWindow", col, "y", Y1, win["c"], win["w"], win["b"], win["t"], inward=-1, panes=(3, 3))
    outdoor_backdrop(col, Vector((win["c"], Y1, 0)), Vector((0, 1, 0)), rng, distance=7.0)
    if opt(ctx, "net_curtains", True):
        curtain("AlbumNets", col, "y", Y1, win["c"], win["w"] * 1.5, win["b"] + 0.02, win["t"] - 0.02, -1,
                color="#f3efe6", sheer=0.9, folds=26, gather=0.6)
    side = dict(c=0.5, w=0.9, b=0.9, t=2.1)
    wall("LeftWall", col, walls, "x", X0, Y0, Y1, 0, H, openings=[(side["c"], side["w"], side["b"], side["t"])])
    window("AlbumSideWindow", col, "x", X0, side["c"], side["w"], side["b"], side["t"], inward=1, panes=(2, 3))
    outdoor_backdrop(col, Vector((X0, side["c"], 0)), Vector((-1, 0, 0)), rng, distance=6.0, trees=0, hedge=False)
    wall("RightWall", col, walls, "x", X1, Y0, Y1, 0, H)
    wall("FrontWall", col, walls, "y", Y0, X0, X1, 0, H)
    trim = M.wood("DadoRail", "painted_white", varnish=0.4, wear=0.3, grain_axis="X")
    box("DadoRail", X1 - X0, 0.025, 0.05, (0, Y1 - 0.075, 0.9), trim, col, bevel=0.004)

    # dining table, chairs, a dresser with plates
    oak = M.wood("DiningTable", "oak", varnish=0.6, wear=0.55, dust=0.04, grain_axis="X", seed=1.3)
    box("TableTop", 1.6, 0.95, 0.04, (0.0, 0.25, TABLE_Z - 0.02), oak, col, bevel=0.006)
    for lx in (-0.72, 0.72):
        for ly in (-0.38, 0.38):
            cylinder("TableLeg", 0.035, TABLE_Z - 0.04, (lx, 0.25 + ly, 0.0), oak, col, 24, radius2=0.025)
    chair_wood = M.wood("Chairs", "walnut", varnish=0.6, wear=0.5, grain_axis="Z")
    for k, (cx, cy, rz) in enumerate(((0.45, 0.95, 180), (-0.45, 0.95, 172), (1.05, 0.2, 90))):
        root = bpy.data.objects.new(f"Chair{k}", None)
        ctx.col.objects.link(root)
        root.location = (cx, cy, 0)
        root.rotation_euler = (0, 0, math.radians(rz))
        for nm, dims, loc in [("Seat", (0.44, 0.42, 0.035), (0, 0, 0.45)),
                              ("Back", (0.42, 0.03, 0.45), (0, 0.2, 0.7))]:
            o = box(f"Chair{k}{nm}", *dims, loc, chair_wood, col, bevel=0.006)
            o.parent = root
        for lx in (-0.19, 0.19):
            for ly in (-0.18, 0.18):
                o = box(f"Chair{k}Leg", 0.03, 0.03, 0.45, (lx, ly, 0.225), chair_wood, col, bevel=0.003)
                o.parent = root
    dresser = M.wood("Dresser", "pine", varnish=0.5, wear=0.6, grain_axis="Z")
    box("Dresser", 1.3, 0.45, 0.9, (1.45, Y1 - 0.3, 0.45), dresser, col, bevel=0.006)
    box("DresserRack", 1.3, 0.25, 1.0, (1.45, Y1 - 0.2, 1.42), dresser, col, bevel=0.006)
    for i in range(5):
        pl = cylinder(f"DresserPlate{i}", 0.1, 0.012, (0.98 + i * 0.235, Y1 - 0.3, 1.18 + 0.1),
                      M.ceramic("DresserPlate", rng.choice(["#e9e3d3", "#c9d6dc", "#d8c4a0"]), 0.05, 0.3, 0.3),
                      col, 48, bevel=0.003)
        pl.rotation_euler = (math.radians(80), 0, 0)
    surf = TABLE_Z

    lights = []
    if switched_on(ctx, "lamp"):
        lamp, ll = P.bankers_lamp("AlbumLamp", col, (-0.55, 0.6, surf), math.radians(-25), on=True, power=7.0)
        if ll:
            lights.append(ll)
    elif clutter > 0.4:
        P.bankers_lamp("AlbumLamp", col, (-0.55, 0.6, surf), math.radians(-25), on=False)

    # ------------------------------------------------------------------ the album
    cover_col = opt(ctx, "cover", "green")
    cover = M.leather("AlbumCover", {"green": "#2f4a38", "red": "#6a2424", "brown": "#5a3a26"}.get(cover_col, "#2f4a38"),
                      rough=0.55, wear=0.6)
    page_mat = (M.paper("AlbumPagesBlack", "#1e1d1b", rough=0.9, age=0.2) if pages_kind == "black"
                else M.paper("AlbumPagesCream", "#e8dfc8", rough=0.8, age=0.5))
    edge_mat = _page_edge_material()
    corner_mat = (M.paper("PhotoCornerBlack", "#111111", rough=0.45, age=0.0) if pages_kind != "black"
                  else M.paper("PhotoCornerGold", "#b39350", rough=0.4, age=0.2))
    ink = (M.plastic("WhitePencil", "#e8e4da", rough=0.85) if pages_kind == "black"
           else M.plastic("AlbumInk", "#232a46", rough=0.5))
    font = hand_font(ctx, ("ReenieBeanie.ttf", "Caveat.ttf", "IndieFlower.ttf")) if captions_on else None

    ax, ay = -0.02, 0.2
    album_rot = 0.0  # the spine runs along Y; pages open to the left and right
    pw, pd = 0.30, 0.33          # one page
    board = 0.004
    thick = 0.012
    z0 = surf
    box("AlbumCoverL", pw + 0.012, pd + 0.014, board, (ax - (pw + 0.012) / 2 - 0.004, ay, z0 + board / 2), cover, col,
        bevel=0.0015)
    box("AlbumCoverR", pw + 0.012, pd + 0.014, board, (ax + (pw + 0.012) / 2 + 0.004, ay, z0 + board / 2), cover, col,
        bevel=0.0015)
    spine = cylinder("AlbumSpine", 0.012, pd + 0.014, (ax, ay - (pd + 0.014) / 2, z0 + 0.004), cover, col, 24,
                     rot=(math.radians(-90), 0, 0))
    spine.scale = (1.0, 0.45, 1.0)
    pz = z0 + board
    _page_block("AlbumPagesL", col, ax - pw - 0.002, ax - 0.002, ay - pd / 2, ay + pd / 2, pz, thick, ax, page_mat,
                edge_mat)
    _page_block("AlbumPagesR", col, ax + 0.002, ax + pw + 0.002, ay - pd / 2, ay + pd / 2, pz, thick, ax, page_mat,
                edge_mat)
    bpy.context.view_layer.update()
    top_z = pz + thick

    # four prints a page; the hero top-left of the right-hand page
    meta = ctx.job["polaroid"]
    extras = list(ctx.job.get("extra_prints", []))
    card_h = meta["card_mm"][1] / 1000.0
    placement = s.get("placement", "mounted")
    caps = CAPTIONS[:]
    rng.shuffle(caps)
    hero_caption = (ctx.spec.get("polaroid", {}).get("caption") or "").strip() or caps.pop()
    slots = []
    for side_sign in (-1, 1):
        for row_y in (0.082, -0.073):
            for col_x in (0.085, 0.218):
                slots.append(Vector((ax + side_sign * col_x, ay + row_y, top_z)))
    hero_slot = 4 if placement == "mounted" else -1   # right page, top row, next to the gutter
    hero = centre = normal = None
    for i, slot in enumerate(slots):
        yaw = math.radians(rng.uniform(-2.5, 2.5))
        if i == hero_slot:
            hero, centre, normal = _mount(ctx, col, meta, "HeroPrint", slot, yaw * 0.5, corner_mat,
                                          hero_caption if captions_on else None, font, ink, top_z)
        elif extras:
            _mount(ctx, col, extras.pop(0), f"Mounted{i}", slot, yaw, corner_mat,
                   caps.pop() if captions_on and caps else None, font, ink, top_z)
        elif rng.random() < 0.6:
            # an empty space: just the corners where a photo was taken out
            w, h = card_size(meta)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    p = slot + Vector((sx * w / 2, sy * h / 2, 0))
                    _corner(f"EmptyCorner{i}", col, Vector((p.x, p.y, 0)), sx, sy, corner_mat, z=top_z + 0.00005)

    if placement != "mounted":
        # the hero has been taken out of its corners and lies loose on the right-hand page
        anchor = Vector((ax + 0.16, ay - 0.01, top_z))
        hero, centre, normal = place_card(meta, "HeroPrint", col, anchor, math.radians(rng.uniform(-18, 18)), "flat")

    # loose prints that slipped out beside the album
    if s.get("extra_photos", True) and extras:
        scatter_prints(extras[:3], col, Vector((ax + 0.5, ay - 0.08, surf)), 0.14, rng, surf, prefix="Loose")

    # ------------------------------------------------------------------ table things
    if opt(ctx, "tea", True):
        P.cup_and_saucer("AlbumTea", col, (ax + 0.48, ay + 0.24, surf), math.radians(rng.uniform(0, 360)))
    if clutter > 0.3:
        P.reading_glasses("AlbumGlasses", col, (ax - 0.45, ay - 0.2, surf), math.radians(rng.uniform(-20, 20)))
    if clutter > 0.5:
        pen = P.pencil("AlbumPencil", col, color="#e8e4da" if pages_kind == "black" else "#2a4a7a", rng=rng)
        pen.location = (ax + 0.36, ay - 0.24, surf + 0.0038)
        pen.rotation_euler = (0, math.radians(90), math.radians(rng.uniform(70, 110)))
    if clutter > 0.6:
        P.vase_with_stems("AlbumFlowers", col, (0.55, 0.62, surf), rng)

    el = 48.0
    view = Vector((0.1, -1.0, 0.0)).normalized()
    vd = Vector((view.x * math.cos(math.radians(el)), view.y * math.cos(math.radians(el)), math.sin(math.radians(el))))
    apparent = card_h * max(0.35, abs(normal.dot(vd)))
    ctx.sun_window = dict(centre=(X0, side["c"], (side["b"] + side["t"]) / 2), bottom=side["b"], top=side["t"],
                          along=(0, 1, 0), width=side["w"], panes=2, rows=3)
    anchors = Anchors(
        subject=centre, card_normal=normal, card_height=apparent, view_dir=vd,
        rack_point=Vector((ax + 0.48, ay + 0.24, surf + 0.06)), tilt_from=Vector((win["c"], Y1, 1.6)),
        pan_from=Vector((ax - 0.15, ay + 0.08, top_z)), reveal_target=Vector((0.0, 0.4, surf + 0.2)),
        min_height=surf + 0.02,
    )
    room = Room(Vector((X0, Y0, 0)), Vector((X1, Y1, H)))
    dust_box = (Vector((-1.0, -0.5, surf)), Vector((1.0, 1.2, surf + 1.2)))
    return dict(anchors=anchors, room=room, dust_box=dust_box, lights=lights, hero=hero)
