# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("matplotlib")
datas += [
    ("pce_app/assets/pce_studio_icon.png", "pce_app/assets"),
    ("pce_app/assets/pce_studio_icon.ico", "pce_app/assets"),
]

a = Analysis(
    ["run_pce_studio.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pyvisa",
        "pyvisa.highlevel",
        "openpyxl",
        "PySide6.support.deprecated",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=1,
)

# Qt 6 on Windows uses the operating-system ICU.  A Poppler installation on
# PATH can otherwise make PyInstaller collect its incompatible ICU 78 DLLs,
# which causes QtCore to fail with WinError 127 in the portable build.
_incompatible_icu = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    binary
    for binary in a.binaries
    if Path(binary[0]).name.lower() not in _incompatible_icu
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="PCEStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="pce_app/assets/pce_studio_icon.ico",
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PCEStudio_portable",
)
