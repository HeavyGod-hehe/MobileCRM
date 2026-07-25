#!/usr/bin/env python3
"""
Build Windows Customer Copy — compiled .exe, no Python source.

Output:  ../Customer Windows Copy/
  Phone Reseller CRM/          (folder with Phone Reseller CRM.exe + libs)
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
    """Install PyInstaller into this Python environment if it's missing, so
    the build never fails just because a fresh machine hasn't set it up yet."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )


def _write_license_secret_file() -> None:
    """Bake CRM_LICENSE_SECRET (the CI/repo secret) into a small text file
    the .spec bundles alongside the frozen app, so it actually reaches the
    customer's machine — see license_guard._build_baked_secret() for why a
    plain env var set only during this build step would otherwise have zero
    effect at runtime on the customer's own machine. Refuses to build at all
    if the secret isn't set, so a missing CI secret fails loudly here
    instead of silently shipping every customer the hardcoded fallback
    secret (the exact bug this exists to close). Never prints the value."""
    secret = os.environ.get("CRM_LICENSE_SECRET", "").strip()
    if not secret:
        raise SystemExit(
            "CRM_LICENSE_SECRET is not set in the environment — refusing to "
            "build a customer release without it. Set it as a CI/repo "
            "secret (see HOW_TO_RELEASE.md) before building."
        )
    (ROOT / "license_build_secret.txt").write_text(secret, encoding="utf-8")


def run_build(spec: str) -> None:
    """Run PyInstaller against the app's .spec file."""
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec],
        cwd=str(ROOT),
        check=True,
        env={**os.environ, "CRM_BUILD_PLATFORM": "win"},
    )


def write_start_here(out: Path) -> None:
    """Drop a plain-English README into the customer's copy — this is often
    the very first thing a non-technical shop owner opens, so it explains
    how to launch the app and where to look if something goes wrong, without
    assuming any Python/dev knowledge."""
    (out / "START HERE.txt").write_text(
        """Phone Reseller CRM — Customer Edition v2.3 (Windows)
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

FEATURES (v2.3)
───────────────
  • Inventory, cash book & accounts stay synced — delete anywhere, updates everywhere
  • Borrow phones from other shopkeepers (payable on shopkeeper account)
  • Accounts: Credit & Debit (expenses like Food deduct from cash or bank)
  • Purchase/sale udhar linked to supplier & buyer accounts
  • Dual IMEI, bulk sell profit, expense edit/delete
  • Today — sold same-day phones count in bought today
  • Billing, Month Report, Returns
  • Restore from backup in Settings

OTHER PLATFORMS
───────────────
  • Mac M1/M2/M3/M4  → Customer Copy Apple Silicon folder
  • Mac Intel        → Customer Copy Intel Mac folder
  • Windows          → this folder (Customer Windows Copy)

Support: contact your CRM vendor.
""",
        encoding="utf-8",
    )


def verify_no_source(out: Path) -> None:
    """Safety check run at the end of every build: fail loudly if any raw
    .py source file ended up in the customer folder. This matters most for
    generate_key.py (the vendor-only key generator) — it must never reach a
    customer's machine, since that would let them mint their own activation
    keys."""
    for path in out.iterdir():
        if path.suffix == ".py" and path.name in SOURCE_NAMES:
            raise RuntimeError(f"Source file must not be shipped: {path}")


def main() -> None:
    """Full Windows customer-build pipeline: compile the app with
    PyInstaller, assemble it into OUT alongside a README and a blank
    license.json, then verify no source code leaked into the output.

    Phase 3 distribution pass: no longer builds/ships FolderPicker.exe as a
    separate customer-visible file. It was already dead code on Windows in
    practice — app.py's browse_folder_api()/browse_backup_file_api() take
    the `sys.platform in ("darwin", "win32")` branch first, which calls
    folder_picker.pick_folder_windows() (ctypes SHBrowseForFolder) directly
    in-process; the subprocess-spawn-a-separate-exe branch below it can only
    ever be reached by a frozen Linux build, which doesn't exist for this
    app. folder_picker.py itself is unchanged and still bundled as Python
    source inside the main app (see PhoneResellerCRM-win.spec's datas) for
    that in-process path — only the redundant standalone .exe build/copy
    step is removed."""
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

    _write_license_secret_file()
    try:
        print("Building Phone Reseller CRM ...")
        run_build("PhoneResellerCRM-win.spec")

        app_src = ROOT / "dist" / "Phone Reseller CRM"
        if not app_src.is_dir():
            raise FileNotFoundError(f"Expected app folder at {app_src}")

        shutil.copytree(app_src, OUT / "Phone Reseller CRM")

        write_start_here(OUT)
        (OUT / "license.json").write_text("{}\n", encoding="utf-8")
        verify_no_source(OUT)
    finally:
        # Never leave the plaintext secret lying around in the source tree
        # once the build (successful or not) is done.
        secret_file = ROOT / "license_build_secret.txt"
        if secret_file.is_file():
            secret_file.unlink()

    print(f"\nOK Customer Windows Copy ready:\n  {OUT}\n")


if __name__ == "__main__":
    main()
