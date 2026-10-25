"""Shot specification.

A ShotSpec fully describes one shot: where it happens, what the polaroid
looks like, how the camera moves and how the result is rendered. The GUI edits
a ShotSpec, the renderer serialises it to JSON and the Blender side reads that
JSON back. This module only uses the standard library so it can be imported
anywhere.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SPEC_VERSION = 1


@dataclass
class PolaroidSpec:
    print_type: str = "instant"       # instant (polaroid/instax) | framed (a photo print in a picture frame)
    frame_style: str = "oak"          # see catalog.FRAME_STYLES (framed only)
    frame_size: str = "6x4"           # see catalog.FRAME_SIZES (framed only)
    frame_mat: bool = True            # card mount (passe-partout) around the photo (framed only)
    fit_photo_aspect: bool = False    # reshape the picture window (and the card/frame) to the photo's own shape
    film: str = "600"                 # see catalog.FILM_TYPES
    photo: str = "builtin:beach"      # file path or builtin:<id>
    photo_zoom: float = 1.0           # >1 crops in
    photo_offset_x: float = 0.0       # -1..1 pan when cropping
    photo_offset_y: float = 0.0
    frame_color: str = "classic"      # see catalog.FRAME_COLORS
    caption: str = "Summer '98"
    caption_pen: str = "marker"       # marker | ballpoint | pencil | none
    caption_hand: str = "caveat"      # see polaroid.handwriting.HANDS
    caption_color: str = "#232c5e"
    condition: str = "loved"          # preset id from catalog.CONDITIONS; values below override
    age_years: float = 25.0           # drives yellowing, fading and colour shift
    fade: float = 0.35                # 0..1
    color_cast: str = "warm"          # warm | magenta | cyan | green | none
    yellowing: float = 0.35           # 0..1, border paper turning cream/yellow
    scratches: float = 0.25           # 0..1
    creases: float = 0.0              # 0..1
    corner_wear: float = 0.3          # 0..1 rounded/frayed corners and edge whitening
    dog_ear: float = 0.0              # 0..1 bent corner
    stains: float = 0.0               # 0..1 coffee / water marks
    fingerprints: float = 0.2         # 0..1 oily prints on the gloss
    dust: float = 0.3                 # 0..1 specks and lint on the surface
    chemical_edge: float = 0.4        # 0..1 developer-reagent artefacts at the image edge
    sun_damage: float = 0.0           # 0..1 one side bleached by sunlight
    tape: bool = False                # yellowed sticky tape on the top edge
    pin_hole: bool = False
    curl: float = 0.25                # 0..1 card curl
    gloss: float = 0.7                # 0..1 how shiny the image area is
    seed: int = 1998


@dataclass
class SceneSpec:
    location: str = "study_desk"      # see catalog.LOCATIONS
    placement: str = "leaning"        # leaning | flat | pile
    time_of_day: str = "golden"       # morning | midday | golden | evening | night
    mood: str = "natural"             # lighting mood, see catalog.MOODS (dark moods replace the daylight)
    weather: str = "clear"            # clear | hazy | overcast
    light_shafts: float = 0.45        # 0..1 volumetric haze so sunbeams show
    dust: float = 0.5                 # 0..1 floating dust in the air
    clutter: float = 0.7              # 0..1 how many props around the subject
    extra_photos: bool = True         # other photos lying around
    options: dict = field(default_factory=dict)  # location-specific options, see catalog.LOCATIONS[..].options
    seed: int = 7


@dataclass
class CameraSpec:
    move: str = "push_in"             # see catalog.MOVES
    framing: str = "close"            # see catalog.FRAMINGS
    lens: str = "vintage_prime"       # see catalog.LENSES (optical character)
    body: str = "film_35"             # see catalog.BODIES (sensor/film behaviour)
    focal_mm: float = 85.0
    fstop: float = 2.0
    sensor: str = "auto"              # auto (from body) | full_frame | super35 | ...
    angle: float = 0.0                # degrees, rotates the default viewpoint around the subject
    height: float = 0.0               # -1..1 lower / higher camera
    duration: float = 8.0             # seconds
    move_amount: float = 1.0          # scales how far the move travels
    handheld: float = 0.0             # 0..1 extra handheld sway on top of any move
    rig_wobble: float = 0.25          # 0..1 small imperfections of a real slider/dolly
    aperture_blades: int = 9
    anamorphic: bool = False          # oval bokeh
    shutter_angle: float = 180.0      # motion blur, degrees. 0 disables
    focus_drift: float = 0.3          # 0..1 a human focus puller's small lag, overshoot and drift
    focus_target: str = "photo"       # photo | face (centre of the picture) | auto
    # "macro_cut" move: an extreme close-up inside the picture, then a hard cut to a normal framing
    cut_at: float = 0.4               # 0..1 point in the shot where the cut happens
    cut_to: str = "push_in"           # the move used after the cut
    macro_fill: float = 4.0           # how much bigger than the frame the print is in the close-up
    cut_in_motion: bool = True        # after a cut the camera is already moving (no ramp up from standstill)
    # shot list: with cuts, each shot overrides move/framing/focal_mm/fstop/angle/height/move_amount/macro_fill
    # and has a length in seconds (see rsm/shotlist.py). Empty = one shot made of the settings above.
    shots: list = field(default_factory=list)


@dataclass
class LookSpec:
    grade: str = "warm_nostalgia"     # see catalog.GRADES
    exposure: float = 0.0             # stops
    grain: float = -1.0               # -1 = from camera body, else 0..1
    vignette: float = 0.25            # 0..1 extra vignette on top of the lens' own fall-off
    halation: float = -1.0            # -1 = from camera body, else 0..1 (red glow around highlights)
    chromatic_aberration: float = 1.0  # multiplier on the lens' own colour fringing
    lens_character: float = 1.0       # multiplier on all optical quirks (0 = perfect lens)
    gate_weave: float = -1.0          # -1 = from camera body, else 0..1
    flicker: float = -1.0             # -1 = from camera body, else 0..1
    bloom: float = 0.25               # 0..1 veiling glare / diffusion filter
    lens_dirt: float = 0.2            # 0..1 dust and smudges on the front element
    letterbox: str = "none"           # none | 1.85 | 2.39


@dataclass
class OutputSpec:
    resolution: str = "uhd4k"         # see catalog.RESOLUTIONS
    fps: float = 24.0
    quality: str = "high"             # see catalog.QUALITY
    custom_samples: int = 0           # >0 overrides the quality preset
    codec: str = "h265_10"            # see catalog.CODECS
    device: str = "auto"              # auto | gpu | cpu
    output_dir: str = ""
    name: str = "shot"
    keep_frames: bool = True
    frame_format: str = "png16"       # png16 | exr
    engine: str = "cycles"            # cycles (path traced) | eevee (fast rasterised drafts)


@dataclass
class ShotSpec:
    version: int = SPEC_VERSION
    polaroid: PolaroidSpec = field(default_factory=PolaroidSpec)
    scene: SceneSpec = field(default_factory=SceneSpec)
    camera: CameraSpec = field(default_factory=CameraSpec)
    look: LookSpec = field(default_factory=LookSpec)
    output: OutputSpec = field(default_factory=OutputSpec)

    # ---- serialisation -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShotSpec":
        def build(dc_type, values):
            values = values or {}
            known = {f.name: f for f in dataclasses.fields(dc_type)}
            kwargs = {}
            for name, f in known.items():
                if name not in values:
                    continue
                v = values[name]
                default = getattr(dc_type(), name) if f.default_factory is dataclasses.MISSING else None
                if isinstance(default, bool):
                    v = bool(v)
                elif isinstance(default, int) and not isinstance(default, bool):
                    v = int(v)
                elif isinstance(default, float):
                    v = float(v)
                kwargs[name] = v
            return dc_type(**kwargs)

        return cls(
            version=int(data.get("version", SPEC_VERSION)),
            polaroid=build(PolaroidSpec, data.get("polaroid")),
            scene=build(SceneSpec, data.get("scene")),
            camera=build(CameraSpec, data.get("camera")),
            look=build(LookSpec, data.get("look")),
            output=build(OutputSpec, data.get("output")),
        )

    @classmethod
    def from_json(cls, text: str) -> "ShotSpec":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> "ShotSpec":
        return cls.from_json(Path(path).read_text(encoding="utf-8-sig"))  # tolerate a BOM from Windows editors

    def copy(self) -> "ShotSpec":
        return ShotSpec.from_dict(self.to_dict())
