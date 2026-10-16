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


def build_card(meta: dict, name: str = "Polaroid", col=None, res_per_mm: float = 1.2):
    """Create the card object. Origin: bottom-centre edge, card in XZ plane facing -Y (towards a
    camera on the -Y side), so local +Z is 'up the card'."""
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
    return Vector(((cx_mm / w_mm - 0.5) * w_mm / 1000.0, 0.0, (1.0 - cy_mm / h_mm) * h_mm / 1000.0))
