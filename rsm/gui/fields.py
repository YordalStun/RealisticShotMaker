"""Declarative description of every setting shown in the app."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import catalog
from ..polaroid.handwriting import HANDS


@dataclass
class Field:
    path: str                 # "polaroid.scratches"
    label: str
    kind: str                 # combo | slider | spin | dspin | check | text | photo | color
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, label) for combos
    minimum: float = 0.0
    maximum: float = 1.0
    step: float = 0.01
    suffix: str = ""
    tip: str = ""
    group: str = ""


def _opts(table) -> list[tuple[str, str]]:
    out = []
    for k, v in table.items():
        out.append((k, catalog.option_name(table, k)))
    return out


SECTIONS: dict[str, list[Field]] = {
    "Scene": [
        Field("scene.location", "Location", "combo", _opts(catalog.LOCATIONS), group="Where",
              tip="The set your photo sits in. Each location is a fully built, ray-traced room."),
        Field("scene.placement", "Photo placement", "combo", list(catalog.PLACEMENTS.items()), group="Where"),
        Field("scene.time_of_day", "Time of day", "combo", list(catalog.TIMES_OF_DAY.items()), group="Light",
              tip="Sets the sun height and colour. Evening and night switch the lamps on."),
        Field("scene.weather", "Weather", "combo", list(catalog.WEATHER.items()), group="Light"),
        Field("scene.light_shafts", "Light shafts (haze)", "slider", group="Light",
              tip="Haze in the air so sunbeams become visible. Adds render time."),
        Field("scene.dust", "Floating dust", "slider", group="Light",
              tip="Dust specks drifting through the air. They sparkle only where light hits them."),
        Field("scene.clutter", "Props around the photo", "slider", group="Set dressing"),
        Field("scene.extra_photos", "Other photos lying around", "check", group="Set dressing"),
        Field("scene.seed", "Variation", "spin", minimum=1, maximum=99999, step=1, group="Set dressing",
              tip="Change to get a different arrangement of the same set."),
    ],
    "Polaroid": [
        Field("polaroid.photo", "Picture", "photo", [(f"builtin:{k}", v) for k, v in catalog.BUILTIN_PHOTOS.items()],
              group="Picture", tip="Pick a sample or load your own photo (JPG, PNG, …)."),
        Field("polaroid.photo_zoom", "Zoom into picture", "slider", minimum=1.0, maximum=3.0, group="Picture"),
        Field("polaroid.photo_offset_x", "Pan left/right", "slider", minimum=-1.0, maximum=1.0, group="Picture"),
        Field("polaroid.photo_offset_y", "Pan up/down", "slider", minimum=-1.0, maximum=1.0, group="Picture"),
        Field("polaroid.film", "Film type", "combo", _opts(catalog.FILM_TYPES), group="Print"),
        Field("polaroid.frame_color", "Frame colour", "combo", [(k, v[0]) for k, v in catalog.FRAME_COLORS.items()],
              group="Print"),
        Field("polaroid.gloss", "Gloss", "slider", group="Print"),
        Field("polaroid.caption", "Handwritten caption", "text", group="Caption"),
        Field("polaroid.caption_hand", "Handwriting", "combo", [(k, v[0]) for k, v in HANDS.items()], group="Caption"),
        Field("polaroid.caption_pen", "Pen", "combo", list(catalog.CAPTION_PENS.items()), group="Caption"),
        Field("polaroid.caption_color", "Ink colour", "color", group="Caption"),
        Field("polaroid.condition", "Condition preset", "combo", [(k, v["name"]) for k, v in catalog.CONDITIONS.items()],
              group="Age and damage", tip="Sets all the sliders below at once. Then fine-tune."),
        Field("polaroid.age_years", "Age", "slider", minimum=0, maximum=60, step=1, suffix=" years", group="Age and damage"),
        Field("polaroid.fade", "Fading", "slider", group="Age and damage"),
        Field("polaroid.color_cast", "Colour shift", "combo", list(catalog.COLOR_CASTS.items()), group="Age and damage"),
        Field("polaroid.yellowing", "Yellowed border", "slider", group="Age and damage"),
        Field("polaroid.sun_damage", "Sun bleaching", "slider", group="Age and damage"),
        Field("polaroid.chemical_edge", "Developer marks at the edge", "slider", group="Age and damage"),
        Field("polaroid.scratches", "Scratches", "slider", group="Wear"),
        Field("polaroid.fingerprints", "Fingerprints", "slider", group="Wear"),
        Field("polaroid.dust", "Dust and lint", "slider", group="Wear"),
        Field("polaroid.corner_wear", "Worn corners and edges", "slider", group="Wear"),
        Field("polaroid.stains", "Coffee and water stains", "slider", group="Wear"),
        Field("polaroid.creases", "Creases", "slider", group="Physical damage"),
        Field("polaroid.dog_ear", "Folded corner", "slider", group="Physical damage"),
        Field("polaroid.curl", "Curl", "slider", group="Physical damage"),
        Field("polaroid.tape", "Old sticky tape", "check", group="Physical damage"),
        Field("polaroid.pin_hole", "Pin hole", "check", group="Physical damage"),
        Field("polaroid.seed", "Damage variation", "spin", minimum=1, maximum=999999, step=1, group="Physical damage",
              tip="Change to get a different pattern of the same damage."),
    ],
    "Camera": [
        Field("camera.move", "Camera move", "combo", _opts(catalog.MOVES), group="Move"),
        Field("camera.duration", "Length", "dspin", minimum=2, maximum=60, step=0.5, suffix=" s", group="Move"),
        Field("camera.cut_at", "Cut happens at", "slider", minimum=0.1, maximum=0.9, group="Close-up cut",
              tip="Only for “Extreme close-up, then cut wider”: how far into the shot the cut comes."),
        Field("camera.cut_to", "After the cut", "combo",
              [(k, v.name) for k, v in catalog.MOVES.items() if k != "macro_cut"], group="Close-up cut",
              tip="The camera move used for the wider part after the cut."),
        Field("camera.macro_fill", "Close-up magnification", "slider", minimum=2.0, maximum=8.0, step=0.1,
              suffix="×", group="Close-up cut", tip="How far into the picture the opening close-up goes."),
        Field("camera.move_amount", "Move distance", "slider", minimum=0.2, maximum=2.0, group="Move"),
        Field("camera.framing", "Framing", "combo", [(k, v[0]) for k, v in catalog.FRAMINGS.items()], group="Move"),
        Field("camera.angle", "Viewpoint angle", "slider", minimum=-45, maximum=45, step=1, suffix="°", group="Move"),
        Field("camera.height", "Camera height", "slider", minimum=-1, maximum=1, group="Move"),
        Field("camera.lens", "Lens", "combo", _opts(catalog.LENSES), group="Lens",
              tip="The optical character: bokeh shape, swirl, fringing and glow are ray traced through a lens model."),
        Field("camera.focal_mm", "Focal length", "combo", [(str(f), f"{f} mm") for f in catalog.FOCAL_LENGTHS], group="Lens"),
        Field("camera.fstop", "Aperture", "combo", [(str(f), f"f/{f:g}") for f in catalog.FSTOPS], group="Lens",
              tip="Lower numbers blur the background more."),
        Field("camera.focus_target", "Focus on", "combo", [("photo", "The photo"), ("auto", "Automatic")], group="Lens"),
        Field("camera.body", "Camera body", "combo", _opts(catalog.BODIES), group="Camera body",
              tip="Sensor size, rolling shutter, grain, gate weave and flicker of different cameras."),
        Field("camera.shutter_angle", "Shutter angle", "slider", minimum=0, maximum=360, step=5, suffix="°",
              group="Camera body", tip="180° is the classic film look. Higher = more motion blur."),
        Field("camera.handheld", "Extra handheld sway", "slider", group="Operator"),
        Field("camera.rig_wobble", "Slider/dolly imperfection", "slider", group="Operator"),
        Field("camera.focus_drift", "Focus puller imperfection", "slider", group="Operator",
              tip="A little lag, overshoot and drift, like a human pulling focus."),
    ],
    "Look": [
        Field("look.grade", "Colour grade", "combo", list(catalog.GRADES.items()), group="Grade"),
        Field("look.exposure", "Exposure", "slider", minimum=-3, maximum=3, step=0.1, suffix=" stops", group="Grade"),
        Field("look.grain", "Grain / noise (-1 = camera default)", "slider", minimum=-1, maximum=1, group="Film"),
        Field("look.halation", "Halation (-1 = camera default)", "slider", minimum=-1, maximum=1, group="Film"),
        Field("look.gate_weave", "Gate weave (-1 = camera default)", "slider", minimum=-1, maximum=1, group="Film"),
        Field("look.flicker", "Flicker (-1 = camera default)", "slider", minimum=-1, maximum=1, group="Film"),
        Field("look.lens_character", "Lens character", "slider", minimum=0, maximum=2, group="Lens effects",
              tip="Scales every optical quirk of the lens. 0 = a perfect lens."),
        Field("look.chromatic_aberration", "Colour fringing", "slider", minimum=0, maximum=3, group="Lens effects"),
        Field("look.bloom", "Glow / diffusion", "slider", group="Lens effects"),
        Field("look.lens_dirt", "Lens dirt", "slider", group="Lens effects"),
        Field("look.vignette", "Extra vignette", "slider", group="Lens effects"),
        Field("look.letterbox", "Letterbox", "combo", [("none", "None"), ("1.85", "1.85:1"), ("2.39", "2.39:1 widescreen")],
              group="Frame"),
    ],
    "Output": [
        Field("output.name", "File name", "text", group="File"),
        Field("output.output_dir", "Save to folder", "folder", group="File"),
        Field("output.resolution", "Resolution", "combo", [(k, v[0]) for k, v in catalog.RESOLUTIONS.items()], group="Video"),
        Field("output.fps", "Frame rate", "combo", [(str(f), f"{f:g} fps") for f in catalog.FRAME_RATES], group="Video"),
        Field("output.codec", "Format", "combo", _opts(catalog.CODECS), group="Video"),
        Field("output.quality", "Render quality", "combo", _opts(catalog.QUALITY), group="Quality",
              tip="More samples = cleaner, more detailed light, and longer renders."),
        Field("output.custom_samples", "Custom samples (0 = preset)", "spin", minimum=0, maximum=65536, step=64,
              group="Quality"),
        Field("output.device", "Render on", "combo", list(catalog.DEVICES.items()), group="Quality"),
        Field("output.keep_frames", "Keep individual frames", "check", group="Quality",
              tip="Keeps the HDR frames so you can regrade without re-rendering."),
    ],
}


def get_attr(spec, path: str) -> Any:
    obj = spec
    for p in path.split("."):
        obj = getattr(obj, p)
    return obj


def set_attr(spec, path: str, value: Any):
    parts = path.split(".")
    obj = spec
    for p in parts[:-1]:
        obj = getattr(obj, p)
    cur = getattr(obj, parts[-1])
    if isinstance(cur, bool):
        value = bool(value)
    elif isinstance(cur, int) and not isinstance(cur, bool):
        value = int(float(value))
    elif isinstance(cur, float):
        value = float(value)
    setattr(obj, parts[-1], value)
