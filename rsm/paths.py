"""Where the program lives and where it keeps its things.

Installed: settings and working files go in %LOCALAPPDATA%\\RealisticShotMaker, renders in Videos.
Portable (a file called portable.txt next to the exe): everything stays in the program's own folder, so the
whole thing runs from a USB stick and leaves nothing behind on the PC.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def install_dir() -> Path:
    """The folder the program runs from (next to RealisticShotMaker.exe when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    return os.environ.get("RSM_PORTABLE") == "1" or (install_dir() / "portable.txt").exists()


def app_data_dir() -> Path:
    if is_portable():
        d = install_dir() / "data"
    else:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        d = Path(base) / "RealisticShotMaker"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_output_dir() -> Path:
    if is_portable():
        return install_dir() / "Renders"
    return Path.home() / "Videos" / "RealisticShotMaker"


def bundled_blender() -> Path | None:
    """Blender shipped inside the all-in-one package."""
    for name in ("blender.exe", "blender"):
        p = install_dir() / "blender" / name
        if p.exists():
            return p
    return None


def settings():
    """QSettings: the registry when installed, an ini file in the program folder when portable."""
    from PySide6.QtCore import QSettings
    if is_portable():
        return QSettings(str(app_data_dir() / "settings.ini"), QSettings.IniFormat)
    return QSettings("RealisticShotMaker", "RealisticShotMaker")
