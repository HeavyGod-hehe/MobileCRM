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
    """Folder containing the actual running .exe/binary — on Mac this is
    *inside* the .app bundle (Contents/MacOS/), unlike customer_install_dir()
    above which deliberately steps back out to the folder the customer sees."""
    return Path(sys.executable).resolve().parent


def customer_data_dir() -> Path | None:
    """The Data/ folder next to the installed app (database, backups, logs).
    Returns None when running from source (not a frozen PyInstaller build),
    since dev runs use a different, repo-local data path instead."""
    if not getattr(sys, "frozen", False):
        return None
    return customer_install_dir() / "Data"


def path_is_inside_app_bundle(path: str | Path) -> bool:
    """True if `path` lives inside the Mac .app bundle or (when frozen) the
    Windows install folder. Used to stop the customer from picking a backup
    destination that would vanish on the next app update/reinstall."""
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
