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
    "cat": "The family cat (real photo)",
    "coffee": "Coffee cup (real photo)",
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
class LocOpt:
    """An option that only exists for one location."""
    id: str
    label: str
    kind: str = "check"            # check | combo | slider
    default: object = False
    choices: tuple = ()            # ((value, label), ...) for combos
    tip: str = ""


AUTO_ON_OFF = (("auto", "Automatic (time of day)"), ("on", "On"), ("off", "Off"))


@dataclass(frozen=True)
class Location(Option):
    placements: tuple[str, ...] = ("leaning", "flat", "pile")
    default_time: str = "golden"
    options: tuple = ()
    default_move: str = ""         # multi-photo sets suggest a move that travels between the photos
    multi: bool = False            # built around several photos


LOCATIONS: dict[str, Location] = {l.id: l for l in [
    Location("study_desk", "Study desk by the window",
             "An old wooden writing desk in a family home. Pencil pot, desk lamp, books, a mug and framed "
             "photos, with a sunny window behind.", default_time="golden", options=(
                 LocOpt("desk_lamp", "Desk lamp", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("curtains", "Curtains", "combo", "open", (("open", "Open"), ("half", "Half drawn"))),
                 LocOpt("letters", "Old letters on the desk", "check", True),
                 LocOpt("bookcase", "Bookcase in the background", "check", True),
                 LocOpt("steam", "Steam rising from the mug", "check", False,
                        tip="A wisp of steam from a fresh coffee. Volumetric, adds render time."),
             )),
    Location("kitchen_table", "Kitchen table, morning",
             "A farmhouse kitchen table with a teapot, fruit bowl and linen runner. Soft morning light "
             "through net curtains.", default_time="morning", options=(
                 LocOpt("mess", "Breakfast mess", "combo", "some",
                        (("none", "Clean table"), ("some", "A little (crumbs, a knife)"),
                         ("lots", "Lots (toast, spilt sugar, rings)"))),
                 LocOpt("flowers", "Flowers on the table", "check", True),
                 LocOpt("fruit", "Fruit bowl", "check", True),
                 LocOpt("pendant", "Hanging lamp", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("net_curtains", "Net curtains", "check", True),
             )),
    Location("attic_trunk", "Attic memory trunk",
             "An open wooden trunk in a dusty attic. Old letters and photos, with a beam of light from a "
             "skylight.", default_time="midday", options=(
                 LocOpt("bare_bulb", "Bare light bulb", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("cobwebs", "Cobwebs", "check", True),
                 LocOpt("trunk_fill", "Trunk contents", "combo", "letters",
                        (("letters", "Bundles of letters"), ("photos", "Loose photos"), ("mixed", "Letters and photos"))),
                 LocOpt("dust_sheets", "Dust sheets over furniture", "check", True),
             )),
    Location("bedside_night", "Bedside table at night",
             "A bedside table lit by a warm lamp: alarm clock, glass of water, reading glasses. Moonlight "
             "from the window.", ("leaning", "flat", "pile"), default_time="night", options=(
                 LocOpt("lamp", "Bedside lamp", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("street_lights", "Street lights outside", "check", True),
                 LocOpt("phone", "Phone screen glowing on the table", "check", False),
                 LocOpt("curtains", "Curtains", "combo", "open", (("open", "Open"), ("half", "Half drawn"))),
             )),
    Location("mantelpiece", "Mantelpiece",
             "A living-room mantelpiece with a carriage clock, candles and frames. Fire glow from below.",
             ("leaning",), default_time="evening", options=(
                 LocOpt("fire", "Fire", "combo", "lit", (("lit", "Burning"), ("embers", "Glowing embers"),
                                                        ("out", "Out"))),
                 LocOpt("candles", "Candles", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("christmas", "Christmas decorations", "check", False,
                        tip="Fairy lights, cards and a garland along the mantel."),
             )),
    Location("investigation_board", "Investigation board",
             "A see-through glass incident board covered in photos, marker notes and red string, in a "
             "detective's office at night.", ("pinned",), default_time="night", options=(
                 LocOpt("board", "Board", "combo", "glass", (("glass", "Glass board"), ("cork", "Cork board"))),
                 LocOpt("string", "String between photos", "check", True),
                 LocOpt("string_color", "String colour", "combo", "red",
                        (("red", "Red"), ("yellow", "Yellow"), ("white", "White"))),
                 LocOpt("room_lights", "Office lights", "combo", "off", (("on", "On"), ("off", "Off"))),
                 LocOpt("spotlight", "Spotlight on the photo", "check", True,
                        tip="A hard light that picks out your photo on the board."),
                 LocOpt("monitors", "Computer screens on", "check", True),
                 LocOpt("blinds", "Light through the blinds", "check", True),
                 LocOpt("marker_notes", "Marker writing on the glass", "check", True),
             )),
    Location("photo_line", "Photo line on a brick wall",
             "Photos pegged along twine lines across a painted brick wall, fairy lights woven through them. "
             "Made for several photos: tour along the line or cut between prints.", ("hanging",),
             default_time="evening", default_move="photo_tour", multi=True, options=(
                 LocOpt("fairy_lights", "Fairy lights", "combo", "on", AUTO_ON_OFF),
                 LocOpt("lines", "Lines of photos", "combo", "2", (("1", "One line"), ("2", "Two lines"))),
                 LocOpt("wall", "Wall", "combo", "brick", (("brick", "Painted brick"), ("plaster", "Plaster"))),
                 LocOpt("lamp", "Desk lamp", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("darkroom", "Darkroom (red safelight)", "check", False,
                        tip="Turns the room into a darkroom: no window, developing trays, a red safelight."),
             )),
    Location("photo_spread", "Shoebox of photos on a coffee table",
             "An old shoebox tipped out across a living-room coffee table: overlapping prints, a magnifying "
             "glass, a cup of tea. Sofa, lamp and window behind. Made for several photos.",
             ("flat", "leaning", "pile"), default_time="golden", default_move="photo_tour", multi=True, options=(
                 LocOpt("spread", "How many photos", "combo", "lots",
                        (("some", "A handful"), ("lots", "The whole box"))),
                 LocOpt("shoebox", "The shoebox", "check", True),
                 LocOpt("magnifier", "Magnifying glass", "check", True),
                 LocOpt("tea", "Cup of tea", "check", True),
                 LocOpt("floor_lamp", "Floor lamp", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("curtains", "Curtains", "combo", "open", (("open", "Open"), ("half", "Half drawn"))),
             )),
    Location("photo_album", "Open photo album",
             "A family album open on the dining table, prints held by photo corners with handwritten "
             "captions. A few loose prints beside it. Made for several photos.", ("mounted", "flat"),
             default_time="morning", default_move="photo_montage", multi=True, options=(
                 LocOpt("pages", "Album pages", "combo", "black", (("black", "Black card (white pencil)"),
                                                                  ("cream", "Cream card (ink)"))),
                 LocOpt("cover", "Cover", "combo", "green", (("green", "Green leather"), ("red", "Red leather"),
                                                            ("brown", "Brown leather"))),
                 LocOpt("captions", "Handwritten captions", "check", True),
                 LocOpt("tea", "Cup of tea", "check", True),
                 LocOpt("lamp", "Table lamp", "combo", "auto", AUTO_ON_OFF),
                 LocOpt("net_curtains", "Net curtains", "check", True),
             )),
]}


def location_options(loc_id: str, overrides: dict | None = None) -> dict:
    """Defaults for a location merged with the user's choices."""
    loc = LOCATIONS.get(loc_id)
    out = {o.id: o.default for o in (loc.options if loc else ())}
    for k, v in (overrides or {}).items():
        if k in out:
            out[k] = v
    return out


PLACEMENTS = {
    "pinned": "Pinned to the board",
    "leaning": "Leaning upright",
    "flat": "Lying flat",
    "pile": "On top of a pile of photos",
    "hanging": "Hanging on a line",
    "mounted": "Mounted in the album",
}

TIMES_OF_DAY = {
    "morning": "Morning",
    "midday": "Midday",
    "golden": "Golden hour",
    "evening": "Evening (lamps on)",
    "night": "Night",
}

@dataclass(frozen=True)
class Mood(Option):
    key: float = 0.0       # dark moods: how bright the lit part of the photo sits (linear); the rest falls away
    dark: bool = False     # replaces the daylight with its own lights
    low_key: float = 1.5   # how hard everything below the highlights is pushed towards black (1 = not at all)


MOODS: dict[str, Mood] = {m.id: m for m in [
    Mood("natural", "Natural (time of day)", "Light from the window and the room's own lamps, set by the time "
         "of day."),
    Mood("low_key", "Low key: one hard light", "A single hard light from high on one side. Deep shadows; "
         "everything it doesn't touch falls to black.", 0.55, True, 1.8),
    Mood("noir_blinds", "Noir: light through blinds", "Hard light through venetian blinds throws stripes "
         "across the photo and the room. Classic film noir.", 0.6, True, 1.7),
    Mood("bare_bulb", "Bare bulb, swinging", "A bare bulb on a flex above the photo, swaying slowly so the "
         "shadows move with it.", 0.55, True, 1.8),
    Mood("torch", "Torch in the dark", "Pitch dark. Someone beside the camera searches with a torch; the beam "
         "cuts through the haze and finds the photo.", 0.6, True, 1.9),
    Mood("candle", "Single candle", "Only a candle just out of shot: warm, low and flickering.", 0.45, True, 1.5),
    Mood("tv_glow", "TV glow", "A television in a dark room: cold light that jumps and shifts with the "
         "picture.", 0.4, True, 1.45),
    Mood("neon", "Neon through the window", "Magenta and cyan light from a neon sign outside, buzzing and "
         "dropping out now and then.", 0.45, True, 1.35),
    Mood("police", "Police lights outside", "Red and blue lights flashing through the window in the dark.",
         0.35, True, 1.45),
    Mood("lightning", "Storm with lightning", "Almost dark, then the room flashes white for an instant, twice.",
         0.14, True, 1.3),
    Mood("moonlight", "Cold moonlight", "Hard, blue-white moonlight through the window, nothing else.",
         0.42, True, 1.6),
    Mood("red_room", "Darkroom red", "One deep-red safelight. Everything else is gone.", 0.4, True, 1.45),
]}

WEATHER = {
    "clear": "Clear",
    "hazy": "Hazy",
    "overcast": "Overcast",
}


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Move(Option):
    default_duration: float = 8.0
    group: str = "classic"      # classic | fun | multi


MOVES: dict[str, Move] = {m.id: m for m in [
    Move("push_in", "Slow push-in", "The camera creeps toward the photo. Says: this matters."),
    Move("macro_cut", "Extreme close-up, then cut wider", "Opens deep inside the picture (faces, grain, "
         "scratches), then hard-cuts to a normal shot of the photo in its setting.", 9.0),
    Move("macro_drift", "Extreme close-up drift", "Deep inside the picture (faces, grain, scratches), drifting "
         "slowly across its surface. Use it as one shot in a shot list; 'Close-up magnification' sets how close."),
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
    # several photos
    Move("photo_tour", "Photo tour", "Glides from photo to photo, pausing on each and racking focus as it "
         "travels, and ends on your photo. Best in the multi-photo locations.", 12.0, "multi"),
    Move("photo_montage", "Photo montage", "Hard cuts between several photos, each with its own slow drift, "
         "ending on your photo. A whole sequence in one shot.", 12.0, "multi"),
    # fun
    Move("whip_cut", "Whip-pan cut", "Lingers on another photo, whips away into a blur and lands on yours. The "
         "cut is hidden inside the motion blur.", 7.0, "fun"),
    Move("whip_pan", "Whip pan", "A beat on something nearby, then a fast swish that lands (and settles) on "
         "the photo.", 6.0, "fun"),
    Move("crash_zoom", "Crash zoom", "A sudden, punchy zoom straight into the photo, with a little bounce as "
         "the zoom ring hits its stop.", 5.0, "fun"),
    Move("dolly_zoom", "Dolly zoom (Vertigo)", "The camera backs away while zooming in: the photo stays the "
         "same size while the room stretches behind it.", 8.0, "fun"),
    Move("wipe_reveal", "Wipe reveal", "Slides past something right in front of the lens: a soft dark wipe, "
         "then the photo.", 7.0, "fun"),
    Move("speed_ramp", "Speed ramp", "Rushes in fast, then slows to a crawl on the photo.", 6.0, "fun"),
    Move("roll_reveal", "Roll reveal", "Starts tipped on its side and rolls level as it settles on the photo.",
         7.0, "fun"),
    Move("orbit", "Orbit", "Circles the photo: all the way round when it lies flat, a wide arc when it "
         "stands.", 12.0, "fun"),
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
    "film16": ("16 mm film", 12.52, 7.41),
    "super8": ("Super 8 film", 5.79, 4.01),
}


@dataclass(frozen=True)
class Lens(Option):
    """Optical character, fed to the ray-traced lens shader. All 0..1 unless noted."""
    blades: int = 9
    blade_curvature: float = 0.8   # 0 straight polygon, 1 circular
    blade_rotation: float = 0.0    # degrees
    cat_eye: float = 0.4           # mechanical vignetting: bokeh turns into lemons at the edges
    swirl: float = 0.0             # tangential astigmatism, Petzval swirl
    spherical: float = 0.3         # spherical aberration: glow wide open, bright-rimmed bokeh
    ca_long: float = 0.3           # longitudinal colour: purple/green fringes on out-of-focus edges
    ca_lat: float = 0.2            # lateral colour: red/blue edges towards the corners
    distortion: float = -0.02      # radial distortion k1 (negative = barrel)
    field_curvature: float = 0.1   # corners focus at a different distance
    breathing: float = 0.04        # angle of view change when focusing close
    bokeh_rim: float = 0.2         # soap-bubble edge on bokeh
    onion: float = 0.0             # onion-ring texture inside bokeh (aspherical elements)
    vignette: float = 0.6          # natural cos^4 fall-off
    squeeze: float = 1.0           # anamorphic aperture ratio (oval bokeh)
    flare: float = 0.3             # veiling glare / ghosts in post
    streak: float = 0.0            # horizontal anamorphic flare streaks


LENSES: dict[str, Lens] = {l.id: l for l in [
    Lens("modern_prime", "Modern cinema prime", "Clean and sharp. Round bokeh, very little fringing.",
         blades=11, blade_curvature=1.0, cat_eye=0.25, swirl=0.0, spherical=0.1, ca_long=0.12, ca_lat=0.05,
         distortion=-0.01, field_curvature=0.0, breathing=0.02, bokeh_rim=0.08, vignette=0.45, flare=0.15),
    Lens("vintage_prime", "Vintage 1970s prime", "Soft glow wide open, slightly cat-eyed bokeh with bright "
         "edges and purple fringing. The classic documentary look.",
         blades=6, blade_curvature=0.55, cat_eye=0.6, swirl=0.12, spherical=0.5, ca_long=0.6, ca_lat=0.25,
         distortion=-0.03, field_curvature=0.25, breathing=0.06, bokeh_rim=0.35, onion=0.12, vignette=0.8,
         flare=0.45),
    Lens("swirly_petzval", "Swirly Helios-style", "Strong swirling bokeh around the edges of the frame and "
         "heavy vignetting. Very characterful.",
         blades=8, blade_curvature=0.6, cat_eye=0.85, swirl=0.9, spherical=0.55, ca_long=0.7, ca_lat=0.3,
         distortion=0.015, field_curvature=0.6, breathing=0.05, bokeh_rim=0.5, onion=0.08, vignette=0.95,
         flare=0.5),
    Lens("cinema_soft", "Warm cinema prime", "Gentle, warm rendering with smooth fall-off. Flattering and calm.",
         blades=9, blade_curvature=0.9, cat_eye=0.45, swirl=0.05, spherical=0.3, ca_long=0.3, ca_lat=0.12,
         distortion=-0.015, field_curvature=0.1, breathing=0.03, bokeh_rim=0.15, vignette=0.6, flare=0.3),
    Lens("anamorphic", "Anamorphic", "Oval bokeh, horizontal flare streaks and gentle barrel distortion.",
         blades=10, blade_curvature=0.9, cat_eye=0.5, swirl=0.1, spherical=0.35, ca_long=0.4, ca_lat=0.3,
         distortion=-0.05, field_curvature=0.3, breathing=0.12, bokeh_rim=0.2, vignette=0.7, squeeze=2.0,
         flare=0.5, streak=0.8),
    Lens("macro", "Macro lens", "Built for extreme close-ups. Very clean, but breathes a lot when focusing.",
         blades=9, blade_curvature=0.8, cat_eye=0.2, swirl=0.0, spherical=0.1, ca_long=0.2, ca_lat=0.05,
         distortion=0.0, field_curvature=0.0, breathing=0.25, bokeh_rim=0.1, vignette=0.4, flare=0.15),
]}


@dataclass(frozen=True)
class Body(Option):
    sensor: str = "super35"
    rolling_shutter: float = 0.0   # fraction of a frame the readout takes
    grain: float = 0.3             # film grain / sensor noise amount
    digital_noise: bool = False    # sensor noise (chroma + pattern) instead of film grain
    gate_weave: float = 0.0
    flicker: float = 0.0
    halation: float = 0.3


BODIES: dict[str, Body] = {b.id: b for b in [
    Body("digital_cinema", "Digital cinema camera", "Large clean sensor, fast readout, fine noise.",
         "super35", 0.08, 0.12, True, 0.0, 0.0, 0.1),
    Body("mirrorless", "Mirrorless / DSLR", "Full-frame stills camera shooting video. Visible rolling shutter "
         "on fast movement.", "full_frame", 0.45, 0.12, True, 0.0, 0.0, 0.0),
    Body("film_35", "35 mm motion picture film", "Organic grain, subtle gate weave and red halation.",
         "super35", 0.0, 0.4, False, 0.35, 0.15, 0.5),
    Body("film_16", "16 mm film", "Heavier grain, more weave and flicker. Home-movie documentary feel.",
         "film16", 0.0, 0.75, False, 0.7, 0.4, 0.6),
    Body("super8", "Super 8", "Very grainy, unsteady and warm, like old home movies.",
         "super8", 0.0, 1.0, False, 1.0, 0.7, 0.55),
]}

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
    "p360": ("Draft 640×360", 640, 360),
    "p480": ("480p 854×480", 854, 480),
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
