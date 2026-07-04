#!/usr/bin/env python3
"""Start the CRM web server and open the default browser."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

from app_paths import customer_data_dir, customer_install_dir

DEFAULT_PORT = int(os.environ.get("CRM_PORT", "5050"))
HOST = os.environ.get("CRM_HOST", "127.0.0.1")


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return customer_install_dir()
    return Path(__file__).resolve().parent


def _log_path() -> Path | None:
    data_dir = customer_data_dir()
    if not data_dir:
        return None
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "crm.log"


def _log(message: str) -> None:
    path = _log_path()
    if not path:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def find_running_crm(host: str = HOST, start: int = DEFAULT_PORT, max_attempts: int = 20) -> int | None:
    """Return the port if a CRM server is already listening."""
    for port in range(start, start + max_attempts):
        url = f"http://{host}:{port}/api/auth/status"
        try:
            with urllib.request.urlopen(url, timeout=0.4) as resp:
                if resp.status == 200:
                    return port
        except (OSError, urllib.error.URLError, ValueError):
            continue
    return None


def find_free_port(start: int, host: str = HOST, max_attempts: int = 20) -> int:
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    return start


def _find_chromium_browser() -> str | None:
    """Locate Chrome or Edge if installed — the only common browsers with a
    reliable "open maximized" command-line flag. There's no cross-browser
    way to force Safari/Firefox to open maximized, so those fall back to a
    normal (unmaximized) window via webbrowser.open()."""
    system = platform.system()
    candidates: list[str] = []
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif system == "Windows":
        program_dirs = [
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
        ]
        rel_paths = [
            r"Google\Chrome\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
        ]
        for base in program_dirs:
            if not base:
                continue
            for rel in rel_paths:
                candidates.append(os.path.join(base, rel))
    for path in candidates:
        if Path(path).is_file():
            return path
    return None


def open_maximized(url: str) -> None:
    """Open the CRM in a maximized browser window if possible, otherwise
    fall back to a normal browser window (whatever the OS default is)."""
    if os.environ.get("CRM_OPEN_MAXIMIZED", "1") != "0":
        browser_path = _find_chromium_browser()
        if browser_path:
            try:
                subprocess.Popen([browser_path, "--new-window", "--start-maximized", url])
                return
            except OSError:
                pass
    webbrowser.open(url)


def open_browser_when_ready(host: str, port: int) -> None:
    url = f"http://{host}:{port}"
    for _ in range(40):
        time.sleep(0.5)
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            continue
    open_maximized(url)


def main() -> None:
    root = _project_root()
    os.chdir(root)
    _log(f"Starting CRM from {root}")

    existing_port = find_running_crm()
    if existing_port is not None:
        url = f"http://{HOST}:{existing_port}"
        _log(f"CRM already running at {url} — opening browser")
        open_maximized(url)
        return

    port = find_free_port(DEFAULT_PORT)
    os.environ["CRM_PORT"] = str(port)
    url = f"http://{HOST}:{port}"

    threading.Thread(target=open_browser_when_ready, args=(HOST, port), daemon=True).start()

    import backup_service

    backup_service.run_startup_backups()
    backup_service.start_auto_backup_thread()

    from app import app

    _log(f"Server ready at {url}")
    app.run(host=HOST, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _log("Startup failed:\n" + traceback.format_exc())
        if getattr(sys, "frozen", False):
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            log_hint = _log_path()
            hint = f"\n\nDetails saved to:\n{log_hint}" if log_hint else ""
            messagebox.showerror(
                "Phone Reseller CRM",
                f"The app could not start.\n\n{exc}{hint}",
            )
            root.destroy()
        raise
