"""Render packs: one .rsmpack file holding a shot's settings and every image it uses, for a render server.

A pack is a zip: shot.rsm.json (the settings, with file paths made relative) plus media/ (the user's own
photos). Built-in photos, fonts and sets are part of the program, so they don't need to travel.
"""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path

from .spec import ShotSpec

EXT = ".rsmpack"
FORMAT = 1


def _file_fields(spec: ShotSpec):
    """(object, attribute) pairs that hold paths to the user's own files."""
    out = []
    if spec.polaroid.photo and not spec.polaroid.photo.startswith("builtin:"):
        out.append((spec.polaroid, "photo"))
    return out


def export_pack(spec: ShotSpec, path: str | Path) -> Path:
    path = Path(path)
    if path.suffix != EXT:
        path = path.with_suffix(EXT)
    s = spec.copy()
    s.output.output_dir = ""          # the server decides where renders go
    media = []
    for i, (obj, attr) in enumerate(_file_fields(s)):
        src = Path(getattr(obj, attr))
        if not src.exists():
            raise FileNotFoundError(f"The photo {src} can't be found, so it can't go in the pack.")
        name = f"media/{i:02d}_{src.name}"
        media.append((src, name))
        setattr(obj, attr, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", json.dumps({"format": FORMAT, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                            "name": s.output.name}))
        z.writestr("shot.rsm.json", json.dumps(s.to_dict(), indent=1))
        for src, name in media:
            z.write(src, name)
    return path


def import_pack(path: str | Path, dest: str | Path) -> ShotSpec:
    """Unpack into dest (a folder of its own) and return the shot with paths pointing at the unpacked files."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("pack.json"))
        if int(meta.get("format", 1)) > FORMAT:
            raise ValueError("This pack was made by a newer version of RealisticShotMaker.")
        for name in z.namelist():
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest.resolve())):   # refuse anything trying to escape the folder
                raise ValueError(f"Bad entry in pack: {name}")
            if name.endswith("/"):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    spec = ShotSpec.from_dict(json.loads((dest / "shot.rsm.json").read_text(encoding="utf-8")))
    for obj, attr in _file_fields(spec):
        setattr(obj, attr, str((dest / getattr(obj, attr)).resolve()))
    return spec
