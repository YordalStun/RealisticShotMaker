# RealisticShotMaker

A Windows program that makes cinematic documentary "insert" shots: an instant
photo on a desk, everything else melting into soft focus, warm window light,
dust in the air, a slow camera move. Every frame is path traced with Blender's
Cycles renderer and rendered out to 4K or 8K video.

## What you get

- **Five fully built sets**: study desk by the window, kitchen table in the
  morning, attic memory trunk, bedside table at night, living-room mantelpiece.
  Each one is a complete room with props, windows, a garden or street outside
  and proper light coming in.
- **Instant prints you control**: Polaroid 600, SX-70, Spectra, Go, Instax
  Mini/Square/Wide. Use your own photo, write a caption in one of six
  handwriting styles, and set how damaged it is: age, fading, colour shift,
  yellowed border, sun bleaching, developer marks, scratches, fingerprints,
  dust, worn corners, coffee and water stains, creases, a folded corner, curl,
  old sticky tape, a pin hole. Creases, curl and folded corners are real
  geometry, not just pictures.
- **15 camera moves**: push-in, pull-out, slides, arcs, tilt-down reveal, rack
  focus in and out, crane down, top-down turn, drift, pan across, handheld and
  locked-off. Moves are eased like a real dolly, with optional slider wobble,
  handheld sway and a human focus puller who lags and overshoots slightly.
- **A ray-traced lens model**: every camera ray goes through a lens with
  aperture blades, cat's-eye bokeh at the edges, swirl, spherical aberration
  (glow wide open, bright-edged bokeh), purple/green colour fringing, lateral
  colour, distortion, field curvature and focus breathing. Choose a lens
  character: modern prime, vintage 70s prime, swirly Helios-style, warm cinema
  prime, anamorphic or macro.
- **Camera bodies**: digital cinema camera, mirrorless (with rolling shutter),
  35 mm film, 16 mm film and Super 8: grain or sensor noise, gate weave,
  flicker, halation, 180° shutter motion blur.
- **Film lab**: AgX tone mapping, colour grades (warm nostalgia, golden memory,
  faded film, cool morning, bleach bypass, black and white), bloom, lens dirt,
  vignette and letterbox. HDR frames are kept, so you can regrade without
  re-rendering.
- **Output**: H.265 10-bit, H.264, ProRes 422 HQ, ProRes 4444, DNxHR HQX, or
  16-bit PNG / OpenEXR image sequences, at 1080p, 1440p, 4K UHD, 4K DCI, 6K,
  8K or vertical 4K, 23.976 to 60 fps.

## Installing

1. Run `RealisticShotMaker-Setup.exe` (built by the GitHub Actions workflow;
   download it from the workflow run's artifacts).
2. Start the program. It looks for **Blender 4.5 or newer**. If it can't find
   it, use **Blender → Download Blender 4.5 LTS** and it fetches the portable
   build from blender.org (about 400 MB) into your user folder.

Your graphics card is used automatically (NVIDIA OptiX first, then CUDA, AMD
HIP or Intel oneAPI). RTX 50-series cards need Blender 4.4 or newer, which is
why 4.5 LTS is the minimum.

## Using it

1. Pick a look from **Quick start**, or go through the tabs on the left:
   *Scene*, *Polaroid*, *Camera*, *Look*, *Output*.
2. Load your own photo in the *Polaroid* tab and set its condition. The print
   preview on the right updates as you go.
3. Press **Preview frame** for a quick render of one moment of the shot (use the
   *Position* slider to choose which).
4. Press **Render video**. The job goes into the queue at the bottom with a
   progress bar and time remaining. Cancelling keeps the finished frames;
   rendering the same job again resumes where it stopped.

Renders are saved under `Videos\RealisticShotMaker\<name>_<date>` unless you
choose another folder: the video, the developed frames, the HDR frames and a
copy of the shot settings (`shot.rsm.json`).

## How long renders take

This is full path tracing with volumetric light, so it is slow on purpose. The
app shows a rough estimate before you start. As a guide for an RTX 5080 with
the default scene settings:

| Quality | Samples | 4K frame | 8K frame |
|---------|--------:|---------:|---------:|
| Preview | 96      | ~10 s    | ~40 s    |
| High    | 512     | ~1 min   | ~4 min   |
| Cinema  | 1536    | ~3 min   | ~12 min  |
| Ultra   | 4096    | ~8 min   | ~30 min  |

An 8-second shot at 24 fps is 192 frames, so a *Cinema* 4K render is roughly
10 hours. Light shafts (haze) and the spectral lens effects add time; turning
**Light shafts** down is the quickest way to speed things up. These figures are
estimates, not measurements on that card.

## Command line

```
RealisticShotMaker.exe render myshot.rsm.json            # render and encode
RealisticShotMaker.exe still myshot.rsm.json --at 0.5    # one preview frame
RealisticShotMaker.exe regrade "path\to\job.json"        # re-run the film lab on kept HDR frames
```

## Building from source

```
pip install -r requirements-dev.txt
python -m rsm                    # start the app
pytest                           # tests
pyinstaller packaging/RealisticShotMaker.spec
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

`tools/bpy_shim.py` lets developers run the Blender side with the `bpy` Python
module instead of a Blender install (set the Blender path to a Python that has
`bpy` installed).

## Project layout

- `rsm/`: the app (spec, presets, print generator, job builder, runner, GUI)
- `rsm_blender/`: scripts that run inside Blender (sets, props, materials,
  lens shader, camera rig, film lab)
- `packaging/`: PyInstaller spec and Inno Setup installer
- `tests/`: unit tests

## Credits

Handwriting fonts (Caveat, Indie Flower, Shadows Into Light, Gochi Hand, Reenie
Beanie, Nothing You Could Do) are under the SIL Open Font License; see
`rsm/assets/fonts`. The two sample photographs are CC0; see
`rsm/assets/photos/LICENSE.txt`. Blender is downloaded separately and is GPL
software from the Blender Foundation.
