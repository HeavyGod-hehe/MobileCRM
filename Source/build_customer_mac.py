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
    """Install PyInstaller into this Python environment if it's missing."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )


def _write_license_secret_file() -> None:
    """Bake CRM_LICENSE_SECRET (the CI/repo secret) into a small text file
    the .spec bundles alongside the frozen app, so it actually reaches the
    customer's machine — see license_guard._build_baked_secret() for why a
    plain env var set only during this build step would otherwise have zero
    effect at runtime on the customer's own machine. Refuses to build at all
    if the secret isn't set, so a missing CI secret fails loudly here
    instead of silently shipping every customer the hardcoded fallback
    secret (the exact bug this exists to close). Never prints the value."""
    secret = os.environ.get("CRM_LICENSE_SECRET", "").strip()
    if not secret:
        raise SystemExit(
            "CRM_LICENSE_SECRET is not set in the environment — refusing to "
            "build a customer release without it. Set it as a CI/repo "
            "secret (see HOW_TO_RELEASE.md) before building."
        )
    (ROOT / "license_build_secret.txt").write_text(secret, encoding="utf-8")


def run_build(spec: str, arch: str) -> None:
    """Run PyInstaller for one architecture slice, using arch-specific env
    vars the .spec file reads to pick the right settings for that chip."""
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
    """True if `path` is a compiled Mac binary (Mach-O format), as opposed
    to a plain data/text file — used to decide which files inside the app
    bundle need architecture-merging (merge_macho_binary) versus a plain copy."""
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
    """Fuse an arm64 build and an x86_64 build of the SAME binary into one
    "universal2" file (via Apple's `lipo` tool) that runs natively on both
    chip types — this is what makes the "Universal Mac" build work without
    needing Rosetta translation."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["lipo", "-create", str(arm_path), str(intel_path), "-output", str(out_path)],
        check=True,
    )
    shutil.copystat(arm_path, out_path, follow_symlinks=False)


def merge_app_bundles(arm_app: Path, intel_app: Path, out_app: Path) -> None:
    """Build the universal .app bundle: start from a full copy of the arm64
    bundle (folder structure, resources, Info.plist), then walk every file
    and replace the compiled binaries with a merged universal2 version
    (via merge_macho_binary). Non-binary files (templates, static assets)
    are identical between architectures, so they're left as plain copies."""
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
    """Sanity check after merging: fail loudly if the merged binary doesn't
    actually contain both architecture slices, instead of silently shipping
    a broken universal build that only works on one chip type."""
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
    """Build one architecture's .app into a throwaway temp folder (used
    only as an intermediate step for build_universal_copy — the single-arch
    build_mac_copy() below writes straight to the real output folder instead)."""
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
    """Build (or reuse two prebuilt) arm64 + x86_64 copies and fuse them
    into one universal2 app. Building both from scratch only works if this
    Mac can run both architectures natively — pass arm64_app/x86_64_app to
    skip straight to merging when they were built elsewhere (e.g. two
    separate CI runners, one per chip)."""
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
    ID, so macOS quarantines them and blocks the first launch. On current
    macOS this shows as "is damaged and can't be opened" rather than the
    older "unidentified developer" dialog — and neither right-click > Open
    nor System Settings > Open Anyway reliably clears it for apps with no
    Developer ID signature at all. This script itself still needs the
    same one-time `xattr -cr` Terminal fix (see START HERE.txt) before it
    can run — but once run, it clears the quarantine flag on the app and
    FolderPicker so they open normally from then on.
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
  This app isn't from the App Store, so macOS blocks it the first time —
  this is normal and only needs fixing once.

  Fix it with Terminal (always works, one copy-paste, takes 10 seconds):
    1. Open Terminal
    2. Type  cd  then a space, then drag THIS FOLDER (the one this file
       is in) onto the Terminal window — do not type the folder path
       yourself, dragging it in avoids typos — then press Enter
    3. Copy this WHOLE line exactly (all one line) and paste it into
       Terminal, then press Enter:

         xattr -cr . && chmod +x *.command "Phone Reseller CRM.app/Contents/MacOS/PhoneResellerCRM" FolderPicker && open "Phone Reseller CRM.app"

    That single line fixes everything AND opens the CRM in one go — you
    should see it open in your browser right after you press Enter.

  Why not just click "Open Anyway" in System Settings? For an app like
  this one (not from an identified Apple developer), that button often
  doesn't work and macOS instead says "is damaged and can't be opened" —
  that message is misleading, the app isn't actually damaged, but that
  screen has no working fix. The Terminal command above is the real fix,
  and only needs doing this once.

AFTER THE FIRST TIME
────────────────────
  • Just double-click Phone Reseller CRM.app directly — no more warnings
  • If CRM is already running, double-clicking opens the existing session
  • If it does not open, wait 10 seconds and visit http://localhost:5050

WRONG CHIP?
───────────
{wrong_chip}

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
    """Safety check run at the end of every build: fail loudly if any raw
    .py source file (especially generate_key.py, the vendor-only key
    generator) ended up in the customer folder."""
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
    """Full single-architecture (or universal, delegated to
    build_universal_copy) Mac customer-build pipeline: compile with
    PyInstaller, verify the binary is actually the requested architecture,
    assemble the .app + FolderPicker + README + quarantine-fix script, then
    verify no source code leaked into the output."""
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
    """CLI entry point — see the module docstring at the top of this file
    for the exact commands (one per architecture)."""
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

    building_locally = not (args.arm64_app and args.x86_64_app)
    if building_locally:
        _write_license_secret_file()
    try:
        build_mac_copy(args.arch, arm64_app=args.arm64_app, x86_64_app=args.x86_64_app)
    finally:
        # Never leave the plaintext secret lying around in the source tree
        # once the build (successful or not) is done.
        secret_file = ROOT / "license_build_secret.txt"
        if secret_file.is_file():
            secret_file.unlink()


if __name__ == "__main__":
    main()
