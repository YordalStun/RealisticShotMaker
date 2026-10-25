"""Shot lists: a camera shot made of several shots with cuts between them, each with its own camera settings.

`spec.camera.shots` holds the shots when there's at least one cut (each a dict of the settings that shot
overrides, plus its length in seconds). With no list, the shot is the camera settings themselves; the older
"close-up, then cut wider" move becomes a two-shot list. `resolve()` turns any of these into the complete,
timed list the renderer follows.
"""
from __future__ import annotations

import copy

from . import catalog
from .spec import ShotSpec

# settings each shot can have its own value for
PER_SHOT = ("move", "framing", "focal_mm", "fstop", "angle", "height", "move_amount", "macro_fill")
MACRO = "macro_drift"


def _from_top(spec: ShotSpec) -> dict:
    c = spec.camera
    return {k: getattr(c, k) for k in PER_SHOT}


def shots_of(spec: ShotSpec) -> list[dict]:
    """The editable shot list (lengths in seconds). Always at least one shot."""
    c = spec.camera
    if len(c.shots) >= 1:
        out = []
        for s in c.shots:
            d = _from_top(spec)
            d.update({k: v for k, v in s.items() if k in PER_SHOT or k == "length"})
            d.setdefault("length", c.duration / len(c.shots))
            out.append(d)
        return out
    if c.move == "macro_cut":
        cut = min(0.9, max(0.1, float(c.cut_at)))
        a = _from_top(spec)
        a.update(move=MACRO, length=c.duration * cut)
        b = _from_top(spec)
        b.update(move=c.cut_to if c.cut_to != "macro_cut" else "push_in", length=c.duration * (1 - cut))
        return [a, b]
    d = _from_top(spec)
    d["length"] = c.duration
    return [d]


def set_shots(spec: ShotSpec, shots: list[dict]):
    """Store an edited shot list back on the spec (and keep the top-level camera fields = the first shot,
    so everything that reads them -- the lens, the estimate, older code -- still sees sensible values)."""
    c = spec.camera
    shots = [dict(s) for s in shots]
    for s in shots:
        s["length"] = max(0.25, float(s.get("length", 1.0)))
    c.duration = round(sum(s["length"] for s in shots), 3)
    if len(shots) <= 1:
        c.shots = []
        if shots:
            for k in PER_SHOT:
                if k in shots[0]:
                    setattr(c, k, shots[0][k])
        if c.move == MACRO and not shots:
            c.move = "push_in"
        return
    c.shots = shots
    first = shots[0]
    for k in PER_SHOT:
        if k in first and k != "move":
            setattr(c, k, first[k])
    c.move = "push_in" if first["move"] in (MACRO, "macro_cut") else first["move"]


def split(shots: list[dict], index: int, at: float = 0.5) -> list[dict]:
    """Cut shot `index` in two at fraction `at` of its length; the new shot starts as a copy."""
    shots = copy.deepcopy(shots)
    s = shots[index]
    total = s["length"]
    a = max(0.25, min(total - 0.25, total * at))
    s["length"] = a
    b = dict(s)
    b["length"] = total - a
    shots.insert(index + 1, b)
    return shots


def remove(shots: list[dict], index: int) -> list[dict]:
    """Remove a shot; its time goes to the neighbour so the total length stays the same."""
    if len(shots) <= 1:
        return shots
    shots = copy.deepcopy(shots)
    gone = shots.pop(index)
    shots[max(0, index - 1) if index > 0 else 0]["length"] += gone["length"]
    return shots


def resolve(spec: ShotSpec) -> list[dict]:
    """Complete, timed shot list for the renderer: every setting filled in, plus t0/t1 (0..1 of the whole
    shot) and the framing fill the shot uses."""
    shots = shots_of(spec)
    total = sum(s["length"] for s in shots) or 1.0
    t = 0.0
    out = []
    for i, s in enumerate(shots):
        d = dict(s)
        d["t0"] = t / total
        t += s["length"]
        d["t1"] = t / total
        if d["move"] == "macro_cut":       # a close-up cut inside a shot list is just the close-up part
            d["move"] = MACRO
        if d["move"] == MACRO:
            d["fill"] = float(d.get("macro_fill", 4.0))
        else:
            d["fill"] = float(catalog.FRAMINGS.get(d.get("framing", "close"), ("", 0.62))[1])
        d["index"] = i
        out.append(d)
    out[-1]["t1"] = 1.0
    return out


def max_fill(spec: ShotSpec) -> float:
    return max(s["fill"] for s in resolve(spec))
