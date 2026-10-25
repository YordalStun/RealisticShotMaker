"""The instant print as geometry: a finely subdivided card with real thickness,
curl, crease folds and a folded dog-ear, textured with the generated maps."""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector

from . import materials as M
from .util import Nodes, link, new_material


def _card_materials(meta: dict, name: str):
    files = meta["files"]
    gloss = float(meta.get("gloss", 0.7))
    front = M.image_material(f"{name}_front", files["color"], files["rough"], files["height"],
                             bump_strength=0.6, bump_distance=0.00025, alpha=True, coat=0.0)
    back = M.image_material(f"{name}_back", files["back"], None, files["height"], bump_strength=0.3,
                            bump_distance=0.0002, alpha=True)
    # back: plastic with a satin sheen
    bsdf = next(nd for nd in back.node_tree.nodes if nd.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.45
    # rim: card stock, uses the front alpha so worn corners disappear on the edge too
    rim = new_material(f"{name}_rim")
    n = Nodes(rim.node_tree)
    uv = n.new("ShaderNodeTexCoord")
    tex = n.new("ShaderNodeTexImage", _interpolation="Closest")
    tex.image = bpy.data.images.load(files["color"], check_existing=True)
    n.link(uv, "UV", tex, "Vector")
    b = n.new("ShaderNodeBsdfPrincipled", Roughness=0.8)
    b.inputs["Base Color"].default_value = (0.78, 0.76, 0.72, 1.0)
    n.link(tex, "Alpha", b, "Alpha")
    out = n.new("ShaderNodeOutputMaterial")
    n.link(b, None, out, "Surface")
    if gloss > 0.5:
        # integral film has a clear plastic window over the picture: add a thin clear coat on the image area
        fbsdf = next(nd for nd in front.node_tree.nodes if nd.bl_idname == "ShaderNodeBsdfPrincipled")
        fbsdf.inputs["Coat Weight"].default_value = 0.0
    return front, back, rim


def build_card(meta: dict, name: str = "Polaroid", col=None, res_per_mm: float = 1.2, stand_deg: float | None = None):
    """Create the card object. Origin: bottom-centre edge, card in XZ plane facing -Y (towards a
    camera on the -Y side), so local +Z is 'up the card'. A framed photo builds its frame instead
    (stand_deg: the lean it stands at, to open its strut)."""
    if meta.get("frame"):
        return build_framed(meta, name, col, stand_deg)
    w_mm, h_mm = meta["card_mm"]
    w, h = w_mm / 1000.0, h_mm / 1000.0
    nx = max(24, int(w_mm * res_per_mm))
    ny = max(24, int(h_mm * res_per_mm))
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    verts = []
    for j in range(ny + 1):
        row = []
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            row.append(bm.verts.new(((u - 0.5) * w, 0.0, v * h)))
        verts.append(row)
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
            for loop in f.loops:
                co = loop.vert.co
                loop[uv_layer].uv = (co.x / w + 0.5, co.z / h)
    # faces were built with +Y normals? ensure front faces -Y
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        if f.normal.y > 0:
            f.normal_flip()

    # ------------------------------------------------------------------ deformations
    def card_xy_mm(co):
        """Vertex → texture coordinates in mm (origin top-left)."""
        return (co.x / w + 0.5) * w_mm, (1.0 - co.z / h) * h_mm

    curl = float(meta.get("curl", 0.0))
    creases = meta.get("creases") or []
    dog = meta.get("dog_ear")
    for v in bm.verts:
        x_mm, y_mm = card_xy_mm(v.co)
        disp = 0.0
        # curl: the print bows so its long edges lift towards the viewer (emulsion side shrinks)
        xn = (x_mm / w_mm - 0.5) * 2
        yn = (y_mm / h_mm - 0.5) * 2
        disp += curl * 0.0035 * (xn * xn) + curl * 0.0012 * (yn * yn)
        # creases: a sharp ridge plus a slight fold of the smaller side
        for c in creases:
            (x0, y0), (x1, y1) = c["p0"], c["p1"]
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy) + 1e-9
            sd = ((x_mm - x0) * dy - (y_mm - y0) * dx) / L       # signed distance in mm
            t = max(0.0, min(1.0, ((x_mm - x0) * dx + (y_mm - y0) * dy) / (L * L)))
            px, py = x0 + t * dx, y0 + t * dy
            dist = math.hypot(x_mm - px, y_mm - py)
            # which side is the smaller flap? the side away from the card centre
            cx, cy = w_mm / 2, h_mm / 2
            centre_side = ((cx - x0) * dy - (cy - y0) * dx) / L
            on_flap = (sd * centre_side) < 0
            depth = c["depth"]
            disp += c["sign"] * depth * 0.00035 * math.exp(-(dist / 0.8) ** 2)
            if on_flap:
                disp += c["sign"] * depth * math.tan(math.radians(4.0)) * abs(sd) * 0.001
        v.co.y -= disp  # towards the viewer (-Y)

        # dog-ear: rotate the corner flap around the fold line
    if dog:
        corner = dog["corner"]
        s = dog["size_mm"]
        ang = math.radians(dog["angle_deg"])
        cxp = 0.0 if corner[1] == "l" else w_mm
        cyp = 0.0 if corner[0] == "t" else h_mm
        a = (cxp + (s if cxp == 0 else -s), cyp)
        b = (cxp, cyp + (s if cyp == 0 else -s))
        fx, fy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(fx, fy)
        ux, uy = fx / L, fy / L
        # normal pointing to the corner
        nxn, nyn = -uy, ux
        if (cxp - a[0]) * nxn + (cyp - a[1]) * nyn < 0:
            nxn, nyn = -nxn, -nyn
        for v in bm.verts:
            x_mm, y_mm = card_xy_mm(v.co)
            d = (x_mm - a[0]) * nxn + (y_mm - a[1]) * nyn
            if d <= 0:
                continue
            # rotate in the plane spanned by (n, viewer direction)
            nd = d * math.cos(ang)
            up = d * math.sin(ang)
            nx_mm = x_mm - nxn * (d - nd)
            ny_mm = y_mm - nyn * (d - nd)
            v.co.x = (nx_mm / w_mm - 0.5) * w
            v.co.z = (1.0 - ny_mm / h_mm) * h
            v.co.y -= up * 0.001

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    link(obj, col)

    front, back, rim = _card_materials(meta, name)
    obj.data.materials.append(front)
    obj.data.materials.append(back)
    obj.data.materials.append(rim)
    sol = obj.modifiers.new("Thickness", "SOLIDIFY")
    sol.thickness = float(meta.get("thickness_mm", 1.0)) / 1000.0
    sol.offset = -1.0  # grow behind the front surface (away from the normal), front stays put
    sol.material_offset = 1
    sol.material_offset_rim = 2
    sol.use_rim = True
    sol.use_even_offset = True
    return obj


