#!/usr/bin/env python3
"""Start the CRM web server and open the default browser."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from app_paths import customer_install_dir

DEFAULT_PORT = int(os.environ.get("CRM_PORT", "5050"))
HOST = os.environ.get("CRM_HOST", "127.0.0.1")


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return customer_install_dir()
    return Path(__file__).resolve().parent


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
    for _ in range(30):
        time.sleep(0.5)
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            continue
    webbrowser.open(url)


def main() -> None:
    root = _project_root()
    os.chdir(root)

    port = find_free_port(DEFAULT_PORT)
    os.environ["CRM_PORT"] = str(port)
    url = f"http://{HOST}:{port}"

    print("Phone Reseller CRM")
    print(f"  Server: {url}")
    print("  Press Ctrl+C to stop.\n")

    threading.Thread(target=open_browser_when_ready, args=(HOST, port), daemon=True).start()

    import backup_service
    backup_service.run_startup_backups()
    backup_service.start_auto_backup_thread()

    from app import app

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
