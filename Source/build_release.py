#!/usr/bin/env python3
"""
Build standalone Phone Reseller CRM executables with PyInstaller.

Outputs:
  ~/Downloads/windows setup/PhoneResellerCRM.exe (+ FolderPicker.exe)
  ~/Downloads/mac setup/PhoneResellerCRM (+ FolderPicker helper)

Run from project root:
  python build_release.py
  python build_release.py --platform windows
  python build_release.py --platform mac
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def get_downloads_dir() -> Path:
    """Resolve the user's local Downloads directory cross-platform."""
    home = Path.home()
    candidates = [
        home / "Downloads",
        home / "download",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    fallback = home / "Downloads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def run_pyinstaller(target_platform: str) -> Path:
    spec = ROOT / "PhoneResellerCRM.spec"
    if not spec.is_file():
        raise FileNotFoundError(f"Missing spec file: {spec}")

    env = os.environ.copy()
    env["CRM_BUILD_PLATFORM"] = target_platform

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(ROOT), check=True, env=env)

    dist_exe = ROOT / "dist" / "PhoneResellerCRM.exe"
    dist_bin = ROOT / "dist" / "PhoneResellerCRM"
    if dist_exe.is_file():
        return dist_exe
    if dist_bin.is_file():
        return dist_bin
    raise FileNotFoundError("PyInstaller did not produce PhoneResellerCRM executable")


def build_folder_picker(target_platform: str) -> Path | None:
    picker_spec = ROOT / "FolderPicker.spec"
    if not picker_spec.is_file():
        return None
    env = os.environ.copy()
    env["CRM_BUILD_PLATFORM"] = target_platform
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(picker_spec)],
        cwd=str(ROOT),
        check=True,
        env=env,
    )
    exe = ROOT / "dist" / "FolderPicker.exe"
    bin_path = ROOT / "dist" / "FolderPicker"
    return exe if exe.is_file() else (bin_path if bin_path.is_file() else None)


def copy_to_output(src: Path, dest_dir: Path, name: str | None = None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or src.name)
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    shutil.copy2(src, dest)
    if platform.system() != "Windows" and not str(dest).endswith(".exe"):
        dest.chmod(dest.stat().st_mode | 0o111)
    return dest


def write_readme(dest_dir: Path, target_platform: str) -> None:
    readme = dest_dir / "README.txt"
    readme.write_text(
        f"""Phone Reseller CRM — {target_platform.title()} Setup
========================================

1. Run PhoneResellerCRM{'(.exe)' if target_platform == 'windows' else ''} to start the CRM.
   Your default browser opens automatically (default port 5050).
2. Or double-click "Start Phone Reseller CRM{' .bat' if target_platform == 'windows' else '.command'}" in this folder.
3. On first launch, create your admin account at the signup screen.
4. The SQLite database (crm.db) is created next to the executable.

Set CRM_PORT=5000 before starting to use a different port.

Built from: {ROOT.name}
""",
        encoding="utf-8",
    )


def resolve_build_targets(requested: str) -> list[str]:
    """Pick build targets for the current host; never require macOS tools on Windows."""
    system = platform.system().lower()
    on_windows = "windows" in system
    on_mac = "darwin" in system or "mac" in system

    if requested == "current":
        if on_windows:
            return ["windows"]
        if on_mac:
            return ["mac"]
        return ["windows"]

    if requested == "mac":
        if not on_mac:
            print("Skipping mac build: macOS build tools are not available on this host.")
            return []
        return ["mac"]

    if requested == "windows":
        return ["windows"]

    return [requested]


def main():
    parser = argparse.ArgumentParser(description="Build CRM standalone executables")
    parser.add_argument(
        "--platform",
        choices=("windows", "mac", "current"),
        default="current",
        help="Target platform folder name (defaults to the current OS)",
    )
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller…")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    downloads = get_downloads_dir()
    targets = resolve_build_targets(args.platform)
    if not targets:
        print("No builds to run on this host.")
        return

    for target in targets:
        folder_name = "windows setup" if target == "windows" else "mac setup"
        out_dir = downloads / folder_name
        print(f"\n=== Building for {target} → {out_dir} ===\n")

        main_exe = run_pyinstaller(target)
        copy_to_output(main_exe, out_dir)

        try:
            picker = build_folder_picker(target)
            if picker:
                copy_to_output(picker, out_dir)
        except subprocess.CalledProcessError:
            print("Warning: FolderPicker build failed (optional)")

        launcher_name = (
            "Start Phone Reseller CRM.bat"
            if target == "windows"
            else "Start Phone Reseller CRM.command"
        )
        launcher_src = ROOT / launcher_name
        if launcher_src.is_file():
            copy_to_output(launcher_src, out_dir)

        write_readme(out_dir, target)
        print(f"Done: {out_dir}")

    print(f"\nAll builds placed under: {downloads}")


if __name__ == "__main__":
    main()
