# -*- mode: python ; coding: utf-8 -*-
# Build with:  pyinstaller packaging/oneclick.spec --noconfirm
# Windows -> dist/ProjectStarter.exe (single file)    macOS -> dist/ProjectStarter.app

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # SPECPATH is provided by PyInstaller
sys.path.insert(0, str(ROOT / "src"))
from oneclick import APP_NAME, __version__  # noqa: E402

NAME = "ProjectStarter"
IS_MAC = sys.platform == "darwin"
icon_file = ROOT / "packaging" / "icons" / ("ProjectStarter.icns" if IS_MAC else "ProjectStarter.ico")
ICON = str(icon_file) if icon_file.exists() and sys.platform in ("win32", "darwin") else None

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[(str(ROOT / "src" / "oneclick" / "builtin_templates"), "oneclick/builtin_templates")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_MAC:
    # macOS: a folder-based app bundle (PyInstaller's recommended layout for .app).
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, icon=ICON, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=ICON,
        bundle_identifier="com.kal-motion.projectstarter",  # change if you register your own identifier
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=NAME,
        console=False,
        icon=ICON,
        upx=False,
    )
