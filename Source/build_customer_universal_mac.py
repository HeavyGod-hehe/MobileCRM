#!/usr/bin/env python3
"""
Build or merge a universal macOS Customer Copy (Intel + Apple Silicon).

Mode 1 — full build on macOS (local):
  python3 build_customer_universal_mac.py

Mode 2 — merge existing arch builds (CI / local):
  python3 build_customer_universal_mac.py \\
    --arm64-dir "../Customer Copy Apple Silicon" \\
    --intel-dir "../Customer Copy Intel Mac"
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = REPO / "Customer Copy Universal Mac"

SOURCE_NAMES = {
    "app.py", "database.py", "license_guard.py", "folder_picker.py",
    "launch_crm.py", "crm_instance.py", "backup_service.py", "email_service.py",
    "generate_key.py", "build_release.py", "build_customer_copy.py",
    "build_customer_mac.py", "build_customer_universal_mac.py",
    "build_customer_windows_copy.py", "run_crm.sh",
    "test_crm.py", "test_crm_performance.py", "stress_test_crm.py",
}


def _lipo_universal(arm_path: Path, intel_path: Path, out_path: Path) -> None:
    subprocess.run(
        ["lipo", "-create", str(arm_path), str(intel_path), "-output", str(out_path)],
        check=True,
    )
    out_path.chmod(0o755)


def _verify_universal(binary: Path) -> None:
    result = subprocess.run(["file", str(binary)], capture_output=True, text=True, check=True)
    output = result.stdout.lower()
    if "x86_64" not in output or "arm64" not in output:
        raise RuntimeError(f"Expected universal binary but file reports:\n{result.stdout}")


def _write_start_here(out: Path) -> None:
    (out / "START HERE.txt").write_text(
        """Phone Reseller CRM — Customer Edition v2.3 (Mac — Universal)
================================================================

This build runs on BOTH:
  • Apple Silicon Macs (M1 / M2 / M3 / M4)
  • Intel Macs (Core i5 / i7 / i9)

NO Python or source code — everything is inside the app.

HOW TO START
────────────
  1. Double-click:  Phone Reseller CRM.app
  2. Browser opens at http://localhost:5050
  3. Closed the browser? Double-click the app again — it reopens the CRM.

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

Support: contact your CRM vendor.
""",
        encoding="utf-8",
    )


def merge_arch_copies(arm_dir: Path, intel_dir: Path, out: Path) -> Path:
    arm_app = arm_dir / "Phone Reseller CRM.app"
    intel_app = intel_dir / "Phone Reseller CRM.app"
    if not arm_app.is_dir():
        raise FileNotFoundError(f"Missing Apple Silicon app: {arm_app}")
    if not intel_app.is_dir():
        raise FileNotFoundError(f"Missing Intel app: {intel_app}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    shutil.copytree(arm_app, out / "Phone Reseller CRM.app")

    for rel in (
        Path("Contents/MacOS/PhoneResellerCRM"),
        Path("Contents/MacOS/FolderPicker"),
    ):
        arm_bin = arm_app / rel
        intel_bin = intel_app / rel
        out_bin = out / "Phone Reseller CRM.app" / rel
        if arm_bin.is_file() and intel_bin.is_file() and out_bin.is_file():
            _lipo_universal(arm_bin, intel_bin, out_bin)

    arm_picker = arm_dir / "FolderPicker"
    intel_picker = intel_dir / "FolderPicker"
    if arm_picker.is_file() and intel_picker.is_file():
        _lipo_universal(arm_picker, intel_picker, out / "FolderPicker")
        (out / "FolderPicker").chmod(0o755)
    elif arm_picker.is_file():
        shutil.copy2(arm_picker, out / "FolderPicker")
        (out / "FolderPicker").chmod(0o755)

    main_binary = out / "Phone Reseller CRM.app" / "Contents" / "MacOS" / "PhoneResellerCRM"
    _verify_universal(main_binary)

    _write_start_here(out)
    (out / "license.json").write_text("{}\n", encoding="utf-8")

    for path in out.iterdir():
        if path.suffix == ".py" and path.name in SOURCE_NAMES:
            raise RuntimeError(f"Source file must not be shipped: {path}")

    print(f"\n✓ Universal Customer Copy ready:\n  {out}\n")
    return out


def build_universal_mac_copy(out: Path | None = None) -> Path:
    if sys.platform != "darwin":
        raise SystemExit(
            "Universal macOS builds must run on macOS.\n"
            "Use GitHub Actions or a Mac to build."
        )

    from build_customer_mac import build_mac_copy

    out = out or OUT

    with tempfile.TemporaryDirectory(prefix="crm-universal-") as tmp:
        tmp_path = Path(tmp)
        arm_dir = tmp_path / "arm64"
        intel_dir = tmp_path / "x86_64"

        print("Building Apple Silicon slice …")
        build_mac_copy("arm64", arm_dir)

        print("Building Intel slice …")
        build_mac_copy("x86_64", intel_dir)

        return merge_arch_copies(arm_dir, intel_dir, out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or merge universal Mac Customer Copy")
    parser.add_argument("--arm64-dir", type=Path, help="Existing Apple Silicon customer copy folder")
    parser.add_argument("--intel-dir", type=Path, help="Existing Intel customer copy folder")
    parser.add_argument("--out", type=Path, default=OUT, help="Output folder")
    args = parser.parse_args()

    if args.arm64_dir and args.intel_dir:
        merge_arch_copies(args.arm64_dir.resolve(), args.intel_dir.resolve(), args.out.resolve())
        return
    if args.arm64_dir or args.intel_dir:
        raise SystemExit("Provide both --arm64-dir and --intel-dir to merge existing builds.")

    build_universal_mac_copy(args.out.resolve())


if __name__ == "__main__":
    main()
