#!/usr/bin/env python3
"""
Build macOS Customer Copy — compiled .app, no Python source.

Output:  ~/Downloads/cursor-panga/Customer Copy/
  Phone Reseller CRM.app
  FolderPicker
  START HERE.txt

Vendor: keep generate_key.py in Source only — never ship it.

Usage (from Source folder):
  python3 build_customer_copy.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "Customer Copy"

SOURCE_NAMES = {
    "app.py", "database.py", "license_guard.py", "folder_picker.py",
    "launch_crm.py", "backup_service.py", "email_service.py", "generate_key.py",
    "build_release.py", "build_customer_copy.py", "run_crm.sh",
    "test_crm.py", "test_crm_performance.py",
}


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )


def run_build(spec: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec],
        cwd=str(ROOT),
        check=True,
        env={**os.environ, "CRM_BUILD_PLATFORM": "mac"},
    )


def write_start_here(out: Path) -> None:
    (out / "START HERE.txt").write_text(
        """Phone Reseller CRM — Customer Edition v2.1 (Mac)
================================================

NO Python or source code — everything is inside the app.

HOW TO START
────────────
  1. Double-click:  Phone Reseller CRM.app
  2. Browser opens at http://localhost:5050

FIRST TIME
──────────
  • Activation: copy Hardware ID → get key from vendor → Activate
  • Sign up with username, password & email
  • Settings → Shop Details (one place for name, address, WhatsApp)
  • Data folder is created automatically next to the app (outside the .app file)
  • Your live database: Data/crm.db
  • Auto backups: Data/Backups/username_crm_backup_DATE.db
  • Open the same folder as Phone Reseller CRM.app to see Data/Backups

FEATURES (v2.1)
───────────────
  • Today — daily sales & cash at a glance
  • Billing — print invoice + WhatsApp receipt
  • Help — where to put cash, udhar, bank entries
  • Month Report — print sales & profit summary
  • Restore from backup in Settings

Support: contact your CRM vendor.
""",
        encoding="utf-8",
    )


def verify_no_source(out: Path) -> None:
    for path in out.rglob("*.py"):
        if path.name in SOURCE_NAMES:
            raise RuntimeError(f"Source file must not be shipped: {path}")


def main() -> None:
    ensure_pyinstaller()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    print("Building Phone Reseller CRM.app …")
    run_build("PhoneResellerCRM-mac.spec")

    app_src = ROOT / "dist" / "Phone Reseller CRM.app"
    if not app_src.is_dir():
        raise FileNotFoundError(f"Expected app at {app_src}")

    shutil.copytree(app_src, OUT / "Phone Reseller CRM.app")

    print("Building FolderPicker …")
    run_build("FolderPicker.spec")
    picker_src = ROOT / "dist" / "FolderPicker"
    if picker_src.is_file():
        macos = OUT / "Phone Reseller CRM.app" / "Contents" / "MacOS"
        shutil.copy2(picker_src, macos / "FolderPicker")
        (macos / "FolderPicker").chmod(0o755)
        shutil.copy2(picker_src, OUT / "FolderPicker")
        (OUT / "FolderPicker").chmod(0o755)

    write_start_here(OUT)
    (OUT / "license.json").write_text("{}\n", encoding="utf-8")
    verify_no_source(OUT)

    print(f"\n✓ Customer Copy ready:\n  {OUT}\n")


if __name__ == "__main__":
    main()
