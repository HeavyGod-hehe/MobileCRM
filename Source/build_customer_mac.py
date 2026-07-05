#!/usr/bin/env python3
"""
Build macOS Customer Copy for a specific CPU architecture.

Output folders (repo root):
  Customer Copy Apple Silicon/   — M1/M2/M3/M4 Macs (arm64)
  Customer Copy Intel Mac/       — Intel Macs (x86_64)
  Customer Copy Universal Mac/   — Intel + Apple Silicon (universal2)

Usage (from Source folder on macOS):
  python3 build_customer_mac.py --arch arm64
  python3 build_customer_mac.py --arch x86_64
  python3 build_customer_mac.py --arch universal
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

ARCH_OUTPUT = {
    "arm64": REPO / "Customer Copy Apple Silicon",
    "x86_64": REPO / "Customer Copy Intel Mac",
    "universal": REPO / "Customer Copy Universal Mac",
}

SOURCE_NAMES = {
    "app.py", "database.py", "license_guard.py", "folder_picker.py",
    "launch_crm.py", "backup_service.py", "email_service.py", "generate_key.py",
    "build_release.py", "build_customer_copy.py", "build_customer_mac.py",
    "build_customer_windows_copy.py", "run_crm.sh",
    "test_crm.py", "test_crm_performance.py", "stress_test_crm.py",
}


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )


def run_build(spec: str, arch: str) -> None:
    env = {
        **os.environ,
        "CRM_BUILD_PLATFORM": "mac",
        "CRM_MAC_ARCH": arch,
    }
    cmd = [*_python_for_arch(arch), "-m", "PyInstaller", "--noconfirm", "--clean", spec]
    subprocess.run(
        cmd,
        cwd=str(ROOT),
        check=True,
        env=env,
    )


def is_macho(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["file", "-b", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return "Mach-O" in result.stdout
    except (OSError, subprocess.CalledProcessError):
        return False


def merge_macho_binary(arm_path: Path, intel_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["lipo", "-create", str(arm_path), str(intel_path), "-output", str(out_path)],
        check=True,
    )
    shutil.copystat(arm_path, out_path, follow_symlinks=False)


def merge_app_bundles(arm_app: Path, intel_app: Path, out_app: Path) -> None:
    if out_app.exists():
        shutil.rmtree(out_app)
    shutil.copytree(arm_app, out_app, symlinks=True)

    for arm_file in arm_app.rglob("*"):
        if not arm_file.is_file() or arm_file.is_symlink():
            continue
        rel = arm_file.relative_to(arm_app)
        intel_file = intel_app / rel
        out_file = out_app / rel
        if not intel_file.is_file():
            continue
        if is_macho(arm_file) and is_macho(intel_file):
            merge_macho_binary(arm_file, intel_file, out_file)


def verify_universal(app_binary: Path) -> None:
    result = subprocess.run(
        ["lipo", "-info", str(app_binary)],
        capture_output=True,
        text=True,
        check=True,
    )
    info = result.stdout.lower()
    if "x86_64" not in info or "arm64" not in info:
        raise RuntimeError(
            f"Expected universal2 binary but lipo reports:\n{result.stdout}"
        )


def _python_for_arch(arch: str) -> list[str]:
    """Return argv prefix to run Python for the requested architecture."""
    if arch == "x86_64" and platform.machine() == "arm64":
        return ["arch", "-x86_64", sys.executable]
    if arch == "arm64" and platform.machine() == "x86_64":
        return ["arch", "-arm64", sys.executable]
    return [sys.executable]


def _build_to_temp(arch: str) -> Path:
    with tempfile.TemporaryDirectory(prefix=f"crm-mac-{arch}-") as tmp:
        tmp_path = Path(tmp)
        out = tmp_path / "out"
        build_mac_copy(arch, out=out)
        staged = tmp_path / "staged"
        shutil.copytree(out / "Phone Reseller CRM.app", staged / "Phone Reseller CRM.app")
        picker = out / "FolderPicker"
        if picker.is_file():
            shutil.copy2(picker, staged / "FolderPicker")
        persist = tempfile.mkdtemp(prefix=f"crm-mac-{arch}-persist-")
        shutil.copytree(staged, persist)
        return Path(persist) / "Phone Reseller CRM.app"


def build_universal_copy(
    out: Path | None = None,
    arm64_app: Path | None = None,
    x86_64_app: Path | None = None,
) -> Path:
    if sys.platform != "darwin":
        raise SystemExit(
            "macOS customer builds must run on macOS.\n"
            "Use GitHub Actions or a Mac to build."
        )

    out = out or ARCH_OUTPUT["universal"]

    if arm64_app or x86_64_app:
        if not (arm64_app and x86_64_app):
            raise SystemExit("--arm64-app and --x86-64-app must both be given together")
        arm_app = Path(arm64_app)
        intel_app = Path(x86_64_app)
        if not arm_app.is_dir():
            raise SystemExit(f"Prebuilt arm64 app not found: {arm_app}")
        if not intel_app.is_dir():
            raise SystemExit(f"Prebuilt x86_64 app not found: {intel_app}")
    else:
        machine = platform.machine()
        if machine not in ("arm64", "x86_64"):
            raise SystemExit(f"Unsupported Mac architecture: {machine}")
        ensure_pyinstaller()

        print("Building arm64 slice …")
        try:
            arm_app = _build_to_temp("arm64")
        except Exception as exc:
            raise SystemExit(
                "Could not build the Apple Silicon (arm64) slice.\n"
                "Run this on an Apple Silicon Mac, or build arm64 and x86_64 copies separately and merge with CI.\n"
                f"Details: {exc}"
            ) from exc

        print("Building x86_64 slice …")
        try:
            intel_app = _build_to_temp("x86_64")
        except Exception as exc:
            raise SystemExit(
                "Could not build the Intel (x86_64) slice.\n"
                "On Apple Silicon, install Rosetta and an x64 Python wheel set.\n"
                f"Details: {exc}"
            ) from exc

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    print("Merging universal Phone Reseller CRM.app …")
    merged_app = out / "Phone Reseller CRM.app"
    merge_app_bundles(arm_app, intel_app, merged_app)

    main_binary = merged_app / "Contents" / "MacOS" / "PhoneResellerCRM"
    main_binary.chmod(0o755)
    verify_universal(main_binary)

    arm_picker = arm_app.parent / "FolderPicker"
    intel_picker = intel_app.parent / "FolderPicker"
    if arm_picker.is_file() and intel_picker.is_file():
        universal_picker = out / "FolderPicker"
        merge_macho_binary(arm_picker, intel_picker, universal_picker)
        universal_picker.chmod(0o755)
        macos = merged_app / "Contents" / "MacOS"
        shutil.copy2(universal_picker, macos / "FolderPicker")
        (macos / "FolderPicker").chmod(0o755)

    write_start_here(out, "universal")
    write_open_me_first(out)
    (out / "license.json").write_text("{}\n", encoding="utf-8")
    verify_no_source(out)

    print(f"\n✓ Universal Customer Copy ready:\n  {out}\n")
    return out


def write_open_me_first(out: Path) -> None:
    """A one-click helper for first-time setup.

    Freshly downloaded apps aren't code-signed with a paid Apple Developer
    ID, so macOS quarantines them and blocks the first launch with "Apple
    could not verify... free of malware". This script clears that
    quarantine flag (the same fix as the manual `xattr -cr` Terminal
    command) and then opens the app, so customers get one thing to
    right-click-Open instead of fighting Gatekeeper on the app itself.
    """
    script = out / "Open Me First.command"
    script.write_text(
        """#!/bin/bash
