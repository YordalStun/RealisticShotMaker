"""Render instant prints on a table under raking window light to judge damage realism.

Runs with a Python that has numpy, Pillow and the `bpy` module:
    python tools/print_studio.py OUT.png [--samples 128] [--size 1600x1000] [--close]
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "rsm_blender"))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from rsm import catalog  # noqa: E402
from rsm.polaroid import generate  # noqa: E402
from rsm.spec import PolaroidSpec  # noqa: E402
from rsmb import filmlab, lens, materials as M  # noqa: E402
from rsmb.locations.common import place_card  # noqa: E402
from rsmb.util import box  # noqa: E402

PRINTS = [
    ("brand_new", "builtin:cat", "600", "classic", "Chelsea"),
    ("loved", "builtin:coffee", "600", "classic", "Café, Lisbon"),
    ("shoebox", "builtin:beach", "sx70", "cream", "Cromer '87"),
    ("water_damaged", "builtin:garden", "600", "classic", "Nan's garden"),
    ("battered", "builtin:birthday", "600", "black", "Happy 6th!"),
    ("sun_bleached", "builtin:snow", "instax_mini", "classic", "Xmas 89"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--size", default="1600x1000")
    ap.add_argument("--close", action="store_true", help="macro view of one battered print")
    ap.add_argument("--work", default=os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "_studio"))
    a = ap.parse_args()
    W, H = (int(v) for v in a.size.split("x"))
    os.makedirs(a.work, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    col = sc.collection
    # table
    box("Table", 1.6, 1.2, 0.04, (0, 0, -0.02), M.wood("Table", "oak", varnish=0.5, wear=0.5, dust=0.05), col,
        bevel=0.004)
    prints = PRINTS[4:5] if a.close else PRINTS
    r = random.Random(4)
    positions = [(-0.16, 0.06), (-0.05, 0.075), (0.065, 0.06), (-0.12, -0.075), (0.0, -0.065), (0.12, -0.07)]
    for i, (cond, photo, film, frame, cap) in enumerate(prints):
        p = PolaroidSpec(film=film, photo=photo, frame_color=frame, caption=cap, seed=200 + i)
        c = dict(catalog.CONDITIONS[cond])
        c.pop("name")
        for k, v in c.items():
            setattr(p, k, v)
        meta = generate(p, 28.0 if a.close else 16.0).save(a.work, f"p{i}")
        x, y = (0.0, 0.0) if a.close else positions[i]
        place_card(meta, f"Print{i}", col, Vector((x, y, 0.0)), math.radians(r.uniform(-14, 14)), "flat")

    # window light: a big soft area light raking across from the left, plus a dim fill
    ld = bpy.data.lights.new("Window", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = 1.2, 0.9
    ld.energy = 900
    ld.color = (1.0, 0.9, 0.78)
    win = bpy.data.objects.new("Window", ld)
    col.objects.link(win)
    win.location = (-1.6, 0.4, 0.9)
    win.rotation_euler = (Vector((0, 0, 0.0)) - win.location).to_track_quat("-Z", "Y").to_euler()
    fl = bpy.data.lights.new("Fill", "AREA")
    fl.size = 2.0
    fl.energy = 80
    fl.color = (0.85, 0.9, 1.0)
    fo = bpy.data.objects.new("Fill", fl)
    col.objects.link(fo)
    fo.location = (1.2, -1.2, 1.5)
    fo.rotation_euler = (Vector((0, 0, 0)) - fo.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.62, 0.65, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.15

    cam_d = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_d)
    col.objects.link(cam)
    sc.camera = cam
    cam_d.sensor_width = 36
    if a.close:
        cam_d.lens = 100
        cam.location = (0.03, -0.2, 0.17)
        target = Vector((0.0, 0.0, 0.0))
        cam_d.dof.aperture_fstop = 4.0
    else:
        cam_d.lens = 50
        cam.location = (0.0, -0.42, 0.5)
        target = Vector((-0.02, 0.0, 0.0))
        cam_d.dof.aperture_fstop = 5.6
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.use_dof = True
    cam_d.dof.focus_distance = (target - cam.location).length
    lens.apply_lens(cam_d, lens.build_osl(dict(blades=9, blade_curvature=0.9, cat_eye=0.3, spherical=0.2,
                                               ca_long=0.2, ca_lat=0.05, vignette=0.5, bokeh_rim=0.1),
                                          cam_d.lens), a.work)

    c = sc.cycles
    sc.render.engine = "CYCLES"
    c.samples = a.samples
    c.use_denoising = True
    c.caustics_refractive = False
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "OPEN_EXR"
    exr = os.path.join(a.work, "studio.exr")
    sc.render.filepath = exr
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(exr)
    import numpy as np
    buf = np.empty(W * H * 4, np.float32)
    img.pixels.foreach_get(buf)
    lin = buf.reshape(H, W, 4)[::-1, :, :3].copy()
    lab = filmlab.FilmLab(dict(grade="natural", grain=0.08, digital_noise=True, bloom=0.1, vignette=0.15,
                               key=0.2), H, W)
    filmlab.write_png8(a.out, lab.process(lin, 0))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
