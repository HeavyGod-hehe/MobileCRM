#!/usr/bin/env python3
"""Build the vendor-only Serial Key Generator .exe (Windows).

Output: ../Serial Key Generator/Serial Key Generator.exe

NEVER ship this exe to a customer — see generate_key.py's own warning.
Bakes the same CRM_LICENSE_SECRET used for the customer CRM build into
this tool too, so keys it issues are signed with the real active secret
instead of silently falling back to the hardcoded default (see
SerialKeyGenerator.spec for why that distinction matters).

Usage (from Source folder, same secret as the CRM release build):
  $env:CRM_LICENSE_SECRET = "..."
  python build_key_generator.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "Serial Key Generator"


def _write_license_secret_file() -> None:
    secret = os.environ.get("CRM_LICENSE_SECRET", "").strip()
    if not secret:
        raise SystemExit(
            "CRM_LICENSE_SECRET is not set — refusing to build a key "
            "generator that would silently sign with the hardcoded fallback "
            "secret instead of the real one. Set it to the SAME value used "
            "for build_customer_windows_copy.py."
        )
    (ROOT / "license_build_secret.txt").write_text(secret, encoding="utf-8")


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Build this on Windows (matches the customer build target).")

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    _write_license_secret_file()
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "SerialKeyGenerator.spec"],
            cwd=str(ROOT),
            check=True,
        )
        exe_src = ROOT / "dist" / "Serial Key Generator.exe"
        if not exe_src.is_file():
            raise FileNotFoundError(f"Expected exe at {exe_src}")

        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir(parents=True)
        shutil.copy2(exe_src, OUT / "Serial Key Generator.exe")

        (OUT / "READ ME.txt").write_text(
            """Serial Key Generator — Vendor Tool
===================================

VENDOR ONLY. Never send this exe to a customer — it can mint activation
keys. Keep it on your own computer only.

HOW TO USE
----------
Double-click "Serial Key Generator.exe". It's a console tool:
  1 - Generate a key for THIS computer (for your own testing)
  2 - Generate a key for a CUSTOMER's Hardware ID (paste what they send you)
  Q - Quit

Every key you generate is logged to issued_keys.log next to this exe, so
you always have a record of who has what.
""",
            encoding="utf-8",
        )
    finally:
        secret_file = ROOT / "license_build_secret.txt"
        if secret_file.is_file():
            secret_file.unlink()

    print(f"\nOK Serial Key Generator ready:\n  {OUT}\n")


if __name__ == "__main__":
    main()
