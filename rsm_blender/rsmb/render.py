"""Cycles configuration, GPU selection and the frame-by-frame render loop."""
from __future__ import annotations

import json
import os
import sys
import time

import bpy


def log(kind: str, **data):
    """Machine-readable progress line for the app (one JSON object per line)."""
    data["kind"] = kind
    sys.stdout.write("RSM " + json.dumps(data) + "\n")
    sys.stdout.flush()


def enable_gpu(preference: str = "auto") -> str:
    """Enable the best available GPU backend. Returns the device used ('GPU:OPTIX', 'CPU', ...)."""
    scene = bpy.context.scene
    if preference == "cpu":
        scene.cycles.device = "CPU"
        return "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        scene.cycles.device = "CPU"
        return "CPU"
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        try:
            prefs.refresh_devices()
        except AttributeError:
            prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == backend  # GPU only: mixing in the CPU slows big frames down
            scene.cycles.device = "GPU"
            return f"GPU:{backend}:" + ",".join(d.name for d in gpus)
    scene.cycles.device = "CPU"
    return "CPU"


def configure(resolved: dict, cam_spec: dict, body: dict, scene=None):
    scene = scene or bpy.context.scene
    r = scene.render
    c = scene.cycles
    r.engine = "CYCLES"
    r.resolution_x = int(resolved["width"])
    r.resolution_y = int(resolved["height"])
    r.resolution_percentage = 100
    r.pixel_aspect_x = r.pixel_aspect_y = 1.0
    fps = float(resolved["fps"])
    if abs(fps - round(fps)) > 0.001:   # 23.976 / 29.97
        r.fps = int(round(fps))
        r.fps_base = round(fps) / fps
    else:
        r.fps = int(round(fps))
        r.fps_base = 1.0
    scene.frame_start = int(resolved["frame_start"])
    scene.frame_end = int(resolved["frame_end"])

    c.samples = int(resolved["samples"])
    c.use_adaptive_sampling = True
    c.adaptive_threshold = float(resolved["noise_threshold"])
    c.adaptive_min_samples = max(16, int(resolved["samples"]) // 32)
    c.time_limit = 0
    c.use_denoising = True
    try:
        c.denoiser = "OPENIMAGEDENOISE"
        c.denoising_input_passes = "RGB_ALBEDO_NORMAL"
        c.denoising_prefilter = "ACCURATE"
        c.denoising_quality = "HIGH"
        c.denoising_use_gpu = True
    except (TypeError, AttributeError):
        pass
    bounces = int(resolved["max_bounces"])
    c.max_bounces = bounces
    c.diffuse_bounces = min(bounces, 8)
    c.glossy_bounces = min(bounces, 8)
    c.transmission_bounces = bounces
    c.volume_bounces = 2
    c.transparent_max_bounces = 32
    c.sample_clamp_direct = 0.0
    c.sample_clamp_indirect = 12.0
    c.blur_glossy = 0.4
    c.caustics_reflective = False
    c.caustics_refractive = True
    c.volume_step_rate = float(resolved.get("volume_step_rate", 1.0))
    c.volume_preview_step_rate = 4.0
    c.volume_max_steps = 512
    c.use_light_tree = True
    c.pixel_filter_type = "BLACKMAN_HARRIS"
    c.filter_width = 1.5
    c.seed = 0
    c.use_animated_seed = True   # noise pattern changes per frame, like real grain
    try:
        c.use_guiding = False    # path guiding is CPU only; keep GPU and CPU renders consistent
    except AttributeError:
        pass
    # motion blur from the shutter angle
    angle = float(cam_spec.get("shutter_angle", 180.0))
    r.use_motion_blur = angle > 0.5
    r.motion_blur_shutter = angle / 360.0
    r.motion_blur_position = "CENTER"
    rs = float(body.get("rolling_shutter", 0.0))
    try:
        c.rolling_shutter_type = "TOP" if rs > 0.001 else "NONE"
        c.rolling_shutter_duration = min(1.0, rs)
    except (TypeError, AttributeError):
        pass
    # persistent data: keep the BVH between frames
    r.use_persistent_data = True
    c.use_auto_tile = True
    c.tile_size = 2048
    # linear scene-referred output; the film lab does the look afterwards
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.display_settings.display_device = "sRGB"
    c.film_exposure = 2 ** float(resolved.get("exposure_stops", 0.0))
    r.film_transparent = False
    im = r.image_settings
    im.file_format = "OPEN_EXR"
    im.color_depth = "16"
    im.exr_codec = "DWAA" if hasattr(im, "exr_codec") else im.exr_codec
    try:
        im.exr_codec = "ZIP"
    except TypeError:
        pass
    im.color_mode = "RGB"


def configure_eevee(resolved: dict, scene=None) -> bool:
    """Switch to EEVEE for fast drafts: rasterised, with screen-space reflections and bounce light standing in
    for real ray tracing. Returns False if this Blender has no EEVEE (the draft then stays on Cycles)."""
    scene = scene or bpy.context.scene
    r = scene.render
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            r.engine = eng
            break
        except TypeError:
            continue
    else:
        return False
    e = scene.eevee

    def set_(attr, val):
        try:
            setattr(e, attr, val)
        except (AttributeError, TypeError):
            pass
    set_("taa_render_samples", max(8, int(resolved["samples"])))
    set_("use_shadows", True)
    set_("shadow_ray_count", 1)
    set_("shadow_step_count", 4)
    set_("use_raytracing", True)            # screen-space only: reflections and refraction through glass
    set_("ray_tracing_method", "SCREEN")
    set_("use_fast_gi", True)               # approximate bounce light from what's on screen
    set_("fast_gi_method", "GLOBAL_ILLUMINATION")
    set_("use_volumetric_shadows", True)
    set_("volumetric_tile_size", "8")
    set_("volumetric_samples", 48)
    set_("use_gtao", True)
    set_("motion_blur_steps", 1)
    for mat in bpy.data.materials:            # let glass show what's behind it rather than the sky
        for attr in ("use_raytrace_refraction", "use_screen_refraction"):
            try:
                setattr(mat, attr, True)
            except AttributeError:
                pass
    for ob in bpy.data.objects:               # window portals are a Cycles idea; EEVEE would light them up
        if ob.type == "LIGHT" and getattr(ob.data.cycles, "is_portal", False):
            ob.hide_render = True
    return True


def render_frames(frames_dir: str, frame_start: int, frame_end: int, only: list[int] | None = None,
                  overwrite: bool = False):
    """Render one EXR per frame into frames_dir/frame_#####.exr. Existing frames are skipped (resume)."""
    scene = bpy.context.scene
    os.makedirs(frames_dir, exist_ok=True)
    todo = only if only else list(range(frame_start, frame_end + 1))
    total = len(todo)
    t_start = time.time()
    done = 0
    for i, f in enumerate(todo):
        path = os.path.join(frames_dir, f"frame_{f:05d}.exr")
        if os.path.exists(path) and not overwrite and os.path.getsize(path) > 0:
            done += 1
            log("frame_skip", frame=f, index=i, total=total)
            continue
        t0 = time.time()
        scene.frame_set(f)
        scene.render.filepath = path
        log("frame_start", frame=f, index=i, total=total)
        bpy.ops.render.render(write_still=True)
        done += 1
        dt = time.time() - t0
        elapsed = time.time() - t_start
        log("frame_done", frame=f, index=i, total=total, seconds=round(dt, 2), elapsed=round(elapsed, 1), path=path)
    log("render_done", total=total, seconds=round(time.time() - t_start, 1))
