# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Windows Customer build (onedir for faster, reliable startup)."""

from pathlib import Path

ROOT = Path(SPECPATH)
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

a = Analysis(
    ["launch_crm.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "templates"), "templates"),
        (str(ROOT / "static"), "static"),
        (str(ROOT / "folder_picker.py"), "."),
        (str(ROOT / "VERSION"), "."),
    ],
    hiddenimports=[
        "werkzeug.security",
        "app_paths",
        "app",
        "backup_service",
        "database",
        "license_guard",
        "email_service",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Phone Reseller CRM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version="version_info.txt" if (ROOT / "version_info.txt").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Phone Reseller CRM",
)
