#!/usr/bin/env python3
"""
Build the Windows Setup installer — the ONE command a customer's whole
download-and-install experience is built from.

Usage (from Source folder, on Windows):
  python build_installer.py

Pipeline: PyInstaller onedir build -> Inno Setup compile -> checksum, with
the finished PhoneResellerCRM-Setup-{version}.exe landing in releases/
alongside a .sha256 file (same convention as the existing update-manifest
checksums in releases/HOSTING.md).

Requires Inno Setup 6's ISCC.exe. If missing:
  winget install JRSoftware.InnoSetup
This script looks in the usual per-user and machine-wide install locations
automatically; set CRM_ISCC_PATH to override.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT))
import build_customer_windows_copy as winbuild  # noqa: E402

RELEASES_DIR = ROOT / "releases"


def _find_iscc() -> Path:
    env_path = os.environ.get("CRM_ISCC_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise SystemExit(
        "ISCC.exe (Inno Setup 6 compiler) not found — install it first:\n"
        "  winget install JRSoftware.InnoSetup\n"
        "Or set CRM_ISCC_PATH to point directly at ISCC.exe."
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_pyinstaller() -> None:
    """Reuses build_customer_windows_copy.py's own PyInstaller step
    (ensure_pyinstaller + the license-secret handling + run_build) rather
    than duplicating it — installer.iss's [Files] section pulls straight
    from dist\\Phone Reseller CRM\\, the raw PyInstaller onedir output, so
    the intermediate "Customer Windows Copy" assembly step isn't needed
    here at all."""
    winbuild.ensure_pyinstaller()
    winbuild._write_license_secret_file()
    try:
        print("Building Phone Reseller CRM (PyInstaller) ...")
        winbuild.run_build("PhoneResellerCRM-win.spec")
    finally:
        secret_file = ROOT / "license_build_secret.txt"
        if secret_file.is_file():
            secret_file.unlink()

    app_dist = ROOT / "dist" / "Phone Reseller CRM"
    launcher = app_dist / "Phone Reseller CRM.exe"
    if not launcher.is_file():
        raise FileNotFoundError(f"Expected {launcher} after PyInstaller build")


def compile_installer() -> Path:
    iscc = _find_iscc()
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Compiling installer with {iscc} ...")
    subprocess.run(
        [str(iscc), str(ROOT / "installer.iss")],
        cwd=str(ROOT),
        check=True,
    )

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    setup_exe = RELEASES_DIR / f"PhoneResellerCRM-Setup-{version}.exe"
    if not setup_exe.is_file():
        raise FileNotFoundError(
            f"Expected {setup_exe} after Inno compile — check installer.iss's "
            "OutputDir/OutputBaseFilename match this script's expectations."
        )
    return setup_exe


def write_checksum(setup_exe: Path) -> Path:
    checksum = _sha256_file(setup_exe)
    checksum_file = setup_exe.with_suffix(setup_exe.suffix + ".sha256")
    checksum_file.write_text(f"{checksum}  {setup_exe.name}\n", encoding="utf-8")
    return checksum_file


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit(
            "The Windows installer must be built on Windows.\n"
            "On this machine, use GitHub Actions or run on a Windows PC:\n"
            "  cd Source\n"
            "  python build_installer.py"
        )

    build_pyinstaller()
    setup_exe = compile_installer()
    checksum_file = write_checksum(setup_exe)

    size_mb = setup_exe.stat().st_size / (1024 * 1024)
    print(f"\nOK Installer ready:\n  {setup_exe}  ({size_mb:.1f} MB)\n  {checksum_file}\n")


if __name__ == "__main__":
    main()