def card_size(meta: dict) -> tuple[float, float]:
    w_mm, h_mm = meta["card_mm"]
    return w_mm / 1000.0, h_mm / 1000.0


def image_centre_local(meta: dict) -> Vector:
    """Centre of the picture area in the card's local space."""
    w_mm, h_mm = meta["card_mm"]
    x, y, iw, ih = meta["image_rect_mm"]
    cx_mm = x + iw / 2
    cy_mm = y + ih / 2
    return Vector(((cx_mm / w_mm - 0.5) * w_mm / 1000.0, print_setback_mm(meta) / 1000.0,
                   (1.0 - cy_mm / h_mm) * h_mm / 1000.0))


# ---------------------------------------------------------------------------------------------------------------
# Framed photos: a picture frame around a photographic print
# ---------------------------------------------------------------------------------------------------------------

def _front_profile(kind: str, m: float) -> list[tuple[float, float]]:
    """The moulding's face from its outer edge (d = 0) to its sight edge (d = m), as (d, setback) in mm:
    setback 0 is the frontmost point, larger is further back towards the wall."""
    pts = []
    if kind == "flat":
        pts = [(0, 1.2), (0.6, 0), (m - 0.6, 0), (m, 1.0)]
    elif kind == "rounded":
        for k in range(13):
            u = k / 12
            pts.append((u * m, 4.5 * (1 - math.sin(math.pi * (0.08 + 0.84 * u)) ** 0.7)))
    elif kind == "stepped":
        a, b = 0.42 * m, 0.72 * m
        pts = [(0, 1.5), (0.8, 0), (a, 0), (a + 0.6, 2.8), (b, 2.8), (b + 0.6, 5.0), (m, 5.0)]
    else:   # ornate: rounded outer bead, a deep cove, a fine inner bead and a sloped sight edge
        for k in range(29):
            u = k / 28
            y = 1.0
            if u < 0.28:
                y = 3.2 * (1 - math.sin(math.pi * u / 0.28) ** 0.6)
            elif u < 0.7:
                v = (u - 0.28) / 0.42
                y = 3.2 + 6.0 * math.sin(math.pi * v) ** 0.8 - 2.4 * v
            elif u < 0.82:
                v = (u - 0.7) / 0.12
                y = 0.8 + 3.2 * (1 - math.sin(math.pi * v))
            else:
                v = (u - 0.82) / 0.18
                y = 4.0 + 3.0 * v
            pts.append((u * m, y))
    return pts


