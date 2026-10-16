"""Run rsm_blender/entry.py with the `bpy` Python module instead of a Blender executable.

Developer tool: python tools/bpy_shim.py -- --job job.json [--still 0.5 ...]
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
entry = os.path.join(HERE, "..", "rsm_blender", "entry.py")
sys.argv = ["blender"] + sys.argv[1:]
runpy.run_path(entry, run_name="__main__")
