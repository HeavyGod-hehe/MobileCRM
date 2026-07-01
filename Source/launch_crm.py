#!/usr/bin/env python3
"""Start the CRM web server and open the default browser."""

from __future__ import annotations

import atexit
import os
import socket
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import crm_instance
from app_paths import customer_data_dir, customer_install_dir

DEFAULT_PORT = int(os.environ.get("CRM_PORT", "5050"))
HOST = crm_instance.HOST


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


def open_browser_when_ready(host: str, port: int) -> None:
    url = f"http://{host}:{port}"
    for _ in range(40):
        time.sleep(0.5)
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            continue
    crm_instance.open_browser(url)


def main() -> None:
    root = _project_root()
    os.chdir(root)
    _log(f"Starting CRM from {root}")

    if crm_instance.focus_existing_instance(_log):
        return

    port = find_free_port(DEFAULT_PORT)
    os.environ["CRM_PORT"] = str(port)
    url = f"http://{HOST}:{port}"

    crm_instance.write_instance(port)
    atexit.register(crm_instance.clear_instance)

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
        crm_instance.clear_instance()
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
