"""Keep the computer awake while it renders.

Windows' sleep timer only counts keyboard and mouse activity, so an overnight render looks like an idle PC
and gets put to sleep mid-shot. While a render runs we tell Windows the system is in use (the screen may
still switch off); when the queue goes idle we hand control back so normal sleep works again.
"""
from __future__ import annotations

import sys

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040   # media-centre style "away mode" where the PC supports it

_awake = False


def keep_awake(on: bool) -> bool:
    """Ask the OS not to sleep (on=True) or allow sleep again (on=False). Call from a long-lived thread (the
    GUI thread): Windows ties the request to the thread that made it. Returns True if the request was made."""
    global _awake
    if on == _awake:
        return True
    if sys.platform != "win32":
        _awake = on
        return False
    try:
        import ctypes
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED if on else 0)
        ok = ctypes.windll.kernel32.SetThreadExecutionState(flags) != 0
        if not ok and on:
            # away mode isn't supported everywhere: the plain request still stops sleep
            ok = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) != 0
    except (AttributeError, OSError):
        return False
    if ok:
        _awake = on
    return ok


def is_kept_awake() -> bool:
    return _awake
