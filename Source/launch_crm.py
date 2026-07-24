#!/usr/bin/env python3
"""Start the CRM web server and open the default browser."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
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
    """Return the port if a CRM server is already listening.

    Any HTTP response counts as "found" — including error statuses like the
    403 this endpoint returns before activation — since that still proves
    our server is bound to the port. Only treat a real connection failure
    (nothing listening there) as "not found" and keep scanning.
    """
    for port in range(start, start + max_attempts):
        url = f"http://{host}:{port}/api/auth/status"
        try:
            urllib.request.urlopen(url, timeout=0.4)
            return port
        except urllib.error.HTTPError:
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
    """Open the CRM in a maximized, borderless "app" window (no tabs or
    address bar) if Chrome/Edge is available, otherwise fall back to a
    normal browser window (whatever the OS default is)."""
    if os.environ.get("CRM_OPEN_MAXIMIZED", "1") != "0":
        browser_path = _find_chromium_browser()
        if browser_path:
            try:
                subprocess.Popen([browser_path, f"--app={url}", "--start-maximized"])
                return
            except OSError:
                pass
    webbrowser.open(url)


def open_browser_when_ready(host: str, port: int) -> None:
    """Wait until the CRM server is actually answering HTTP requests before
    opening the browser - not just until the OS accepts a TCP handshake on
    the port.

    The previous version used a raw socket.create_connection() as its
    readiness check. On Windows, the OS can accept a TCP connection on a
    listening socket slightly before the WSGI app behind it (Flask/Werkzeug)
    is actually ready to handle a request - e.g. while run_startup_backups()
    is still finishing on a fresh install, or under antivirus-induced disk
    slowness right after a customer's very first launch. That race would
    open the browser to a "connection refused"/blank page a moment too
    early, which looked to a customer exactly like the app "getting stuck".
    Matches find_running_crm()'s already-correct pattern in this same file:
    an actual HTTP GET, where even an error response (e.g. the 403 the
    activation gate returns pre-license) still proves the app itself is
    live and serving, not just that a socket is open.
    """
    status_url = f"http://{host}:{port}/api/auth/status"
    for _ in range(40):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(status_url, timeout=0.5)
            break
        except urllib.error.HTTPError:
            break
        except (OSError, urllib.error.URLError, ValueError):
            continue
    open_maximized(f"http://{host}:{port}")


def _spawn_detached_server(port: int) -> None:
    """Start the actual CRM server as a fully detached background process.

    On macOS, Finder/Launch Services tracks any process launched via the
    .app bundle as "the app" and, on a second double-click, tries to
    re-activate that same process instead of starting a new one — but this
    app has no window to activate, so that reopen silently fails (error
    -600) and nothing happens. Spawning the real server via a plain
    subprocess (not through the bundle) keeps it invisible to Launch
    Services, so every double-click of the .app always gets a fresh,
    short-lived launcher that either starts the server or, if one's
    already running, just reopens the browser.
    """
    env = {**os.environ, "CRM_SERVER_ROLE": "1", "CRM_PORT": str(port)}
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve())]

    kwargs: dict = {
        "cwd": str(_project_root()),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(cmd, **kwargs)


def _run_server(port: int) -> None:
    os.environ["CRM_PORT"] = str(port)

    import backup_service

    backup_service.run_startup_backups()
    backup_service.start_auto_backup_thread()

    from app import app

    _log(f"Server ready at http://{HOST}:{port}")
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        _log(
            f"WARNING: CRM_HOST={HOST} is a non-loopback address -- this app "
            "has no CSRF protection and was built for localhost-only use. "
            "Anyone who can reach this address on the network can use the "
            "CRM as if they were logged in. Only do this on a trusted network."
        )
    app.run(host=HOST, port=port, debug=False, use_reloader=False, threaded=True)


def _ensure_std_streams() -> None:
    """The customer build is windowed (no console), so sys.stdout/stderr
    are None in the frozen exe — there's no console for them to point at.
    That's normally harmless, EXCEPT Werkzeug's dev server (used by
    app.run() below) writes a log line to stderr for every single request
    it handles, even with debug=False. Writing to a None stream raises
    AttributeError, which was crashing the whole server the moment the
    first request came in. Give it a real file to write to instead, so
    the app survives and any of this output is still inspectable."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    target = None
    try:
        data_dir = customer_data_dir()
        if data_dir:
            data_dir.mkdir(parents=True, exist_ok=True)
            target = open(data_dir / "crm-console.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        target = None
    if target is None:
        target = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = target
    if sys.stderr is None:
        sys.stderr = target


def main() -> None:
    _ensure_std_streams()
    root = _project_root()
    os.chdir(root)

    if os.environ.get("CRM_SERVER_ROLE") == "1":
        port = int(os.environ.get("CRM_PORT", DEFAULT_PORT))
        _log(f"Starting CRM server (detached) from {root}")
        _run_server(port)
        return

    _log(f"Starting CRM launcher from {root}")

    existing_port = find_running_crm()
    if existing_port is not None:
        url = f"http://{HOST}:{existing_port}"
        _log(f"CRM already running at {url} — opening browser")
        open_maximized(url)
        return

    port = find_free_port(DEFAULT_PORT)
    _spawn_detached_server(port)
    open_browser_when_ready(HOST, port)
    _log(f"Launcher handed off to detached server on port {port}, exiting")


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
