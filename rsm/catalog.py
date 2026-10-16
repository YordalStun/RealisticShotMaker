"""Everything the user can pick from: locations, moves, film types, looks,
render presets. The GUI builds its menus from these tables and the renderer
resolves ids into concrete numbers with them."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Option:
    id: str
    name: str
    description: str = ""


# ---------------------------------------------------------------------------
# Polaroid
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FilmType(Option):
    card_mm: tuple[float, float] = (88.0, 107.0)     # width, height
    image_mm: tuple[float, float] = (79.0, 79.0)
    image_origin_mm: tuple[float, float] = (4.5, 6.0)  # left, top
    chemistry: str = "integral"                       # integral | instax


FILM_TYPES: dict[str, FilmType] = {f.id: f for f in [
    FilmType("600", "Polaroid 600", "The classic square instant photo with the thick bottom border.",
             (88.0, 107.0), (79.0, 79.0), (4.5, 6.0)),
    FilmType("sx70", "Polaroid SX-70", "Same size as the 600, with the softer, dreamier SX-70 chemistry.",
             (88.0, 107.0), (79.0, 79.0), (4.5, 6.0)),
    FilmType("spectra", "Polaroid Spectra", "Wide 1990s Polaroid with a rectangular picture.",
             (102.0, 101.0), (92.0, 73.0), (5.0, 6.0)),
    FilmType("go", "Polaroid Go", "Small modern Polaroid.",
             (54.0, 66.6), (47.0, 46.0), (3.5, 5.0)),
    FilmType("instax_mini", "Instax Mini", "Credit-card sized instant photo.",
             (54.0, 86.0), (46.0, 62.0), (4.0, 6.5), "instax"),
    FilmType("instax_square", "Instax Square", "Square Instax.",
             (72.0, 86.0), (62.0, 62.0), (5.0, 7.0), "instax"),
    FilmType("instax_wide", "Instax Wide", "Landscape Instax.",
             (108.0, 86.0), (99.0, 62.0), (4.5, 6.5), "instax"),
]}

FRAME_COLORS: dict[str, tuple[str, str]] = {
    # id: (display name, hex)
    "classic": ("Classic white", "#f1eee6"),
    "cream": ("Cream", "#ece2cc"),
    "black": ("Black", "#1d1c1b"),
    "sky": ("Sky blue", "#a9c6dc"),
    "coral": ("Coral", "#e59a86"),
    "mint": ("Mint", "#b9dccb"),
}

CAPTION_PENS = {
    "marker": "Felt-tip marker",
    "ballpoint": "Ballpoint pen",
    "pencil": "Pencil",
    "none": "No writing",
}

COLOR_CASTS = {
    "warm": "Warm / orange",
    "magenta": "Magenta",
    "cyan": "Cyan / teal",
    "green": "Green",
    "none": "None",
}

# Condition presets set every damage slider at once.
CONDITIONS: dict[str, dict] = {
    "brand_new": dict(name="Brand new", age_years=0, fade=0.0, yellowing=0.0, scratches=0.0, creases=0.0,
                      corner_wear=0.0, dog_ear=0.0, stains=0.0, fingerprints=0.05, dust=0.05,
                      chemical_edge=0.15, sun_damage=0.0, tape=False, pin_hole=False, curl=0.05,
                      color_cast="none"),
    "album": dict(name="Kept in an album", age_years=18, fade=0.2, yellowing=0.2, scratches=0.08, creases=0.0,
                  corner_wear=0.1, dog_ear=0.0, stains=0.0, fingerprints=0.1, dust=0.15,
                  chemical_edge=0.3, sun_damage=0.0, tape=False, pin_hole=False, curl=0.1,
                  color_cast="warm"),
    "loved": dict(name="Loved and handled", age_years=25, fade=0.35, yellowing=0.35, scratches=0.25,
                  creases=0.0, corner_wear=0.3, dog_ear=0.0, stains=0.0, fingerprints=0.2, dust=0.3,
                  chemical_edge=0.4, sun_damage=0.0, tape=False, pin_hole=False, curl=0.25,
                  color_cast="warm"),
    "shoebox": dict(name="Forgotten in a shoebox", age_years=40, fade=0.55, yellowing=0.6, scratches=0.5,
                    creases=0.15, corner_wear=0.55, dog_ear=0.2, stains=0.15, fingerprints=0.3, dust=0.6,
                    chemical_edge=0.55, sun_damage=0.0, tape=False, pin_hole=False, curl=0.4,
                    color_cast="magenta"),
    "sun_bleached": dict(name="Sun-bleached on a fridge", age_years=30, fade=0.7, yellowing=0.5,
                         scratches=0.2, creases=0.0, corner_wear=0.35, dog_ear=0.0, stains=0.05,
                         fingerprints=0.25, dust=0.3, chemical_edge=0.4, sun_damage=0.75, tape=True,
                         pin_hole=False, curl=0.3, color_cast="cyan"),
    "water_damaged": dict(name="Water damaged", age_years=35, fade=0.5, yellowing=0.55, scratches=0.3,
                          creases=0.1, corner_wear=0.5, dog_ear=0.1, stains=0.85, fingerprints=0.2, dust=0.4,
                          chemical_edge=0.7, sun_damage=0.0, tape=False, pin_hole=False, curl=0.7,
                          color_cast="green"),
    "battered": dict(name="Battered keepsake", age_years=45, fade=0.6, yellowing=0.7, scratches=0.75,
                     creases=0.7, corner_wear=0.8, dog_ear=0.7, stains=0.35, fingerprints=0.4, dust=0.6,
                     chemical_edge=0.6, sun_damage=0.15, tape=True, pin_hole=True, curl=0.55,
                     color_cast="magenta"),
}

BUILTIN_PHOTOS: dict[str, str] = {
    "beach": "Family day at the beach",
    "garden": "Back garden in summer",
    "sunset": "Sunset over a field",
    "birthday": "Birthday candles",
    "snow": "Snowy street",
    "lake": "Lake and mountains",
}


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Location(Option):
    placements: tuple[str, ...] = ("leaning", "flat", "pile")
    default_time: str = "golden"


LOCATIONS: dict[str, Location] = {l.id: l for l in [
    Location("study_desk", "Study desk by the window",
             "An old wooden writing desk in a family home. Pencil pot, desk lamp, books, a mug and framed "
             "photos, with a sunny window behind.", default_time="golden"),
    Location("kitchen_table", "Kitchen table, morning",
             "A farmhouse kitchen table with a teapot, fruit bowl and linen cloth. Soft morning light "
             "through net curtains.", default_time="morning"),
    Location("attic_trunk", "Attic memory trunk",
             "An open wooden trunk in a dusty attic. Old letters and photos, with a beam of light from a "
             "skylight.", default_time="midday"),
    Location("bedside_night", "Bedside table at night",
             "A bedside table lit by a warm lamp: alarm clock, glass of water, reading glasses. Moonlight "
             "from the window.", ("leaning", "flat", "pile"), default_time="night"),
    Location("mantelpiece", "Mantelpiece",
             "A living-room mantelpiece with a carriage clock, candles and frames. Fire glow from below.",
             ("leaning",), default_time="evening"),
]}

PLACEMENTS = {
    "leaning": "Leaning upright",
    "flat": "Lying flat",
    "pile": "On top of a pile of photos",
}

TIMES_OF_DAY = {
    "morning": "Morning",
    "midday": "Midday",
    "golden": "Golden hour",
    "evening": "Evening (lamps on)",
    "night": "Night",
}

WEATHER = {
    "clear": "Clear sun",
    "hazy": "Hazy sun",
    "overcast": "Overcast",
}


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Move(Option):
    default_duration: float = 8.0


MOVES: dict[str, Move] = {m.id: m for m in [
    Move("push_in", "Slow push-in", "The camera creeps toward the photo. Says: this matters."),
    Move("pull_out", "Slow pull-out", "Starts tight on the photo and drifts back to reveal the room.", 9.0),
    Move("slide_right", "Slide right", "Glides sideways to the right. Foreground and background move at "
         "different speeds (parallax)."),
    Move("slide_left", "Slide left", "Glides sideways to the left."),
    Move("arc_right", "Arc right", "Curves around the photo to the right, light shifting across it.", 9.0),
    Move("arc_left", "Arc left", "Curves around the photo to the left.", 9.0),
    Move("tilt_reveal", "Tilt-down reveal", "Starts on the blurred window or room and tilts down onto "
         "the photo."),
    Move("rack_in", "Rack focus to photo", "Camera holds still. Focus pulls from the background to the "
         "photo."),
    Move("rack_out", "Rack focus away", "Focus starts on the photo and pulls to something in the "
         "background."),
    Move("crane_down", "Crane down", "Descends from above the table to eye level with the photo.", 9.0),
    Move("top_down", "Top-down turn", "Looks straight down on the photo while slowly rotating.", 10.0),
    Move("drift", "Gentle drift", "An almost imperceptible float forward and sideways."),
    Move("pan_across", "Pan across", "Pans from a nearby object onto the photo."),
    Move("handheld", "Handheld", "Basically still, with the natural sway of a person holding the camera."),
    Move("locked_off", "Locked-off", "No movement at all. Dust and light provide the life."),
]}

FRAMINGS = {
    # id: (name, fraction of frame height the photo card fills)
    "extreme_close": ("Extreme close-up (the picture itself)", 1.25),
    "close": ("Close-up", 0.62),
    "medium": ("Medium (photo and surroundings)", 0.32),
    "wide": ("Wide (the whole table)", 0.15),
}

SENSORS = {
    # id: (name, sensor width mm, sensor height mm)
    "full_frame": ("Full frame", 36.0, 24.0),
    "super35": ("Super 35", 24.89, 18.66),
}

FOCAL_LENGTHS = [24, 35, 50, 65, 85, 100, 135]
FSTOPS = [1.2, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0]


# ---------------------------------------------------------------------------
# Look
# ---------------------------------------------------------------------------

GRADES = {
    "natural": "Natural",
    "warm_nostalgia": "Warm nostalgia",
    "golden_memory": "Golden memory",
    "faded_film": "Faded film",
    "cool_morning": "Cool morning",
    "bleach_bypass": "Bleach bypass",
    "black_white": "Black and white",
}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

RESOLUTIONS = {
    # id: (name, width, height)
    "preview": ("Preview 960×540", 960, 540),
    "hd1080": ("Full HD 1920×1080", 1920, 1080),
    "qhd1440": ("QHD 2560×1440", 2560, 1440),
    "uhd4k": ("4K UHD 3840×2160", 3840, 2160),
    "dci4k": ("4K DCI 4096×2160", 4096, 2160),
    "uhd6k": ("6K 6144×3456", 6144, 3456),
    "uhd8k": ("8K UHD 7680×4320", 7680, 4320),
    "vertical4k": ("Vertical 4K 2160×3840", 2160, 3840),
}

FRAME_RATES = [23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 60.0]


@dataclass(frozen=True)
class Quality(Option):
    samples: int = 256
    noise_threshold: float = 0.01
    max_bounces: int = 12
    volume_step: float = 0.05


QUALITY: dict[str, Quality] = {q.id: q for q in [
    Quality("draft", "Draft", "Fast check of framing and movement.", 24, 0.08, 6, 0.2),
    Quality("preview", "Preview", "Good enough to judge the look.", 96, 0.03, 8, 0.1),
    Quality("high", "High", "Clean, detailed frames for most uses.", 512, 0.01, 12, 0.05),
    Quality("cinema", "Cinema", "Movie quality. Slow.", 1536, 0.004, 16, 0.03),
    Quality("ultra", "Ultra", "Maximum detail for 8K masters. Very slow.", 4096, 0.002, 24, 0.02),
]}


@dataclass(frozen=True)
class Codec(Option):
    container: str = "mp4"
    ffmpeg_args: tuple[str, ...] = ()
    sequence: bool = False


CODECS: dict[str, Codec] = {c.id: c for c in [
    Codec("h265_10", "H.265 10-bit (MP4)", "Small files, high quality, plays almost everywhere.", "mp4",
          ("-c:v", "libx265", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p10le",
           "-tag:v", "hvc1", "-x265-params", "aq-mode=3:no-sao=1")),
    Codec("h264", "H.264 (MP4)", "Most compatible.", "mp4",
          ("-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-tune", "film",
           "-movflags", "+faststart")),
    Codec("prores_hq", "Apple ProRes 422 HQ (MOV)", "Editing master for Premiere, Resolve, Final Cut.",
          "mov", ("-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-vendor", "apl0")),
    Codec("prores_4444", "Apple ProRes 4444 (MOV)", "Highest quality editing master.", "mov",
          ("-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuv444p10le", "-vendor", "apl0")),
    Codec("dnxhr_hqx", "Avid DNxHR HQX (MOV)", "10-bit editing master.", "mov",
          ("-c:v", "dnxhd", "-profile:v", "dnxhr_hqx", "-pix_fmt", "yuv422p10le")),
    Codec("png_seq", "PNG image sequence (16-bit)", "One lossless image per frame.", "", (), True),
    Codec("exr_seq", "OpenEXR sequence (HDR)", "Linear HDR frames for colour grading.", "", (), True),
]}

DEVICES = {"auto": "Automatic (GPU if available)", "gpu": "Graphics card (GPU)", "cpu": "Processor (CPU)"}


def option_name(table, key: str) -> str:
    v = table.get(key)
    if v is None:
        return key
    if isinstance(v, Option):
        return v.name
    if isinstance(v, tuple):
        return v[0]
    if isinstance(v, dict):
        return v.get("name", key)
    return str(v)
