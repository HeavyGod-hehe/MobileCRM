# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — vendor-only Serial Key Generator.

NEVER ship the resulting exe to a customer — it signs activation keys.
Keep it on the vendor's own machine only, same as generate_key.py.

Bundles license_build_secret.txt (same file build_customer_windows_copy.py
writes from CRM_LICENSE_SECRET) so this tool signs keys with the SAME
secret baked into the customer CRM build — otherwise it would silently
fall back to the hardcoded default secret in license_guard.py and issue
keys that still work (verify_activation_key accepts the fallback as a
legacy secret) but aren't actually protected by the real rotating secret.

Usage: set CRM_LICENSE_SECRET, then run
  python build_key_generator.py
(don't invoke this .spec directly with a bare `pyinstaller` command).
"""

from pathlib import Path

ROOT = Path(SPECPATH)

_license_secret_file = ROOT / "license_build_secret.txt"
if not _license_secret_file.is_file():
    raise SystemExit(
        "license_build_secret.txt is missing — build_key_generator.py writes "
        "it from CRM_LICENSE_SECRET before invoking PyInstaller. Don't run "
        "this .spec directly; use that script."
    )

a = Analysis(
    ["key_generator_app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(_license_secret_file), "."),
    ],
    hiddenimports=[
        "generate_key",
        "license_guard",
        "app_paths",
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
    name="Serial Key Generator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