def _loft_rect(name: str, W: float, H: float, profile, col=None, mats=(), sharp_deg: float = 32.0,
               side_mat=(0, 1, 0, 1), closed=True):
    """Sweep a cross-section around a rectangle with mitred corners (one set of vertices per side, so the
    mitres stay crisp). profile: [(inset_mm, setback_mm)]. The rectangle is W x H mm, bottom edge on z = 0,
    centred on x; setback goes along +Y. side_mat: material index for bottom, right, top, left."""
    bm = bmesh.new()
    n = len(profile)

    def corner(d, y, c):
        sx = (W / 2 - d) / 1000.0
        sz = (H / 2 - d) / 1000.0
        x, z = ((-sx, -sz), (sx, -sz), (sx, sz), (-sx, sz))[c]
        return Vector((x, y / 1000.0, H / 2000.0 + z))

    # profile corners that should shade hard
    sharp = set()
    for k in range(n):
        if not closed and k in (0, n - 1):
            continue
        p0, p1, p2 = profile[k - 1], profile[k], profile[(k + 1) % n]
        a = Vector((p1[0] - p0[0], p1[1] - p0[1]))
        b = Vector((p2[0] - p1[0], p2[1] - p1[1]))
        if a.length > 1e-9 and b.length > 1e-9 and math.degrees(a.angle(b)) > sharp_deg:
            sharp.add(k)
    for side in range(4):
        c0, c1 = side, (side + 1) % 4
        rows = [(bm.verts.new(corner(d, y, c0)), bm.verts.new(corner(d, y, c1))) for d, y in profile]
        last = n if closed else n - 1
        for k in range(last):
            a, b = rows[k], rows[(k + 1) % n]
            f = bm.faces.new((a[0], a[1], b[1], b[0]))
            f.material_index = side_mat[side]
            f.smooth = True
        for k in sharp:
            e = bm.edges.get(rows[k])
            if e is not None:
                e.smooth = False
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    link(obj, col)
    for mt in mats:
        obj.data.materials.append(mt)
    return obj


def _frame_materials(finish: str, name: str):
    """(along-X material, along-Z material) so the grain runs along every side of the moulding."""
    woods = {"oak": ("oak", 0.55, 0.15), "walnut": ("walnut", 0.6, 0.12), "pine": ("pine", 0.35, 0.25),
             "white": ("painted_white", 0.5, 0.35)}
    if finish in woods:
        preset, varnish, wear = woods[finish]
        return (M.wood(f"{name}_woodX", preset, varnish, wear, scale=9.0, grain_axis="X"),
                M.wood(f"{name}_woodZ", preset, varnish, wear, scale=9.0, grain_axis="Z"))
    if finish == "gold":
        m = M.metal(f"{name}_gilt", "#d9b45e", 0.3, 0.3, 0.3)
    elif finish == "silver":
        m = M.metal(f"{name}_silver", "#c6c8ca", 0.22, 0.3, 0.15, brushed=True)
    else:
        m = M.plastic(f"{name}_black", "#151413", 0.38, coat=0.15)
    return m, m


