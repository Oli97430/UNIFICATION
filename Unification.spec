# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for UNIFICATION.

Build:
    pyinstaller --noconfirm Unification.spec

Output:
    dist/Unification.exe   (Windows, single-file, windowed)
    dist/Unification       (Linux/macOS)
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
HERE = Path(SPECPATH).resolve()

datas = [
    (str(HERE / "assets" / "logo.png"), "assets"),
    (str(HERE / "assets" / "logo.ico"), "assets"),
    (str(HERE / "assets" / "logo_32.png"), "assets"),
    (str(HERE / "assets" / "logo_64.png"), "assets"),
    (str(HERE / "assets" / "logo_128.png"), "assets"),
    (str(HERE / "assets" / "blender_mcp_addon.py"), "assets"),
    (str(HERE / "assets" / "freecad_mcp_addon.py"), "assets"),
    (str(HERE / "assets" / "gimp_mcp_addon.py"), "assets"),
    (str(HERE / "assets" / "inkscape_mcp_server.py"), "assets"),
    (str(HERE / "assets" / "photoshop_mcp_server.py"), "assets"),
    (str(HERE / "mcp_server.py"), "."),
]
# customtkinter ships a JSON theme tree it loads at runtime
datas += collect_data_files("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy.testing", "pytest", "tornado"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_path = str(HERE / "assets" / "logo.ico") if sys.platform == "win32" else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Unification",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,         # windowed app — no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
