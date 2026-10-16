"""Blender entry point.

    blender -b --factory-startup -P entry.py -- --job path/to/job.json [--still 0.5] [--regrade]

Builds the shot described in the job file and renders it frame by frame:
EXR (linear HDR) -> film lab -> 16-bit PNG, ready for encoding.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import random
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from rsmb import camera_rig, filmlab, lens, render, world  # noqa: E402
from rsmb.locations.common import Ctx, aim_sun_through  # noqa: E402
from rsmb.render import log  # noqa: E402
from rsmb.util import collection  # noqa: E402


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--still", type=float, default=None, help="render one frame at this point (0..1) of the shot")
    ap.add_argument("--still-out", default=None)
    ap.add_argument("--regrade", action="store_true", help="re-run the film lab on existing EXR frames")
    ap.add_argument("--save-blend", default=None)
    ap.add_argument("--frames", default=None, help="comma separated frame numbers to render")
    ap.add_argument("--crop", default=None, help="x0,y0,x1,y1 fractions: render only this window of the frame "
                    "(full-resolution detail check)")
    return ap.parse_args(argv)


def build_scene(job: dict):
    spec = job["spec"]
    res = job["resolved"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from rsmb import materials as _materials
    _materials._cache.clear()  # materials from a previous build in this process no longer exist
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    col = collection("RSM_Set")
    rng = random.Random(int(spec["scene"].get("seed", 7)))
    tod = spec["scene"].get("time_of_day", "golden")
    ctx = Ctx(job=job, spec=spec, col=col, rng=rng, quality=res, work_dir=job["paths"]["work"],
              lights_on=tod in ("evening", "night"))
    loc_id = spec["scene"].get("location", "study_desk")
    try:
        mod = importlib.import_module(f"rsmb.locations.{loc_id}")
    except ModuleNotFoundError:
        log("warning", message=f"Location {loc_id} not found, using study_desk")
        mod = importlib.import_module("rsmb.locations.study_desk")
    from rsmb.locations import common as loc_common
    loc_common.PLACED_PRINTS.clear()
    built = mod.build(ctx)
    anchors: camera_rig.Anchors = built["anchors"]
    room = built["room"]
    anchors.extra = dict(anchors.extra or {}, room=(tuple(room.min), tuple(room.max)),
                         photos=list(loc_common.PLACED_PRINTS))

    # ---- sky and sun
    tp = world.TIME_PRESETS.get(tod, world.TIME_PRESETS["golden"])
    az, el = 250.0, tp["elev"]
    if ctx.sun_window and tp["elev"] > 0:
        az, el = aim_sun_through(ctx.sun_window, anchors.subject, tp["elev"])
    elif ctx.sun_window:
        az, _ = aim_sun_through(ctx.sun_window, anchors.subject, 10)
    sun, tp = world.setup_sky(tod, spec["scene"].get("weather", "clear"), az, scene)
    if sun is not None:
        # re-aim exactly with the chosen elevation
        a, e = math.radians(az), math.radians(el)
        from mathutils import Vector
        d_from = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
        sun.rotation_quaternion = (-d_from).to_track_quat("-Z", "Y")

    # ---- atmosphere
    shafts = float(spec["scene"].get("light_shafts", 0.4))
    if spec["scene"].get("weather") == "hazy":
        shafts = min(1.0, shafts + 0.2)
    if shafts > 0.01 and res.get("volumetrics", True):
        world.add_haze(room.min, room.max, density=0.05 * shafts ** 1.5, anisotropy=0.6, col=col)
    dust = float(spec["scene"].get("dust", 0.5))
    if dust > 0.01:
        mn, mx = built["dust_box"]
        world.add_dust_motes(mn, mx, int(5000 * dust), seed=int(spec["scene"].get("seed", 7)), col=col)

    # ---- camera body + lens
    cam_spec = spec["camera"]
    body = job["body"]
    lens_def = job["lens"]
    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    col.objects.link(cam)
    scene.camera = cam
    sw, sh = job["sensor_mm"]
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = sw
    cam_data.sensor_height = sh
    cam_data.lens = float(cam_spec["focal_mm"])
    cam_data.clip_start = 0.005
    cam_data.clip_end = 200.0
    character = float(spec["look"].get("lens_character", 1.0))
    ca_scale = float(spec["look"].get("chromatic_aberration", 1.0))
    from rsmb.shots import ZOOM_MOVES
    zoomable = cam_spec["move"] in ZOOM_MOVES or (cam_spec["move"] == "macro_cut" and cam_spec.get("cut_to") in ZOOM_MOVES)
    src = lens.build_osl(lens_def, float(cam_spec["focal_mm"]), character, ca_scale, zoomable=zoomable)
    lens.apply_lens(cam_data, src, job["paths"]["work"])
    aspect = res["width"] / res["height"]
    camera_rig.animate_camera(cam, cam_spec, anchors, float(res["fps"]), int(res["frame_start"]),
                              int(res["frame_end"]), (sw, sh), float(job["framing_fill"]),
                              int(spec["scene"].get("seed", 7)) * 13 + 5, aspect)

    render.configure(res, cam_spec, body, scene)
    res["exposure_stops"] = float(tp.get("exposure", 0.0))
    scene.cycles.film_exposure = 2 ** (tp.get("exposure", 0.0))
    device = render.enable_gpu(spec["output"].get("device", "auto"))
    log("device", device=device)
    if device.startswith("GPU:") and ":OPTIX:" not in device + ":":
        # OSL custom cameras need the CPU or OptiX; elsewhere use Blender's own lens with matching settings
        cam_data.type = "PERSP"
        cam_data.dof.aperture_blades = int(lens_def.get("blades", 9)) if lens_def.get("blade_curvature", 1) < 0.95 else 0
        cam_data.dof.aperture_ratio = float(lens_def.get("squeeze", 1.0))
        if zoomable and cam_data.animation_data and cam_data.animation_data.action:
            # the zoom track lived on aperture_ratio for the custom lens; move it to the focal length
            from rsmb.camera_rig import _fcurves
            focal = float(cam_spec["focal_mm"])
            for fc in list(_fcurves(cam_data.animation_data.action)):
                if fc.data_path == "dof.aperture_ratio":
                    for kp in fc.keyframe_points:
                        cam_data.lens = focal * kp.co.y
                        cam_data.keyframe_insert("lens", frame=kp.co.x)
                    fc.keyframe_points.clear()
            cam_data.dof.aperture_ratio = float(lens_def.get("squeeze", 1.0))
        log("warning", message="This graphics card can't run the ray-traced lens model (it needs NVIDIA OptiX or "
                               "the CPU). Rendering with Blender's standard lens instead.")
    return scene


def load_exr(path: str) -> np.ndarray:
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    buf = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(buf)
    bpy.data.images.remove(img)
    return buf.reshape(h, w, 4)[::-1, :, :3].copy()


def develop_frames(job: dict, frames: list[int]):
    res = job["resolved"]
    params = job["filmlab"]
    exr_dir = job["paths"]["exr"]
    png_dir = job["paths"]["frames"]
    os.makedirs(png_dir, exist_ok=True)
    lab = None
    for i, f in enumerate(frames):
        src = os.path.join(exr_dir, f"frame_{f:05d}.exr")
        if not os.path.exists(src):
            continue
        dst = os.path.join(png_dir, f"frame_{f:05d}.png")
        lin = load_exr(src)
        if lab is None:
            lab = filmlab.FilmLab(params, lin.shape[0], lin.shape[1], seed=int(job["spec"]["scene"].get("seed", 7)))
        out = lab.process(lin, f - int(res["frame_start"]), float(res["fps"]))
        filmlab.write_png16(dst, out)
        log("frame_developed", frame=f, index=i, total=len(frames), path=dst)


def main():
    args = parse_args()
    with open(args.job, "r", encoding="utf-8") as fh:
        job = json.load(fh)
    res = job["resolved"]
    fs, fe = int(res["frame_start"]), int(res["frame_end"])
    if args.regrade:
        develop_frames(job, list(range(fs, fe + 1)))
        log("done")
        return
    t0 = time.time()
    scene = build_scene(job)
    log("scene_built", seconds=round(time.time() - t0, 1), objects=len(bpy.data.objects))
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
    if args.still is not None:
        f = fs + int(round(args.still * (fe - fs)))
        scene.frame_set(f)
        if args.crop:
            x0, y0, x1, y1 = (float(v) for v in args.crop.split(","))
            scene.render.use_border = True
            scene.render.use_crop_to_border = True
            # Blender's border origin is bottom-left
            scene.render.border_min_x, scene.render.border_max_x = x0, x1
            scene.render.border_min_y, scene.render.border_max_y = 1 - y1, 1 - y0
        exr = args.still_out + ".exr" if args.still_out else os.path.join(job["paths"]["work"], "still.exr")
        scene.render.filepath = exr
        bpy.ops.render.render(write_still=True)
        lin = load_exr(exr)
        lab = filmlab.FilmLab(job["filmlab"], lin.shape[0], lin.shape[1], seed=int(job["spec"]["scene"].get("seed", 7)))
        out = lab.process(lin, f - fs, float(res["fps"]))
        png = (args.still_out or os.path.join(job["paths"]["work"], "still")) + ".png"
        filmlab.write_png8(png, out)
        log("still_done", path=png, frame=f)
        return
    only = [int(x) for x in args.frames.split(",")] if args.frames else None
    frames = only or list(range(fs, fe + 1))
    exr_dir = job["paths"]["exr"]
    # render and develop as we go so the app can show finished frames early
    os.makedirs(exr_dir, exist_ok=True)
    total = len(frames)
    t_start = time.time()
    lab = None
    for i, f in enumerate(frames):
        exr = os.path.join(exr_dir, f"frame_{f:05d}.exr")
        png = os.path.join(job["paths"]["frames"], f"frame_{f:05d}.png")
        if os.path.exists(png) and os.path.getsize(png) > 0:
            log("frame_skip", frame=f, index=i, total=total)
            continue
        if not (os.path.exists(exr) and os.path.getsize(exr) > 0):
            scene.frame_set(f)
            scene.render.filepath = exr
            log("frame_start", frame=f, index=i, total=total)
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            log("frame_rendered", frame=f, index=i, total=total, seconds=round(time.time() - t0, 2),
                elapsed=round(time.time() - t_start, 1))
        lin = load_exr(exr)
        if lab is None:
            lab = filmlab.FilmLab(job["filmlab"], lin.shape[0], lin.shape[1],
                                  seed=int(job["spec"]["scene"].get("seed", 7)))
        os.makedirs(job["paths"]["frames"], exist_ok=True)
        filmlab.write_png16(png, lab.process(lin, f - fs, float(res["fps"])))
        log("frame_done", frame=f, index=i, total=total, path=png, elapsed=round(time.time() - t_start, 1))
    log("render_done", total=total, seconds=round(time.time() - t_start, 1))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # report to the app, then fail
        log("error", message=str(exc), trace=traceback.format_exc())
        sys.exit(1)
