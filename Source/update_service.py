"""Auto-updater for frozen (PyInstaller) customer builds.

Hosts a version.json manifest (see releases/version.json.example). The app
compares semver, downloads the platform zip, and applies it via a small helper
script after the CRM process exits (required on Windows/macOS).
"""

from __future__ import annotations

import hashlib
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
    """The version number of the app that is actually running right now."""
    return _read_local_version()


def _read_local_version() -> str:
    """Read the VERSION file bundled at build time. In a frozen (PyInstaller)
    build it lives inside the app's bundled resources (sys._MEIPASS); when
    running from source it's just the VERSION file next to this script."""
    if getattr(sys, "frozen", False):
        ver_path = Path(sys._MEIPASS) / "VERSION"
        if ver_path.is_file():
            return ver_path.read_text(encoding="utf-8").strip()
        return "1.0.0"
    ver_path = Path(__file__).resolve().parent / "VERSION"
    return ver_path.read_text(encoding="utf-8").strip() if ver_path.is_file() else "0.0.0"


def version_tuple(version: str) -> tuple[int, ...]:
    """Turn "2.4.11" into (2, 4, 11) so versions can be compared numerically
    instead of as strings (string comparison would wrongly say "2.9" > "2.10")."""
    parts: list[int] = []
    for piece in (version or "").strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def is_newer_version(remote: str, current: str) -> bool:
    """True if the manifest's version is ahead of what's installed. Falls
    back to a plain string inequality if either version string doesn't
    parse as numeric, so a weird version string never crashes the check."""
    if not remote:
        return False
    try:
        return version_tuple(remote) > version_tuple(current)
    except (ValueError, TypeError):
        return remote.strip() != current.strip()


def is_frozen_build() -> bool:
    """True only for a compiled customer copy (PyInstaller), never when
    running from source — auto-updates only make sense for customer builds."""
    return bool(getattr(sys, "frozen", False))


def platform_key() -> str | None:
    """Which key this machine should look up in the manifest's "downloads"
    map (windows / mac_intel / mac_arm64), or None on an unsupported OS."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            return "mac_arm64"
        return "mac_intel"
    return None


def _http_get_text(url: str, timeout: int = 12) -> str:
    """Plain GET request with a short timeout — update checks must never
    hang the app if the customer has no internet or GitHub is unreachable."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8").strip()


def _http_get_json(url: str, timeout: int = 12) -> dict[str, Any]:
    """Same as _http_get_text() but parses the response as JSON (the manifest format)."""
    text = _http_get_text(url, timeout=timeout)
    return json.loads(text)


def _set_state(**kwargs) -> None:
    """Update the shared install-progress state (status/progress/message)
    behind a lock, since it's written from the background download thread
    and read from the web request thread that polls it for the progress bar."""
    with _state_lock:
        _state.update(kwargs)


def get_update_state() -> dict[str, Any]:
    """Snapshot of the current update-install progress, polled by the
    Settings page's progress bar while an update is downloading/installing."""
    with _state_lock:
        return dict(_state)


def _pick_download(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Find the right download entry for this machine's OS/architecture in
    the manifest, falling back to a universal Mac build if this Mac's exact
    architecture isn't listed separately."""
    downloads = manifest.get("downloads") or {}
    key = platform_key()
    if not key:
        return None
    if key in downloads:
        return downloads[key]
    if sys.platform == "darwin" and "mac_universal" in downloads:
        return downloads["mac_universal"]
    return None


def _is_valid_manifest(data: Any) -> bool:
    """Structural check on a fetched manifest before it's trusted anywhere
    else in this module. Bug #10: nothing validated version.json's shape
    before this -- a malformed manifest (e.g. a download entry that's a
    string instead of an object) would crash check_for_updates() with an
    AttributeError instead of being treated as "no update available," the
    same way an unreachable manifest already is."""
    if not isinstance(data, dict):
        return False
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        return False
    downloads = data.get("downloads")
    if downloads is not None:
        if not isinstance(downloads, dict):
            return False
        for entry in downloads.values():
            if not isinstance(entry, dict):
                return False
            if "url" in entry and not isinstance(entry["url"], str):
                return False
            if "sha256" in entry and not isinstance(entry["sha256"], str):
                return False
    return True


def fetch_manifest(url: str | None = None) -> dict[str, Any] | None:
    """Download and parse version.json from the public releases repo.
    Returns None on any network/parse/shape failure rather than raising,
    since a failed update check should be invisible to the shop owner, not
    a crash."""
    manifest_url = (url or DEFAULT_MANIFEST_URL).strip()
    if not manifest_url:
        return None
    try:
        data = _http_get_json(manifest_url, timeout=4)
        if _is_valid_manifest(data):
            return data
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    return None


def check_for_updates() -> dict[str, Any]:
    """The main entry point the Settings page calls to check for updates.
    Tries the modern JSON manifest first; if that's unreachable, falls back
    to the old plain-text VERSION file (LEGACY_VERSION_URL) so very old
    customer builds that predate the manifest format still get a "new
    version available" notice, even without a working auto-install."""
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
        "download_sha256": (download or {}).get("sha256"),
        "can_auto_install": can_auto_install,
        "platform": platform_key(),
        "frozen": is_frozen_build(),
    }


