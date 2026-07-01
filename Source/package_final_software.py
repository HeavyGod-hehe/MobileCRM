#!/usr/bin/env python3
"""Package full Version007 source for ~/Downloads/Final Software (build on Mac locally)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path.home() / "Downloads" / "Final Software"
REPO_OUT = OUT / "MobileCRM"

# Copy these top-level repo items (full source tree, no pre-built Mac .app).
INCLUDE_ITEMS = (
    "Source",
    "README.md",
    "README.txt",
    "CUSTOMER_COPIES.md",
    ".gitignore",
)

IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "build", "dist")


def package() -> Path:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    REPO_OUT.mkdir(parents=True)

    for name in INCLUDE_ITEMS:
        src = ROOT / name
        if src.exists():
            dest = REPO_OUT / name
            if src.is_dir():
                shutil.copytree(src, dest, ignore=IGNORE)
            else:
                shutil.copy2(src, dest)

    # Double-clickable Mac builder at the Final Software root.
    builder_src = ROOT / "Source" / "BUILD ON MAC.command"
    builder_dest = OUT / "BUILD ON MAC.command"
    shutil.copy2(builder_src, builder_dest)
    builder_dest.chmod(0o755)

    (OUT / "README.txt").write_text(
        """Phone Reseller CRM — Final Software (Mac)
===========================================

WHAT IS IN THIS FOLDER
----------------------
  MobileCRM/          Full Version007 source code from GitHub
  BUILD ON MAC.command   Double-click to build the Mac app locally

HOW TO BUILD ON YOUR MACBOOK
----------------------------
  1. Put this whole "Final Software" folder in:
       ~/Downloads/Final Software

  2. Double-click:
       BUILD ON MAC.command

  3. Wait for the build to finish (a few minutes).

  4. Open:
       Phone Reseller CRM (Mac Universal)/Phone Reseller CRM.app

WHY BUILD LOCALLY?
------------------
  macOS often blocks downloaded apps as "damaged" if they were built
  on another computer. Building on your own Mac fixes that.

IF macOS STILL BLOCKS THE APP
-----------------------------
  Open Terminal in the app folder and run:
    xattr -cr "Phone Reseller CRM.app"
    codesign --force --deep --sign - "Phone Reseller CRM.app"

  Then right-click the app → Open → Open.

BROWSER TIP
-----------
  Closed the browser? Double-click the app again to reopen CRM.
""",
        encoding="utf-8",
    )

    print(f"Packaged to: {OUT}")
    return OUT


def make_zip(zip_path: Path | None = None) -> Path:
    package()
    zip_path = zip_path or Path("/tmp/Phone-Reseller-CRM-Source-v2.3.zip")
    if zip_path.exists():
        zip_path.unlink()
    subprocess.run(
        ["zip", "-r", "-y", str(zip_path), "."],
        cwd=str(OUT),
        check=True,
    )
    print(f"Zip ready: {zip_path}")
    return zip_path


if __name__ == "__main__":
    make_zip()
