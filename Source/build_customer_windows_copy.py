#!/usr/bin/env python3
"""
Build Windows Customer Copy — compiled .exe, no Python source.

Output:  ../Customer Windows Copy/
  Phone Reseller CRM/          (folder with Phone Reseller CRM.exe + libs)
  FolderPicker.exe
  START HERE.txt

Vendor: keep generate_key.py in Source only — never ship it.

Usage (from Source folder on Windows):
  python build_customer_windows_copy.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "Customer Windows Copy"

SOURCE_NAMES = {
    "app.py", "database.py", "license_guard.py", "folder_picker.py",
    "launch_crm.py", "backup_service.py", "email_service.py", "generate_key.py",
    "build_release.py", "build_customer_copy.py", "build_customer_windows_copy.py",
    "run_crm.sh", "test_crm.py", "test_crm_performance.py",
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
        env={**os.environ, "CRM_BUILD_PLATFORM": "win"},
    )


def write_start_here(out: Path) -> None:
    (out / "START HERE.txt").write_text(
        """Phone Reseller CRM — Customer Edition v2.2 (Windows)
=====================================================

NO Python or source code — everything is inside the app folder.

HOW TO START
────────────
  1. Double-click:  Phone Reseller CRM\\Phone Reseller CRM.exe
  2. Browser opens at http://localhost:5050
  3. If it does not open, wait 10 seconds and visit http://localhost:5050

TROUBLESHOOTING
───────────────
  • Check Data\\crm.log next to the app folder for errors
  • Your data lives in Data\\crm.db and Data\\Backups\\
  • Use Settings → Close CRM instead of closing from Task Manager

FIRST TIME
──────────
  • Activation: copy Hardware ID → get key from vendor → Activate
  • Sign up with username, password & email
  • Settings → Shop Details (one place for name, address, WhatsApp)
  • Data folder is created automatically next to the app (outside the exe folder)
  • Your live database: Data\\crm.db
  • Auto backups: Data\\Backups\\username_crm_backup_DATE.db
  • Open the same folder as "Phone Reseller CRM" to see Data\\Backups

FEATURES (v2.2)
───────────────
  • Total costing shown when adding phones or expenses
  • Faster, more reliable app startup
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
    for path in out.iterdir():
        if path.suffix == ".py" and path.name in SOURCE_NAMES:
            raise RuntimeError(f"Source file must not be shipped: {path}")


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit(
            "Windows customer builds must run on Windows.\n"
            "On this machine, use GitHub Actions or run on a Windows PC:\n"
            "  cd Source\n"
            "  python build_customer_windows_copy.py"
        )

    ensure_pyinstaller()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    print("Building Phone Reseller CRM ...")
    run_build("PhoneResellerCRM-win.spec")

    app_src = ROOT / "dist" / "Phone Reseller CRM"
    if not app_src.is_dir():
        raise FileNotFoundError(f"Expected app folder at {app_src}")

    shutil.copytree(app_src, OUT / "Phone Reseller CRM")

    print("Building FolderPicker ...")
    run_build("FolderPicker.spec")
    picker_src = ROOT / "dist" / "FolderPicker.exe"
    if not picker_src.is_file():
        raise FileNotFoundError(f"Expected FolderPicker.exe at {picker_src}")
    shutil.copy2(picker_src, OUT / "FolderPicker.exe")

    write_start_here(OUT)
    (OUT / "license.json").write_text("{}\n", encoding="utf-8")
    verify_no_source(OUT)

    print(f"\nOK Customer Windows Copy ready:\n  {OUT}\n")


if __name__ == "__main__":
    main()
