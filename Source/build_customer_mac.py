#!/usr/bin/env python3
"""
Build macOS Customer Copy for a specific CPU architecture.

Output folders (repo root):
  Customer Copy Apple Silicon/   — M1/M2/M3/M4 Macs (arm64)
  Customer Copy Intel Mac/     — Intel Macs (x86_64)

Usage (from Source folder on macOS):
  python3 build_customer_mac.py --arch arm64
  python3 build_customer_mac.py --arch x86_64
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent

ARCH_OUTPUT = {
    "arm64": REPO / "Customer Copy Apple Silicon",
    "x86_64": REPO / "Customer Copy Intel Mac",
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
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec],
        cwd=str(ROOT),
        check=True,
        env=env,
    )


def write_start_here(out: Path, arch: str) -> None:
    chip_label = "Apple Silicon (M1/M2/M3/M4)" if arch == "arm64" else "Intel Mac"
    (out / "START HERE.txt").write_text(
        f"""Phone Reseller CRM — Customer Edition v2.3 (Mac — {chip_label})
{'=' * (52 + len(chip_label))}

This build is for: {chip_label}
NO Python or source code — everything is inside the app.

HOW TO START
────────────
  1. Double-click:  Phone Reseller CRM.app
  2. Browser opens at http://localhost:5050
  3. If it does not open, wait 10 seconds and visit http://localhost:5050

WRONG CHIP?
───────────
  • M1/M2/M3/M4 Mac → use "Customer Copy Apple Silicon" folder
  • Intel Mac       → use "Customer Copy Intel Mac" folder
  • Windows PC      → use "Customer Windows Copy" folder

FIRST TIME ON MAC
─────────────────
  If macOS blocks the app:
  1. Open Terminal in this folder
  2. Run:  xattr -cr "Phone Reseller CRM.app"
  3. Right-click the app → Open → Open

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

FEATURES (v2.3)
───────────────
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


def build_mac_copy(arch: str, out: Path | None = None) -> Path:
    if sys.platform != "darwin":
        raise SystemExit(
            "macOS customer builds must run on macOS.\n"
            "Use GitHub Actions or a Mac to build."
        )
    if arch not in ARCH_OUTPUT:
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
        help="Target Mac CPU: arm64 (Apple Silicon) or x86_64 (Intel)",
    )
    args = parser.parse_args()
    build_mac_copy(args.arch)


if __name__ == "__main__":
    main()
