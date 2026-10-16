import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "rsm_blender"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# keep tests away from the real app data (render queue, drafts, settings)
import tempfile  # noqa: E402
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="rsm_test_")
