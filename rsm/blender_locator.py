"""Find a usable Blender installation, or download the portable LTS build."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .paths import app_data_dir, bundled_blender  # noqa: F401  (app_data_dir kept here for older imports)

RECOMMENDED = "4.5.4"
MIN_VERSION = (4, 5)  # the custom lens needs Blender 4.5+ (OSL custom cameras)
DOWNLOAD_URL = "https://download.blender.org/release/Blender{major}/blender-{ver}-windows-x64.zip"


def _version_of(exe: str) -> tuple[int, int, int] | None:
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        out = subprocess.run([exe, "-b", "--factory-startup", "--version"], capture_output=True, text=True,
                             timeout=60, creationflags=flags).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"Blender (\d+)\.(\d+)\.?(\d+)?", out)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def candidates() -> list[str]:
    found: list[str] = []
    env = os.environ.get("RSM_BLENDER")
    if env:
        found.append(env)
    own = bundled_blender()          # the all-in-one package carries its own Blender
    if own is not None:
        found.append(str(own))
    found += sorted(glob.glob(str(app_data_dir() / "blender" / "*" / "blender.exe")), reverse=True)
    found += sorted(glob.glob(str(app_data_dir() / "blender" / "*" / "blender")), reverse=True)
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramW6432", r"C:\Program Files")):
            found += sorted(glob.glob(os.path.join(root, "Blender Foundation", "Blender*", "blender.exe")), reverse=True)
        steam = [r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
                 r"C:\Program Files\Steam\steamapps\common\Blender\blender.exe"]
        found += [s for s in steam if os.path.exists(s)]
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Classes\blendfile\shell\open\command") as k:
                        cmd = winreg.QueryValue(k, None)
                        m = re.match(r'"([^"]+blender[^"]*\.exe)"', cmd, re.I)
                        if m:
                            found.append(m.group(1))
                except OSError:
                    pass
        except ImportError:
            pass
    elif sys.platform == "darwin":
        found.append("/Applications/Blender.app/Contents/MacOS/Blender")
    w = shutil.which("blender")
    if w:
        found.append(w)
    seen, out = set(), []
    for f in found:
        if f and f not in seen and os.path.exists(f):
            seen.add(f)
            out.append(f)
    return out


def find_blender() -> tuple[str | None, tuple | None]:
    """Return (path, version) of the newest suitable Blender, or (None, None)."""
    best = (None, None)
    for c in candidates():
        v = _version_of(c)
        if v and v[:2] >= MIN_VERSION and (best[1] is None or v > best[1]):
            best = (c, v)
    return best


def download_blender(on_progress: Callable[[float, str], None] | None = None, version: str = RECOMMENDED) -> str:
    """Download and unpack the portable Windows build into the app data folder. Returns blender.exe."""
    major = ".".join(version.split(".")[:2])
    url = DOWNLOAD_URL.format(major=major, ver=version)
    dest_dir = app_data_dir() / "blender"
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"blender-{version}.zip"

    def report(frac, msg):
        if on_progress:
            on_progress(frac, msg)

    if not zip_path.exists():
        tmp = zip_path.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                report(got / total if total else 0.0, f"Downloading Blender {version}: {got >> 20} MB")
        tmp.rename(zip_path)
    report(1.0, "Unpacking Blender…")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest_dir)
    zip_path.unlink(missing_ok=True)
    exe = sorted(glob.glob(str(dest_dir / f"blender-{version}*" / "blender.exe")))
    if not exe:
        raise RuntimeError("Blender was downloaded but blender.exe was not found in the archive.")
    return exe[-1]
