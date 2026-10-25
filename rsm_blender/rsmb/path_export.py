"""Camera path export for the app's 3D view: a light description of the built set and the camera's path.

Writes JSON: simplified set (oriented boxes with a colour; the room shell flagged so the view can see inside),
the photos as quads (the hero with its image), and per frame the camera position, viewing direction, up,
field of view, focus point and which shot of the shot list it belongs to.
"""
from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

ROOM_WORDS = ("Wall", "Floor", "Ceiling")
SKIP_WORDS = ("Haze", "Dust", "Portal", "Steam", "Mood", "Cobweb", "Fairy", "Glow", "Sky")


def _colour(obj) -> list[float]:
    """A representative colour for an object: its first material's base colour (or emission)."""
    for slot in obj.material_slots:
        m = slot.material
        if m is None:
            continue
        if m.use_nodes and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    sock = n.inputs.get("Base Color")
                    if sock is not None and not sock.is_linked:
                        return [round(c, 3) for c in sock.default_value[:3]]
                    return [0.55, 0.5, 0.45]
                if n.type == "EMISSION":
                    return [1.0, 0.85, 0.6]
        return [round(c, 3) for c in m.diffuse_color[:3]]
    return [0.6, 0.6, 0.6]


def _boxes():
    from .locations.common import PLACED_PRINTS
    prints = {p["name"] for p in PLACED_PRINTS}
    out = []
    for o in bpy.data.objects:
        if o.type not in ("MESH", "CURVE", "FONT") or o.hide_render:
            continue
        if any(w in o.name for w in SKIP_WORDS) or o.name in prints or (o.parent and o.parent.name in prints):
            continue
        corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
        size = (max(c.x for c in corners) - min(c.x for c in corners), max(c.y for c in corners) - min(c.y for c in corners),
                max(c.z for c in corners) - min(c.z for c in corners))
        if math.sqrt(sum(s * s for s in size)) < 0.02:
            continue   # pencils' ferrules, crumbs, matches: just noise at this scale
        out.append({"name": o.name, "c": [[round(v, 4) for v in c] for c in corners], "col": _colour(o),
                    "room": any(w in o.name for w in ROOM_WORDS)})
    return out


def _prints(job: dict):
    from .locations.common import PLACED_PRINTS
    out = []
    for p in PLACED_PRINTS:
        o = bpy.data.objects.get(p["name"])
        if o is None:
            continue
        corners = [o.matrix_world @ Vector(c) for c in o.bound_box]
        # the card's face: the four corners furthest along its thin axis' opposite sides collapse to a quad
        n = Vector(p["normal"]).normalized()
        front = sorted(corners, key=lambda c: c.dot(n))[-4:]
        ctr = sum(front, Vector()) / 4
        up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((0, 1, 0))
        right = up.cross(n).normalized()
        up = n.cross(right).normalized()
        quad = sorted(front, key=lambda c: math.atan2((c - ctr).dot(up), (c - ctr).dot(right)))
        out.append({"quad": [[round(v, 4) for v in c] for c in quad], "hero": bool(p.get("hero")),
                    "image": job["polaroid"]["files"].get("color", "") if p.get("hero") else ""})
    return out


def export(job: dict, path: str, scene=None):
    scene = scene or bpy.context.scene
    cam = scene.camera
    shots = job.get("shots") or [{"t0": 0.0, "t1": 1.0, "move": job["spec"]["camera"]["move"]}]
    fs, fe = scene.frame_start, scene.frame_end
    n = fe - fs + 1
    frames = []
    for i, f in enumerate(range(fs, fe + 1)):
        scene.frame_set(f)
        m = cam.matrix_world
        fwd = (m.to_3x3() @ Vector((0, 0, -1))).normalized()
        up = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
        # the custom lens zooms through its aperture-ratio track; Blender's own lens through the focal length
        zoom = cam.data.dof.aperture_ratio if cam.data.get("rsm_zoomable") else 1.0
        lens = cam.data.lens * zoom
        fov = 2 * math.atan(cam.data.sensor_width / (2 * lens))
        t = i / max(1, n - 1)
        shot = next((k for k, s in enumerate(shots) if t <= s["t1"] + 1e-9), len(shots) - 1)
        frames.append({"p": [round(v, 4) for v in m.translation], "f": [round(v, 4) for v in fwd],
                       "u": [round(v, 4) for v in up], "fov": round(fov, 4),
                       "fd": round(cam.data.dof.focus_distance, 4), "shot": shot})
    res = job["resolved"]
    data = {"version": 1, "fps": res["fps"], "aspect": res["width"] / res["height"], "frames": frames,
            "shots": [{"move": s["move"], "t0": s["t0"], "t1": s["t1"]} for s in shots],
            "boxes": _boxes(), "prints": _prints(job)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path
