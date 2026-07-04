#!/usr/bin/env python3
"""Write Source/releases/version.json for the in-app auto-updater."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "releases" / "version.json"


def build_manifest(version: str, repo: str, tag: str, notes: str = "") -> dict:
    base = f"https://github.com/{repo}/releases/download/{tag}"
    return {
        "version": version,
        "release_notes": notes or (
            f"Phone Reseller CRM {version} is ready. "
            "Open Settings → Software Update → Install update. Your Data folder is kept."
        ),
        "page_url": f"https://github.com/{repo}/releases/tag/{tag}",
        "downloads": {
            "windows": {"url": f"{base}/PhoneResellerCRM-Windows-{version}.zip"},
            "mac_intel": {"url": f"{base}/PhoneResellerCRM-IntelMac-{version}.zip"},
            "mac_arm64": {"url": f"{base}/PhoneResellerCRM-AppleSilicon-{version}.zip"},
            "mac_universal": {"url": f"{base}/PhoneResellerCRM-UniversalMac-{version}.zip"},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo", required=True, help="owner/name e.g. HeavyGod-hehe/MobileCRM-releases")
    parser.add_argument("--tag", required=True, help="release tag e.g. v2.3.0")
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--output", default=str(OUT),
        help="Where to write version.json (default: Source/releases/version.json)",
    )
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(build_manifest(args.version, args.repo, args.tag, args.notes), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