# Clears the macOS "downloaded from the internet" flag that triggers the
# "Apple could not verify this app is free of malware" warning, then opens
# the CRM. Safe to run every time — it's a no-op once the flag is gone.
cd "$(dirname "$0")"
xattr -cr "Phone Reseller CRM.app" 2>/dev/null
xattr -cr "FolderPicker" 2>/dev/null
open "Phone Reseller CRM.app"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def write_start_here(out: Path, arch: str) -> None:
    if arch == "universal":
        chip_label = "Universal (Intel + Apple Silicon)"
        wrong_chip = """  This build runs on BOTH:
  • Intel Mac
  • Apple Silicon (M1/M2/M3/M4)"""
    else:
        chip_label = "Apple Silicon (M1/M2/M3/M4)" if arch == "arm64" else "Intel Mac"
        wrong_chip = """  • M1/M2/M3/M4 Mac → use "Customer Copy Apple Silicon" folder
  • Intel Mac       → use "Customer Copy Intel Mac" folder
  • Both chip types → use "Customer Copy Universal Mac" folder
  • Windows PC      → use "Customer Windows Copy" folder"""
    (out / "START HERE.txt").write_text(
        f"""Phone Reseller CRM — Customer Edition v{VERSION} (Mac — {chip_label})
{'=' * (52 + len(chip_label))}

This build is for: {chip_label}
NO Python or source code — everything is inside the app.

HOW TO START (first time)
──────────────────────────
  1. Double-click:  Open Me First.command
  2. macOS will warn it's from an unidentified developer — that's expected
     for a freshly downloaded app. Right-click "Open Me First.command" →
     Open → Open. (Only needs doing once.)
  3. The CRM opens in your browser at http://localhost:5050

AFTER THE FIRST TIME
────────────────────
  • Just double-click Phone Reseller CRM.app directly — no more warnings
  • If CRM is already running, double-clicking opens the existing session
  • If it does not open, wait 10 seconds and visit http://localhost:5050

WRONG CHIP?
───────────
{wrong_chip}

STILL BLOCKED?
──────────────
  If "Open Me First.command" itself won't run:
  1. Open Terminal in this folder
  2. Run:  xattr -cr "Phone Reseller CRM.app" "FolderPicker"
  3. Or: System Settings → Privacy & Security → scroll down → "Open Anyway"

TROUBLESHOOTING
───────────────
  • Check Data/crm.log next to the app for errors
  • Your data lives in Data/crm.db and Data/Backups/
  • Use Settings → Close CRM instead of Force Quit

FIRST TIME SETUP
────────────────
  • Activation: copy Hardware ID → get key from vendor → Activate
  • Sign up with username, password & email
  • Settings → Shop Details (name, address, WhatsApp)
  • Data folder is created automatically next to the app

FEATURES
────────
  • Inventory, cash book & accounts stay synced
  • Borrow phones from shopkeepers
  • Accounts Credit & Debit — Food/expenses deduct from cash or bank
  • Dual IMEI, bulk sell, returns, journal, billing

Support: contact your CRM vendor.
""",
        encoding="utf-8",
    )


