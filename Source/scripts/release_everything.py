#!/usr/bin/env python3
"""
One-click vendor release: push to GitHub, trigger CI release, rebuild local Mac app.

Usage:
  python3 scripts/release_everything.py          # push + build + open Actions
  python3 scripts/release_everything.py --bump    # bump patch in VERSION first
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # MobileCRM repo root
SOURCE = ROOT / "Source"
VERSION_FILE = SOURCE / "VERSION"
REPO = "HeavyGod-hehe/MobileCRM"
ACTIONS_URL = f"https://github.com/{REPO}/actions/workflows/release.yml"
RELEASES_URL = f"https://github.com/{REPO}/releases"


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"  → {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd or ROOT, check=check)


def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def bump_patch(version: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not m:
        raise SystemExit(f"VERSION must be x.y.z (got {version!r})")
    major, minor, patch = map(int, m.groups())
    return f"{major}.{minor}.{patch + 1}"


def git_push() -> None:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status.strip():
        run(["git", "add", "-A"])
        ver = read_version()
        run(["git", "commit", "-m", f"Release {ver}"])
    ahead = subprocess.check_output(
        ["git", "rev-list", "--count", f"origin/{branch}..HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    if ahead != "0":
        run(["git", "push", "-u", "origin", branch])
    else:
        print("  → Git already up to date on remote.")


def gh_token() -> str | None:
    try:
        out = subprocess.check_output(["gh", "auth", "token"], stderr=subprocess.DEVNULL, text=True)
        return out.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    token = __import__("os").environ.get("GITHUB_TOKEN", "").strip()
    return token or None


def trigger_workflow(branch: str) -> bool:
    token = gh_token()
    if not token:
        print("  → gh not installed — push may have started the workflow if VERSION changed.")
        return False
    payload = json.dumps({"ref": branch}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/workflows/release.yml/dispatches",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
        print("  → Release workflow triggered on GitHub.")
        return True
    except urllib.error.HTTPError as e:
        print(f"  → Could not trigger workflow via API ({e.code}). Push may still have started it.")
        return False


def detect_mac_arch() -> str:
    import platform

    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return "x86_64"


def build_and_copy_desktop(version: str) -> Path:
    arch = detect_mac_arch()
    arch_label = {"arm64": "Apple Silicon", "x86_64": "Intel Mac"}[arch]
    print(f"\n  Building local Mac app ({arch_label}) — several minutes…")
    run([sys.executable, "build_customer_mac.py", "--arch", arch], cwd=SOURCE)

    src_names = {
        "arm64": "Customer Copy Apple Silicon",
        "x86_64": "Customer Copy Intel Mac",
    }
    src = ROOT / src_names[arch]
    dest = Path.home() / "Desktop" / f"Phone Reseller CRM v{version}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    print(f"\n  ✓ Desktop copy ready:\n    {dest}\n")
    return dest


def open_urls() -> None:
    for url in (ACTIONS_URL, RELEASES_URL):
        subprocess.run(["open", url], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="One-click CRM release")
    parser.add_argument(
        "--bump",
        action="store_true",
        help="Bump patch version in Source/VERSION before push",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip local Mac build (CI only)",
    )
    args = parser.parse_args()

    print("\n  Phone Reseller CRM — Release Everything")
    print("  " + "─" * 40 + "\n")

    if args.bump:
        old = read_version()
        new = bump_patch(old)
        VERSION_FILE.write_text(new + "\n", encoding="utf-8")
        print(f"  Version: {old} → {new}")
        run(["git", "add", str(VERSION_FILE)])
        run(["git", "commit", "-m", f"Release {new}"])

    version = read_version()
    print(f"  Releasing v{version}\n")

    print("  [1/3] Pushing to GitHub…")
    git_push()

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    print("\n  [2/3] Starting GitHub release build…")
    trigger_workflow(branch)

    if not args.skip_build and sys.platform == "darwin":
        print("\n  [3/3] Building app for your Desktop…")
        build_and_copy_desktop(version)
    else:
        print("\n  [3/3] Skipped local build.")

    print("  Opening GitHub Actions in your browser…")
    open_urls()
    print("\n  Done. GitHub builds Windows + all Mac types (~15 min).")
    print("  Customers will see the update in Settings → Software Update.\n")


if __name__ == "__main__":
    main()
