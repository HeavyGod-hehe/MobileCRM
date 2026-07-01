# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — macOS Customer .app bundle (no source code)."""

import platform
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    ['app.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'templates'), 'templates'),
        (str(ROOT / 'static'), 'static'),
        (str(ROOT / 'folder_picker.py'), '.'),
        (str(ROOT / 'VERSION'), '.'),
    ],
    hiddenimports=[
        'werkzeug.security',
        'backup_service',
        'database',
        'license_guard',
        'email_service',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PhoneResellerCRM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if platform.system() == 'Darwin':
    app = BUNDLE(
        exe,
        name='Phone Reseller CRM.app',
        icon=None,
        bundle_identifier='com.phonereseller.crm',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleName': 'Phone Reseller CRM',
            'CFBundleDisplayName': 'Phone Reseller CRM',
            'CFBundleShortVersionString': '2.1.0',
        },
    )
