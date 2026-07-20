#!/usr/bin/env python3
"""Native OS folder picker — tkinter on all platforms, runs in its own process."""

from __future__ import annotations

import sys


def pick_folder_macos() -> str | None:
    """Native macOS folder dialog via AppleScript (works from Flask subprocess)."""
    import subprocess

    script = 'POSIX path of (choose folder with prompt "Select backup folder")'
    return _run_osascript_choose(script)


def pick_file_macos() -> str | None:
    """Native macOS file dialog for .db backup restore."""
    import subprocess

    script = 'POSIX path of (choose file with prompt "Select CRM backup file" of type {"db","public.database"})'
    return _run_osascript_choose(script)


def _run_osascript_choose(script: str) -> str | None:
    """Shared runner behind pick_folder_macos()/pick_file_macos(): runs the
    given AppleScript, and treats the user hitting Cancel as a normal
    "nothing picked" result rather than an error."""
    import subprocess

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        if "User canceled" in err or "User cancelled" in err:
            return None
        if result.returncode == 1 and not (result.stdout or "").strip():
            return None
        raise RuntimeError(err or "macOS picker failed")
    path = (result.stdout or "").strip()
    return path or None


def pick_folder_tkinter() -> str | None:
    """Cross-platform fallback folder dialog (used on Windows/Linux, and as
    a backstop if the macOS-native picker above fails)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title="Select backup folder") or None
    finally:
        root.destroy()


def pick_folder_windows() -> str | None:
    """Native Windows folder dialog via the shell32 SHBrowseForFolder API
    (looks like a normal Windows Explorer picker, unlike the plainer tkinter
    fallback below)."""
    import ctypes
    from ctypes import wintypes

    BIF_RETURNONLYFSDIRS = 0x00000001
    BIF_NEWDIALOGSTYLE = 0x00000040

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", ctypes.c_uint),
            ("lpfn", ctypes.c_void_p),
            ("lParam", ctypes.c_longlong),
            ("iImage", ctypes.c_int),
        ]

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32

    display_name = ctypes.create_unicode_buffer(260)
    bi = BROWSEINFO()
    bi.hwndOwner = 0
    bi.pszDisplayName = display_name
    bi.lpszTitle = "Select backup folder"
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE

    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return None

    path_buf = ctypes.create_unicode_buffer(260)
    if not shell32.SHGetPathFromIDListW(pidl, path_buf):
        ole32.CoTaskMemFree(pidl)
        return None
    ole32.CoTaskMemFree(pidl)
    return path_buf.value or None


def pick_file_tkinter() -> str | None:
    """Cross-platform fallback file dialog for choosing a .db backup to restore."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askopenfilename(
            title="Select CRM backup file",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
        )
        return path or None
    finally:
        root.destroy()


def pick_backup_file() -> str | None:
    """Pick a .db file to restore: try the native macOS dialog first, falling
    back to tkinter everywhere else (or if the native one errors out)."""
    if sys.platform == "darwin":
        try:
            return pick_file_macos()
        except Exception:
            try:
                return pick_file_tkinter()
            except ImportError:
                return None
    try:
        return pick_file_tkinter()
    except ImportError:
        return None


def main() -> None:
    """Entry point when this file is spawned as its own subprocess (see
    app.py's browse_folder_api()) — GUI file/folder pickers can't run inside
    Flask's request thread, so app.py launches this script and reads the
    chosen path back from stdout. Picks the right native dialog for the
    current OS, with a tkinter fallback everywhere."""
    pick_file = "--file" in sys.argv
    path = None
    if pick_file:
        path = pick_backup_file()
    elif sys.platform == "darwin":
        try:
            path = pick_folder_macos()
        except Exception:
            try:
                path = pick_folder_tkinter()
            except ImportError:
                sys.exit(2)
    elif sys.platform == "win32":
        try:
            path = pick_folder_windows()
        except Exception:
            path = pick_folder_tkinter()
    else:
        try:
            path = pick_folder_tkinter()
        except ImportError:
            sys.exit(2)

    if path:
        print(path, flush=True)


if __name__ == "__main__":
    main()
