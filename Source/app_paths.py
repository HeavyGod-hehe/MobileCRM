"""Resolve customer-visible folders outside the macOS .app bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def customer_install_dir() -> Path:
    """Folder where the customer keeps the app (same level as the .app), not inside it."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if exe.parent.name == "MacOS":
            contents = exe.parent.parent
            if contents.name == "Contents" and (contents / "Info.plist").is_file():
                return contents.parent.parent
        return exe.parent
    return Path(__file__).resolve().parent


def executable_dir() -> Path:
    return Path(sys.executable).resolve().parent


def customer_data_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return customer_install_dir() / "Data"


def path_is_inside_app_bundle(path: str | Path) -> bool:
    text = str(path).replace("\\", "/")
    if ".app/Contents/" in text:
        return True
    if not getattr(sys, "frozen", False):
        return False
    try:
        resolved = Path(path).resolve()
        exe_root = executable_dir().resolve()
        return exe_root in resolved.parents or resolved == exe_root
    except OSError:
        return False
