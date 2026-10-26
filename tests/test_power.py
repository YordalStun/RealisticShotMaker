import sys

from rsm import power


def test_keep_awake_follows_the_queue(tmp_path, monkeypatch):
    calls = []

    class K32:
        def SetThreadExecutionState(self, flags):
            calls.append(flags)
            return 1

    class Windll:
        kernel32 = K32()
    import ctypes
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", Windll(), raising=False)
    monkeypatch.setattr(power, "_awake", False)
    assert power.keep_awake(True) and power.is_kept_awake()
    assert calls[-1] & power.ES_SYSTEM_REQUIRED and calls[-1] & power.ES_CONTINUOUS
    power.keep_awake(True)                     # no repeat calls while already awake
    assert len(calls) == 1
    assert power.keep_awake(False) and not power.is_kept_awake()
    assert calls[-1] == power.ES_CONTINUOUS    # sleep allowed again