def _frame_glass(name: str):
    """Picture glass: reflections and the odd smudge, but light goes straight through (no refraction, no
    shadow), the way a 2 mm pane looks."""
    from .util import srgb
    mat = new_material(name)
    n = Nodes(mat.node_tree)
    tc = n.new("ShaderNodeTexCoord")
    sm = n.new("ShaderNodeTexNoise", Scale=60.0, Detail=6.0, Roughness=0.6)
    n.link(tc, "Object", sm, "Vector")
    smr = n.ramp((sm, "Fac"), [(0.6, (0, 0, 0)), (0.78, (1, 1, 1))])
    vor = n.new("ShaderNodeTexVoronoi", Scale=900.0)
    n.link(tc, "Object", vor, "Vector")
    dust = n.math("MULTIPLY", n.math("LESS_THAN", (vor, "Distance"), 0.09), n.math("GREATER_THAN", (vor, "Color"), 0.85))
    gloss = n.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Color"].default_value = (1, 1, 1, 1)
    n.link(n.math("ADD", 0.01, n.math("MULTIPLY", (smr, "Color"), 0.08)), None, gloss, "Roughness")
    fres = n.new("ShaderNodeFresnel", IOR=1.52)
    clear = n.new("ShaderNodeBsdfTransparent")
    clear.inputs["Color"].default_value = srgb("#fcfefc")
    mix = n.new("ShaderNodeMixShader")
    n.link(fres, "Fac", mix, "Fac")
    n.link(clear, None, mix, 1)
    n.link(gloss, None, mix, 2)
    speck = n.new("ShaderNodeBsdfDiffuse")
    speck.inputs["Color"].default_value = (0.7, 0.68, 0.64, 1)
    mix2 = n.new("ShaderNodeMixShader")
    n.link(dust, None, mix2, "Fac")
    n.link(mix, None, mix2, 1)
    n.link(speck, None, mix2, 2)
    out = n.new("ShaderNodeOutputMaterial")
    n.link(mix2, None, out, "Surface")
    return mat


def _lip(fr: dict) -> tuple[float, float]:
    """How far back the glass sits behind the frame's front, and the rebate width (mm)."""
    face = _front_profile(fr.get("profile", "flat"), float(fr["moulding_mm"]))
    return min(float(fr["depth_mm"]) - 7.0, face[-1][1] + 4.0), 6.0


def print_setback_mm(meta: dict) -> float:
    """How far behind the front of the object the picture is (a framed photo sits behind glass and mat)."""
    fr = meta.get("frame")
    if not fr:
        return 0.0
    return _lip(fr)[0] + 2.0 + (1.6 if fr.get("mat") else 0.0) + 0.05


