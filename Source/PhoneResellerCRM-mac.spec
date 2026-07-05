# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — macOS Customer .app (onedir bundle for faster, reliable startup)."""

import os
import platform
from pathlib import Path

ROOT = Path(SPECPATH)
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

_mac_arch = os.environ.get("CRM_MAC_ARCH", "").strip().lower()
TARGET_ARCH = _mac_arch if _mac_arch in ("arm64", "x86_64") else None

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
        "update_service",
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
    name="PhoneResellerCRM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PhoneResellerCRM",
)

if platform.system() == "Darwin":
    app = BUNDLE(
        coll,
        name="Phone Reseller CRM.app",
        icon=None,
        bundle_identifier="com.phonereseller.crm",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleName": "Phone Reseller CRM",
            "CFBundleDisplayName": "Phone Reseller CRM",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "10.13",
            "LSMultipleInstancesProhibited": False,
        },
    )
