"""Auto-updater for frozen (PyInstaller) customer builds.

Hosts a version.json manifest (see releases/version.json.example). The app
compares semver, downloads the platform zip, and applies it via a small helper
script after the CRM process exits (required on Windows/macOS).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from app_paths import customer_data_dir, customer_install_dir

# All customer apps check this file for updates (no setup needed per customer).
# Points at a SEPARATE public releases repo, not the private source repo —
# the source repo (and the licensing code in it) never needs to be public
# for the updater to work. See HOW_TO_RELEASE.md.
DEFAULT_MANIFEST_URL = os.environ.get(
    "CRM_UPDATE_MANIFEST_URL",
    "https://raw.githubusercontent.com/HeavyGod-hehe/MobileCRM-releases/main/version.json",
)
LEGACY_VERSION_URL = os.environ.get(
    "CRM_GITHUB_VERSION_URL",
    "https://raw.githubusercontent.com/HeavyGod-hehe/MobileCRM-releases/main/VERSION",
)

_USER_AGENT = "PhoneResellerCRM-Updater/1.0"
_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle | checking | downloading | extracting | applying | restarting | error | done
    "progress": 0,
    "message": "",
    "error": None,
    "remote_version": None,
}


def get_current_version() -> str:
    return _read_local_version()


def _read_local_version() -> str:
    if getattr(sys, "frozen", False):
        ver_path = Path(sys._MEIPASS) / "VERSION"
        if ver_path.is_file():
            return ver_path.read_text(encoding="utf-8").strip()
        return "1.0.0"
    ver_path = Path(__file__).resolve().parent / "VERSION"
    return ver_path.read_text(encoding="utf-8").strip() if ver_path.is_file() else "0.0.0"


def version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in (version or "").strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def is_newer_version(remote: str, current: str) -> bool:
    if not remote:
        return False
    try:
        return version_tuple(remote) > version_tuple(current)
    except (ValueError, TypeError):
        return remote.strip() != current.strip()


def is_frozen_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def platform_key() -> str | None:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            return "mac_arm64"
        return "mac_intel"
    return None


def _http_get_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8").strip()


def _http_get_json(url: str, timeout: int = 12) -> dict[str, Any]:
    text = _http_get_text(url, timeout=timeout)
    return json.loads(text)


def _set_state(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def get_update_state() -> dict[str, Any]:
    with _state_lock:
        return dict(_state)


def _pick_download(manifest: dict[str, Any]) -> dict[str, Any] | None:
    downloads = manifest.get("downloads") or {}
    key = platform_key()
    if not key:
        return None
    if key in downloads:
        return downloads[key]
    if sys.platform == "darwin" and "mac_universal" in downloads:
        return downloads["mac_universal"]
    return None


def fetch_manifest(url: str | None = None) -> dict[str, Any] | None:
    manifest_url = (url or DEFAULT_MANIFEST_URL).strip()
    if not manifest_url:
        return None
    try:
        data = _http_get_json(manifest_url, timeout=4)
        if isinstance(data, dict) and data.get("version"):
            return data
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    return None


def check_for_updates() -> dict[str, Any]:
    current = _read_local_version()
    manifest = fetch_manifest()
    remote_version = None
    release_notes = ""
    page_url = ""
    download = None
    update_available = False

    if manifest:
        remote_version = str(manifest.get("version", "")).strip()
        release_notes = str(manifest.get("release_notes") or manifest.get("notes") or "")
        page_url = str(manifest.get("page_url") or manifest.get("download_hint") or "")
        download = _pick_download(manifest)
        update_available = is_newer_version(remote_version, current)
    else:
        try:
            remote_version = _http_get_text(LEGACY_VERSION_URL, timeout=4)
            update_available = is_newer_version(remote_version, current)
            page_url = "https://github.com/HeavyGod-hehe/MobileCRM/tree/Version007"
        except (urllib.error.URLError, TimeoutError, OSError):
            remote_version = None

    can_auto_install = bool(
        is_frozen_build()
        and update_available
        and download
        and download.get("url")
        and platform_key() is not None
    )

    return {
        "current_version": current,
        "remote_version": remote_version,
        "update_available": update_available,
        "release_notes": release_notes,
        "download_hint": page_url,
        "download_url": (download or {}).get("url"),
        "can_auto_install": can_auto_install,
        "platform": platform_key(),
        "frozen": is_frozen_build(),
    }


def _updates_dir() -> Path:
    data = customer_data_dir()
    if data:
        path = data / "Updates"
    else:
        path = Path(tempfile.gettempdir()) / "PhoneResellerCRM" / "Updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_target() -> dict[str, Any]:
    install = customer_install_dir()
    if sys.platform == "win32":
        app_dir = install / "Phone Reseller CRM"
        launcher = app_dir / "Phone Reseller CRM.exe"
        return {
            "kind": "windows_onedir",
            "install_dir": install,
            "app_dir": app_dir,
            "launcher": launcher,
        }
    if sys.platform == "darwin":
        app_bundle = install / "Phone Reseller CRM.app"
        launcher = app_bundle / "Contents" / "MacOS" / "PhoneResellerCRM"
        return {
            "kind": "mac_app",
            "install_dir": install,
            "app_bundle": app_bundle,
            "launcher": launcher,
        }
    raise RuntimeError("Automatic updates are only supported on Windows and macOS builds.")


def _download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with dest.open("wb") as handle:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    progress = min(99, int(downloaded * 100 / total))
                    _set_state(progress=progress, message=f"Downloading… {progress}%")


def _find_payload_root(staging: Path, kind: str) -> Path:
    if kind == "windows_onedir":
        name = "Phone Reseller CRM"
        direct = staging / name
        if direct.is_dir():
            return direct
    if kind == "mac_app":
        name = "Phone Reseller CRM.app"
        direct = staging / name
        if direct.is_dir():
            return direct
    for candidate in staging.rglob(name):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Update package is missing the application folder.")


def _spawn_windows_updater(new_app_dir: Path, target: dict[str, Any], parent_pid: int) -> Path:
    install = target["install_dir"]
    app_dir = target["app_dir"]
    launcher = target["launcher"]
    launcher_name = launcher.name
    backup = install / f"{app_dir.name}.update-backup"
    script = _updates_dir() / "apply_update.bat"
    script.write_text(
        f"""@echo off
