"""Ad-hoc sign macOS app bundles so Gatekeeper does not report them as damaged."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def strip_quarantine(path: Path) -> None:
    if sys.platform != "darwin":
        return
    subprocess.run(["xattr", "-cr", str(path)], check=False)


def adhoc_sign_app(app_path: Path) -> None:
    if sys.platform != "darwin":
        return
    if not app_path.is_dir():
        raise FileNotFoundError(f"App bundle not found: {app_path}")

    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
        check=True,
    )
    verify = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)],
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        raise RuntimeError(f"codesign verify failed for {app_path}:\n{verify.stderr}")


def prepare_mac_app(app_path: Path) -> None:
    """Remove quarantine flags and ad-hoc sign a .app bundle."""
    strip_quarantine(app_path)
    adhoc_sign_app(app_path)
    strip_quarantine(app_path)
