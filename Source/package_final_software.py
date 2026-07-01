#!/usr/bin/env python3
"""Package the latest Version007 CRM into ~/Downloads/Final Software."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Source"
OUT = Path.home() / "Downloads" / "Final Software"
UNIVERSAL = ROOT / "Customer Copy Universal Mac"
WINDOWS = ROOT / "Customer Windows Copy - Built"


def package() -> Path:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copytree(SOURCE, OUT / "Source")
    if UNIVERSAL.is_dir():
        shutil.copytree(UNIVERSAL, OUT / "Phone Reseller CRM (Mac Universal)")
    if WINDOWS.is_dir():
        shutil.copytree(WINDOWS, OUT / "Phone Reseller CRM (Windows)")

    (OUT / "README.txt").write_text(
        """Phone Reseller CRM — Final Software Package
=============================================

Mac (Intel + Apple Silicon):
  Open folder: Phone Reseller CRM (Mac Universal)
  Double-click: Phone Reseller CRM.app

Windows:
  Open folder: Phone Reseller CRM (Windows)
  Double-click: Phone Reseller CRM\\Phone Reseller CRM.exe

Browser tip (Mac):
  If you close the browser, double-click the app again to reopen CRM.
  The server keeps running in the background until you use Settings → Close CRM.

Developers:
  Rebuild Mac universal app on macOS:
    cd Source
    python3 build_customer_universal_mac.py
""",
        encoding="utf-8",
    )

    print(f"Packaged to: {OUT}")
    return OUT


if __name__ == "__main__":
    package()