setlocal EnableExtensions
timeout /t 2 /nobreak >nul
:wait
tasklist /FI "PID eq {parent_pid}" 2>nul | find "{parent_pid}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
if not exist "{new_app_dir}\\{launcher_name}" (
  rem Downloaded update looks incomplete/broken — leave the working
  rem install untouched and relaunch it instead of installing something
  rem that might not run.
  start "" "{launcher}"
  del /f /q "%~f0"
  exit /b 1
)
if exist "{backup}" rmdir /s /q "{backup}"
if exist "{app_dir}" move /Y "{app_dir}" "{backup}"
move /Y "{new_app_dir}" "{app_dir}"
if exist "{app_dir}\\{launcher_name}" (
  start "" "{launcher}"
  timeout /t 3 /nobreak >nul
  if exist "{backup}" rmdir /s /q "{backup}"
) else (
  rem The move somehow produced a broken install — restore the backup
  rem so the customer isn't left with nothing.
  if exist "{app_dir}" rmdir /s /q "{app_dir}"
  if exist "{backup}" move /Y "{backup}" "{app_dir}"
  start "" "{launcher}"
)
del /f /q "%~f0"
""",
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
        cwd=str(install),
    )
    return script


def _spawn_mac_updater(new_app_bundle: Path, target: dict[str, Any], parent_pid: int) -> Path:
    install = target["install_dir"]
    app_bundle = target["app_bundle"]
    launcher_rel = "Contents/MacOS/PhoneResellerCRM"
    backup = install / "Phone Reseller CRM.app.update-backup"
    script = _updates_dir() / "apply_update.command"
    script.write_text(
        f"""#!/bin/bash
# No `set -e` here on purpose — this script's job IS the safety net, so a
# transient non-zero exit from e.g. `open` must not abort it mid-way and
# skip the backup cleanup below.
sleep 2
while kill -0 {parent_pid} 2>/dev/null; do sleep 1; done
if [ ! -x "{new_app_bundle}/{launcher_rel}" ]; then
  # Downloaded update looks incomplete/broken — leave the working install
  # untouched and relaunch it instead of installing something that might
  # not run.
  open "{app_bundle}" || true
  rm -f "$0"
  exit 1
fi
rm -rf "{backup}"
if [ -d "{app_bundle}" ]; then mv "{app_bundle}" "{backup}"; fi
mv "{new_app_bundle}" "{app_bundle}"
if [ -x "{app_bundle}/{launcher_rel}" ]; then
  open "{app_bundle}" || true
  sleep 2
  rm -rf "{backup}"
else
  # The move somehow produced a broken install — restore the backup so
  # the customer isn't left with nothing.
  rm -rf "{app_bundle}"
  if [ -d "{backup}" ]; then mv "{backup}" "{app_bundle}"; fi
  open "{app_bundle}" || true
fi
rm -f "$0"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    subprocess.Popen(
        ["/bin/bash", str(script)],
        start_new_session=True,
        close_fds=True,
        cwd=str(install),
    )
    return script


def _apply_downloaded_update(zip_path: Path, target: dict[str, Any]) -> None:
    staging = _updates_dir() / "staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    _set_state(status="extracting", progress=99, message="Extracting update…")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(staging)

    payload = _find_payload_root(staging, target["kind"])

    if target["kind"] == "mac_app":
        # zip extraction does not reliably preserve the Unix executable bit
        # (this exact failure mode shipped once already) — restore it
        # explicitly rather than trust the archive's metadata.
        for name in ("PhoneResellerCRM", "FolderPicker"):
            for match in payload.rglob(name):
                if match.is_file():
                    match.chmod(0o755)

    parent_pid = os.getpid()

    _set_state(status="applying", progress=100, message="Preparing to restart…")
    if target["kind"] == "windows_onedir":
        _spawn_windows_updater(payload, target, parent_pid)
    else:
        _spawn_mac_updater(payload, target, parent_pid)

    _set_state(status="restarting", progress=100, message="Restarting CRM with the new version…")
    time.sleep(0.5)
    os._exit(0)


def _install_worker(download_url: str) -> None:
    try:
        target = _resolve_target()
        zip_path = _updates_dir() / "update-download.zip"
        if zip_path.exists():
            zip_path.unlink()

        _set_state(status="downloading", progress=0, message="Downloading update…")
        _download_file(download_url, zip_path)
        _apply_downloaded_update(zip_path, target)
    except Exception as exc:
        _set_state(status="error", error=str(exc), message=str(exc))


def start_install(download_url: str | None = None) -> dict[str, Any]:
    if not is_frozen_build():
        raise RuntimeError("In-app updates only work in the compiled customer app.")

    info = check_for_updates()
    url = (download_url or info.get("download_url") or "").strip()
    if not url:
        raise RuntimeError("No download URL for this platform in the update manifest.")

    with _state_lock:
        if _state.get("status") in ("downloading", "extracting", "applying", "restarting"):
            return dict(_state)

    _set_state(status="checking", progress=0, message="Starting update…", error=None)
    thread = threading.Thread(target=_install_worker, args=(url,), daemon=True)
    thread.start()
    return get_update_state()
