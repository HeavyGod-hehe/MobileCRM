"""Track the running CRM server so relaunching the app reopens the browser."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

from app_paths import customer_data_dir

HOST = os.environ.get("CRM_HOST", "127.0.0.1")


def instance_path() -> Path | None:
    data_dir = customer_data_dir()
    if not data_dir:
        return None
    return data_dir / "crm.instance"


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def server_responds(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def read_instance() -> tuple[int, int] | None:
    path = instance_path()
    if not path or not path.is_file():
        return None
    try:
        parts = path.read_text(encoding="utf-8").strip().split()
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])
    except (OSError, ValueError):
        return None


def write_instance(port: int) -> None:
    path = instance_path()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()} {port}\n", encoding="utf-8")


def clear_instance() -> None:
    path = instance_path()
    if not path or not path.is_file():
        return
    try:
        current = read_instance()
        if current and current[0] != os.getpid():
            return
        path.unlink()
    except OSError:
        pass


def open_browser(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
        return
    webbrowser.open(url)


def focus_existing_instance(log=None) -> bool:
    """If CRM is already running, open the browser and return True."""
    inst = read_instance()
    if not inst:
        return False

    pid, port = inst
    if not is_process_running(pid):
        clear_instance()
        return False

    if not server_responds(HOST, port):
        clear_instance()
        return False

    url = f"http://{HOST}:{port}"
    if log:
        log(f"CRM already running (pid {pid}); opening browser at {url}")
    open_browser(url)
    return True
