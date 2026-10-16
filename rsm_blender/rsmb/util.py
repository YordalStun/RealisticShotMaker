"""Helpers for building geometry and node trees inside Blender."""
from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector


# ---------------------------------------------------------------------------
# Collections / objects
# ---------------------------------------------------------------------------

def collection(name: str, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if col.name not in [c.name for c in parent.children]:
        parent.children.link(col)
    return col


def link(obj, col=None):
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_object(name: str, bm: bmesh.types.BMesh, col=None, smooth: bool = False, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth() if hasattr(me, "shade_smooth") else [setattr(p, "use_smooth", True) for p in me.polygons]
    obj = bpy.data.objects.new(name, me)
    link(obj, col)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def set_smooth(obj, smooth=True):
    for p in obj.data.polygons:
        p.use_smooth = smooth


def add_bevel(obj, width: float, segments: int = 3, angle_deg: float = 35.0, harden=True):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle_deg)
    m.harden_normals = harden
    m.miter_outer = "MITER_ARC"
    return m


def add_subsurf(obj, levels: int = 2, render_levels: int | None = None):
    m = obj.modifiers.new("Subdivision", "SUBSURF")
    m.levels = levels
    m.render_levels = render_levels if render_levels is not None else levels
    return m


def add_weighted_normals(obj):
    m = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    return m


def box_bm(sx, sy, sz, center=(0, 0, 0)) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((sx, sy, sz)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm


def box(name, sx, sy, sz, loc=(0, 0, 0), mat=None, col=None, bevel=0.0, segments=3, rot=(0, 0, 0)):
    obj = mesh_object(name, box_bm(sx, sy, sz), col, mat=mat)
    obj.location = loc
    obj.rotation_euler = rot
    if bevel > 0:
        add_bevel(obj, bevel, segments)
        add_weighted_normals(obj)
    return obj


def cylinder_bm(radius, depth, segments=48, cap=True, center=(0, 0, 0), radius2=None) -> bmesh.types.BMesh:
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=segments, radius1=radius,
                          radius2=radius if radius2 is None else radius2, depth=depth)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm


def cylinder(name, radius, depth, loc=(0, 0, 0), mat=None, col=None, segments=48, radius2=None, bevel=0.0,
             rot=(0, 0, 0)):
    obj = mesh_object(name, cylinder_bm(radius, depth, segments, True, (0, 0, depth / 2), radius2), col, mat=mat)
    obj.location = loc
    obj.rotation_euler = rot
    set_smooth(obj)
    if bevel > 0:
        add_bevel(obj, bevel, 3, 50)
        add_weighted_normals(obj)
    return obj


def lathe(name, profile, segments=64, mat=None, col=None, loc=(0, 0, 0), smooth=True, close=False):
    """Revolve a (radius, z) profile around Z."""
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0, z)) for r, z in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi,
                   steps=segments, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    obj = mesh_object(name, bm, col, smooth=smooth, mat=mat)
    obj.location = loc
    if smooth:
        set_smooth(obj)
    return obj


