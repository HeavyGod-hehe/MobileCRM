#!/usr/bin/env python3
"""Native OS folder picker — tkinter on all platforms, runs in its own process."""

from __future__ import annotations

import sys


def pick_folder_macos() -> str | None:
    """Native macOS folder dialog via AppleScript (works from Flask subprocess)."""
    import subprocess

    script = 'POSIX path of (choose folder with prompt "Select backup folder")'
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
        raise RuntimeError(err or "macOS folder picker failed")
    path = (result.stdout or "").strip()
    return path or None


def pick_folder_tkinter() -> str | None:
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


def main() -> None:
    path = None
    if sys.platform == "darwin":
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
