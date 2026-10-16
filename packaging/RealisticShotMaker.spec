# PyInstaller spec: builds dist/RealisticShotMaker/RealisticShotMaker.exe (one-folder build).
# Run from the repository root:  pyinstaller packaging/RealisticShotMaker.spec
import os
from PyInstaller.utils.hooks import collect_data_files

root = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [
    (os.path.join(root, "rsm", "assets"), os.path.join("rsm", "assets")),
    # the Blender-side scripts run inside Blender, so they ship as plain files
    (os.path.join(root, "rsm_blender"), "rsm_blender"),
    (os.path.join(root, "tools", "bpy_shim.py"), "tools"),
]
datas += collect_data_files("imageio_ffmpeg")

a = Analysis(
    [os.path.join(root, "packaging", "launcher.py")],
    pathex=[root],
    datas=datas,
    hiddenimports=["rsm.gui.app", "rsm.cli"],
    excludes=["tkinter", "matplotlib", "scipy", "bpy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="RealisticShotMaker",
    console=False,
    icon=os.path.join(root, "packaging", "icon.ico") if os.path.exists(os.path.join(root, "packaging", "icon.ico")) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RealisticShotMaker")