def verify_no_source(out: Path) -> None:
    for path in out.iterdir():
        if path.suffix == ".py" and path.name in SOURCE_NAMES:
            raise RuntimeError(f"Source file must not be shipped: {path}")


def verify_arch(app_binary: Path, expected: str) -> None:
    """Confirm the built binary matches the requested architecture."""
    result = subprocess.run(
        ["file", str(app_binary)],
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout.lower()
    if expected == "arm64" and "arm64" not in output:
        raise RuntimeError(
            f"Expected arm64 binary but file reports:\n{result.stdout}\n"
            "Build on macOS with CRM_MAC_ARCH=arm64"
        )
    if expected == "x86_64" and "x86_64" not in output:
        raise RuntimeError(
            f"Expected x86_64 binary but file reports:\n{result.stdout}\n"
            "For Intel builds on Apple Silicon CI, use architecture: x64 Python."
        )


def build_mac_copy(
    arch: str,
    out: Path | None = None,
    arm64_app: Path | None = None,
    x86_64_app: Path | None = None,
) -> Path:
    if sys.platform != "darwin":
        raise SystemExit(
            "macOS customer builds must run on macOS.\n"
            "Use GitHub Actions or a Mac to build."
        )
    if arch == "universal":
        return build_universal_copy(out, arm64_app=arm64_app, x86_64_app=x86_64_app)
    if arch not in ("arm64", "x86_64"):
        raise ValueError(f"arch must be one of {list(ARCH_OUTPUT)}")

    out = out or ARCH_OUTPUT[arch]
    ensure_pyinstaller()

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    print(f"Building Phone Reseller CRM.app ({arch}) …")
    run_build("PhoneResellerCRM-mac.spec", arch)

    app_src = ROOT / "dist" / "Phone Reseller CRM.app"
    if not app_src.is_dir():
        raise FileNotFoundError(f"Expected app at {app_src}")

    main_binary = app_src / "Contents" / "MacOS" / "PhoneResellerCRM"
    verify_arch(main_binary, arch)

    shutil.copytree(app_src, out / "Phone Reseller CRM.app")

    print("Building FolderPicker …")
    run_build("FolderPicker.spec", arch)
    picker_src = ROOT / "dist" / "FolderPicker"
    if picker_src.is_file():
        macos = out / "Phone Reseller CRM.app" / "Contents" / "MacOS"
        shutil.copy2(picker_src, macos / "FolderPicker")
        (macos / "FolderPicker").chmod(0o755)
        shutil.copy2(picker_src, out / "FolderPicker")
        (out / "FolderPicker").chmod(0o755)

    write_start_here(out, arch)
    write_open_me_first(out)
    (out / "license.json").write_text("{}\n", encoding="utf-8")
    verify_no_source(out)

    print(f"\n✓ Customer Copy ready ({arch}):\n  {out}\n")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Mac Customer Copy")
    parser.add_argument(
        "--arch",
        required=True,
        choices=sorted(ARCH_OUTPUT),
        help="Target Mac CPU: arm64, x86_64, or universal (Intel + Apple Silicon)",
    )
    parser.add_argument(
        "--arm64-app",
        type=Path,
        default=None,
        help="Prebuilt arm64 .app to merge (universal only; skips building from source)",
    )
    parser.add_argument(
        "--x86-64-app",
        type=Path,
        default=None,
        help="Prebuilt x86_64 .app to merge (universal only; skips building from source)",
    )
    args = parser.parse_args()
    build_mac_copy(args.arch, arm64_app=args.arm64_app, x86_64_app=args.x86_64_app)


if __name__ == "__main__":
    main()