def _updates_dir() -> Path:
    """Scratch folder for downloaded update zips/staging files — inside the
    customer's Data folder when frozen, or the OS temp dir when running
    from source (where customer_data_dir() returns None)."""
    data = customer_data_dir()
    if data:
        path = data / "Updates"
    else:
        path = Path(tempfile.gettempdir()) / "PhoneResellerCRM" / "Updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_target() -> dict[str, Any]:
    """Figure out where the currently-installed app lives on disk and what
    its launcher executable is called, so the updater knows exactly what to
    replace. Raises on any OS other than Windows/macOS (Linux auto-update
    isn't supported).

    Windows note: customer_install_dir() already resolves to the PyInstaller
    onedir app folder itself (it returns sys.executable's own parent — same
    folder customer_data_dir() sits next to, via `.. / "Data"`). This used to
    be treated here as if it were the folder ABOVE the app folder, then
    "Phone Reseller CRM" was appended again — one directory too deep, so
    app_dir/launcher pointed at a path that never existed and Windows
    installs could never auto-update (Mac's branch below was never affected,
    since its equivalent walk-up-out-of-the-bundle logic already lives
    inside customer_install_dir() itself). Deliberately NOT changing
    customer_install_dir() itself to fix this — that function also decides
    where customer_data_dir()/DB_PATH lives, and moving it out from under
    already-installed customers would look like their database vanished on
    the next update. This fix is scoped to the updater's own path math only."""
    if sys.platform == "win32":
        app_dir = customer_install_dir()
        launcher = Path(sys.executable).resolve()
        return {
            "kind": "windows_onedir",
            "install_dir": app_dir.parent,
            "app_dir": app_dir,
            "launcher": launcher,
        }
    install = customer_install_dir()
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
    """Stream the update zip to disk in chunks (not all at once — these
    files can be tens of MB), updating the shared progress state as it goes
    so the Settings page's progress bar can show real percentage."""
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
    """Find the actual app folder/bundle inside the extracted update zip -
    release zips are expected to contain it at the top level, but this also
    searches subfolders in case a release was zipped with an extra wrapper
    directory."""
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
    """Write and launch a helper .bat script that swaps the old app folder
    for the new one and relaunches the app. This can't happen from inside
    this process: Windows won't let you delete/replace a running .exe's own
    folder, so the swap has to happen from a separate process after this one
    exits (the script polls `tasklist` for parent_pid to know when that's
    safe). The script also keeps a backup and rolls back automatically if
    the new folder turns out to be missing its launcher, so a bad download
    can't leave the customer with no working app at all."""
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
    """macOS equivalent of _spawn_windows_updater() above: a helper shell
    script (using `kill -0` to poll whether the old process has exited)
    swaps the .app bundle and relaunches it, with the same backup-and-
    rollback safety net if the downloaded bundle looks broken."""
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
    """Unzip the downloaded update, fix up file permissions the zip format
    doesn't preserve, hand off to the platform-specific helper script to do
    the actual swap-and-relaunch, then exit this process immediately
    (os._exit, not a normal return) so the helper script's wait-for-parent-
    to-exit check succeeds."""
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_worker(download_url: str, expected_sha256: str | None = None) -> None:
    """Runs in a background thread (started by start_install() below): does
    the actual download + apply, updating _state as it progresses so the
    web UI's polling can show a live progress bar. Any exception here is
    caught and stored in _state["error"] instead of crashing the thread
    silently, since an uncaught background-thread exception would otherwise
    just vanish with no feedback to the shop owner."""
    try:
        target = _resolve_target()
        zip_path = _updates_dir() / "update-download.zip"
        if zip_path.exists():
            zip_path.unlink()

        _set_state(status="downloading", progress=0, message="Downloading update…")
        _download_file(download_url, zip_path)

        if expected_sha256:
            _set_state(status="downloading", progress=99, message="Verifying download…")
            actual = _sha256_file(zip_path)
            if actual.lower() != expected_sha256.lower():
                raise RuntimeError(
                    "Downloaded update failed checksum verification — the file "
                    "may be corrupted or incomplete. Please try again."
                )

        _apply_downloaded_update(zip_path, target)
    except Exception as exc:
        _set_state(status="error", error=str(exc), message=str(exc))


def start_install(download_url: str | None = None) -> dict[str, Any]:
    """Kick off an update install in the background and return immediately
    (the web request that triggers this can't block for the whole download).
    Refuses to start a second install if one is already in progress, and
    refuses entirely outside a frozen customer build."""
    if not is_frozen_build():
        raise RuntimeError("In-app updates only work in the compiled customer app.")

    info = check_for_updates()
    url = (download_url or info.get("download_url") or "").strip()
    if not url:
        raise RuntimeError("No download URL for this platform in the update manifest.")

    # Only trust the manifest's checksum when downloading the exact URL it
    # was computed for -- an explicitly overridden download_url has no
    # known-good checksum to verify against.
    expected_sha256 = info.get("download_sha256") if url == info.get("download_url") else None

    with _state_lock:
        if _state.get("status") in ("downloading", "extracting", "applying", "restarting"):
            return dict(_state)

    _set_state(status="checking", progress=0, message="Starting update…", error=None)
    thread = threading.Thread(target=_install_worker, args=(url, expected_sha256), daemon=True)
    thread.start()
    return get_update_state()