def parent_keep(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def look_at_matrix(eye: Vector, target: Vector, up=Vector((0, 0, 1))) -> Matrix:
    fwd = (target - eye).normalized()
    right = fwd.cross(up)
    if right.length < 1e-6:
        right = fwd.cross(Vector((0, 1, 0)))
    right.normalize()
    cam_up = right.cross(fwd)
    m = Matrix((right, cam_up, -fwd)).transposed().to_4x4()
    m.translation = eye
    return m


def seeded(seed: int) -> random.Random:
    return random.Random(seed)


# ---------------------------------------------------------------------------
# Node tree helper
# ---------------------------------------------------------------------------

class Nodes:
    """Tiny DSL for building shader node trees.

    n = Nodes(mat)
    tex = n.new("ShaderNodeTexNoise", Scale=40)
    n.link(tex, "Fac", bsdf, "Roughness")
    """

    def __init__(self, tree, clear=True):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        if clear:
            self.nodes.clear()
        self._x = 0

    def new(self, type_: str, **inputs):
        node = self.nodes.new(type_)
        node.location = (self._x, 0)
        self._x += 220
        for key, val in inputs.items():
            if key.startswith("_"):
                setattr(node, key[1:], val)
                continue
            sock = node.inputs.get(key)
            if sock is None:
                # some sockets share names (e.g. Mix node); fall back to attribute
                if hasattr(node, key):
                    setattr(node, key, val)
                continue
            if hasattr(val, "outputs") or isinstance(val, tuple) and len(val) == 2 and hasattr(val[0], "outputs"):
                self.link(val, None, node, key)
            else:
                try:
                    sock.default_value = val
                except (TypeError, ValueError):
                    if isinstance(val, (int, float)) and hasattr(sock.default_value, "__len__"):
                        sock.default_value = [val] * len(sock.default_value)
                    else:
                        raise
        return node

    @staticmethod
    def out(node, name=None):
        if isinstance(node, tuple):
            node, name = node
        if name is None:
            return node.outputs[0]
        if isinstance(name, int):
            return node.outputs[name]
        s = node.outputs.get(name)
        if s is None:
            raise KeyError(f"{node.bl_idname} has no output {name!r}: {[o.name for o in node.outputs]}")
        return s

    @staticmethod
    def _is_node_like(a):
        return hasattr(a, "outputs") or hasattr(a, "is_output") or (
            isinstance(a, tuple) and len(a) == 2 and hasattr(a[0], "outputs"))

    def link(self, a, a_out, b, b_in):
        """Connect a node output to b's input; plain values are written into the socket instead."""
        if isinstance(b_in, int):
            dst = b.inputs[b_in]
        else:
            dst = b.inputs.get(b_in)
            if dst is None:
                raise KeyError(f"{b.bl_idname} has no input {b_in!r}: {[i.name for i in b.inputs]}")
        if not self._is_node_like(a):
            try:
                dst.default_value = a
            except (TypeError, ValueError):
                dst.default_value = [a] * len(dst.default_value)
            return b
        src = a if hasattr(a, "is_output") else self.out(a, a_out)
        self.links.new(src, dst)
        return b

    # common building blocks ------------------------------------------------
    def math(self, op, a, b=None, clamp=False):
        n = self.new("ShaderNodeMath", _operation=op, _use_clamp=clamp)
        self._feed(n, 0, a)
        if b is not None:
            self._feed(n, 1, b)
        return n

    def vmath(self, op, a, b=None):
        n = self.new("ShaderNodeVectorMath", _operation=op)
        self._feed(n, 0, a)
        if b is not None:
            self._feed(n, 1, b)
        return n

    def mix(self, data_type, fac, a, b, blend="MIX", clamp=True):
        n = self.new("ShaderNodeMix", _data_type=data_type, _blend_type=blend, _clamp_result=clamp)
        # Mix node sockets: 0 Factor(float), 1 Factor(vector), A/B per type
        idx = {"FLOAT": (2, 3), "VECTOR": (4, 5), "RGBA": (6, 7)}[data_type]
        self._feed(n, 0, fac)
        self._feed(n, idx[0], a)
        self._feed(n, idx[1], b)
        out_idx = {"FLOAT": 0, "VECTOR": 1, "RGBA": 2}[data_type]
        return (n, out_idx)

    def ramp(self, fac, stops, interp="LINEAR"):
        n = self.new("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = interp
        while len(cr.elements) > len(stops):
            cr.elements.remove(cr.elements[-1])
        while len(cr.elements) < len(stops):
            cr.elements.new(0.5)
        for el, (pos, col) in zip(cr.elements, stops):
            el.position = pos
            el.color = col if len(col) == 4 else (*col, 1.0)
        self._feed(n, 0, fac)
        return n

    def _feed(self, node, idx, val):
        sock = node.inputs[idx]
        if val is None:
            return
        if hasattr(val, "outputs") or (isinstance(val, tuple) and len(val) == 2 and hasattr(val[0], "outputs")):
            self.links.new(self.out(val), sock)
        elif hasattr(val, "is_output"):  # a socket
            self.links.new(val, sock)
        else:
            try:
                sock.default_value = val
            except (TypeError, ValueError):
                sock.default_value = [val] * len(sock.default_value)


def new_material(name: str):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat


def srgb(hex_or_tuple):
    """Hex '#rrggbb' or sRGB tuple → linear RGBA tuple for node colour sockets."""
    if isinstance(hex_or_tuple, str):
        h = hex_or_tuple.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    else:
        c = list(hex_or_tuple[:3])

    def lin(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return (lin(c[0]), lin(c[1]), lin(c[2]), 1.0)