def build_framed(meta: dict, name: str = "Polaroid", col=None, stand_deg: float | None = None):
    """A photo in a picture frame, as one object tree with the same rules as a card: origin at the
    bottom-centre of the front, facing -Y, up is +Z, depth goes back along +Y. stand_deg opens the strut
    on the back for a frame standing at that lean; otherwise it's folded flat."""
    fr = meta["frame"]
    W, H = fr["outer_mm"]
    m = float(fr["moulding_mm"])
    D = float(fr["depth_mm"])
    iw, ih = fr["inner_mm"]
    face = _front_profile(fr.get("profile", "flat"), m)
    lip, rebate = _lip(fr)
    prof = face + [(m, lip), (m - rebate, lip), (m - rebate, D), (0, D)]
    mx, mz = _frame_materials(fr.get("finish", "oak"), name)
    obj = _loft_rect(name, W, H, prof, col, (mx, mz), side_mat=(0, 1, 0, 1))

    def child(o):
        o.parent = obj
        return o

    # glass, then the mat, then the print, then the backing board
    under = rebate - 1.0                          # how far everything behind the lip extends under it
    gw, gh = iw + 2 * under, ih + 2 * under
    y = lip
    from .util import box
    glass = box(f"{name}_Glass", gw / 1000, 0.002, gh / 1000, (0, (y + 1.0) / 1000, H / 2000), _frame_glass(f"{name}_glass"), col)
    child(glass)
    y += 2.0
    if fr.get("mat"):
        vw, vh = fr["window_mm"]
        t = 1.6
        bev = t * 0.9                              # 45-degree bevel: the window's back is that much smaller
        mprof = [(0, 0), ((gw - vw) / 2 - 0.0, 0), ((gw - vw) / 2 + bev, t), (0, t)]
        mat_paper = M.paper(f"{name}_mat", "#ece6d8", 0.85, age=0.15)
        core = M.paper(f"{name}_matcore", "#f6f3ec", 0.8, age=0.0)
        mo = _loft_rect(f"{name}_Mat", gw, gh, mprof, col, (mat_paper, core), sharp_deg=20, side_mat=(0, 0, 0, 0))
        for p in mo.data.polygons:                 # the bevelled cut shows the white core
            p.material_index = 1 if abs(p.normal.y) < 0.95 and abs(p.normal.y) > 0.3 else 0
        mo.location = (0, y / 1000, (H - gh) / 2000)
        child(mo)
        y += t
    pm = dict(meta)
    pm.update(card_mm=list(meta["print_mm"]), image_rect_mm=list(meta["print_image_rect_mm"]), thickness_mm=0.3,
              curl=0.0, creases=[], dog_ear=None, frame=None)
    pw, ph = pm["card_mm"]
    pr = build_card(pm, f"{name}_Print", col, res_per_mm=0.25)
    pr.location = (0, (y + 0.05) / 1000, (H - ph) / 2000)
    child(pr)
    y += 0.4
    back = box(f"{name}_Backing", gw / 1000, 0.0025, gh / 1000, (0, (y + 1.25) / 1000, H / 2000),
               M.paper(f"{name}_hardboard", "#6a5440", 0.9, age=0.4), col)
    child(back)
    # the strut: a tapered leg hinged two-thirds of the way up the back
    leg_mat = M.paper(f"{name}_strut", "#3a2e24", 0.8, age=0.2)
    zh = H * 0.62
    sw = min(32.0, W * 0.2)
    if stand_deg is not None and stand_deg > 1:
        L = math.radians(stand_deg)
        # foot on the floor the frame stands on: local points with z = (y - D) tan L
        s = zh * 0.5
        foot = Vector((0, (D + s) / 1000, s * math.tan(L) / 1000))
    else:
        foot = Vector((0, (D + 2.0) / 1000, zh * 0.08 / 1000))
    hinge = Vector((0, (D + 1.0) / 1000, zh / 1000))
    bm = bmesh.new()
    axis = (foot - hinge)
    sideways = Vector((1, 0, 0))
    thick = axis.cross(sideways).normalized() * 0.0015
    vs = []
    for t_, half in ((0.0, sw * 0.32), (1.0, sw * 0.5)):
        c = hinge + axis * t_
        for sx in (-1, 1):
            for sy in (0, 1):
                vs.append(bm.verts.new(c + sideways * (sx * half / 1000) + thick * sy))
    # vs: [top: (-,0),(-,1),(+,0),(+,1)], [bottom: same]
    q = lambda *ix: bm.faces.new([vs[i] for i in ix])
    q(0, 2, 6, 4); q(1, 5, 7, 3); q(0, 4, 5, 1); q(2, 3, 7, 6); q(0, 1, 3, 2); q(4, 6, 7, 5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f"{name}_Strut")
    bm.to_mesh(me)
    bm.free()
    strut = bpy.data.objects.new(f"{name}_Strut", me)
    link(strut, col)
    strut.data.materials.append(leg_mat)
    child(strut)
    obj["rsm_frame"] = True
    return obj
