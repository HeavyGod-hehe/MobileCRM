#!/usr/bin/env python3
"""Write Source/releases/version.json for the in-app auto-updater."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "releases" / "version.json"

# Platform key -> the zip filename release.yml packages it as (see its
# "Package release zips" step). Used to look up each artifact's checksum
# when --artifacts-dir is given.
_ZIP_NAMES = {
    "windows": "PhoneResellerCRM-Windows-{version}.zip",
    "mac_intel": "PhoneResellerCRM-IntelMac-{version}.zip",
    "mac_arm64": "PhoneResellerCRM-AppleSilicon-{version}.zip",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    version: str, repo: str, tag: str, notes: str = "", artifacts_dir: Path | None = None,
) -> dict:
    base = f"https://github.com/{repo}/releases/download/{tag}"
    downloads = {}
    for key, name_tpl in _ZIP_NAMES.items():
        name = name_tpl.format(version=version)
        entry = {"url": f"{base}/{name}"}
        if artifacts_dir:
            zip_path = artifacts_dir / name
            if zip_path.is_file():
                entry["sha256"] = _sha256_file(zip_path)
        downloads[key] = entry
    return {
        "version": version,
        "release_notes": notes or (
            f"Phone Reseller CRM {version} is ready. "
            "Open Settings → Software Update → Install update. Your Data folder is kept."
        ),
        "page_url": f"https://github.com/{repo}/releases/tag/{tag}",
        "downloads": downloads,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo", required=True, help="owner/name e.g. HeavyGod-hehe/MobileCRM-releases")
    parser.add_argument("--tag", required=True, help="release tag e.g. v2.3.0")
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--artifacts-dir", default=None,
        help="Folder containing the just-built release zips (dist/ in release.yml) -- "
             "when given, each download entry gets a sha256 checksum of its actual zip file, "
             "so update_service.py and validate_release.py can catch a corrupted download/build.",
    )
    parser.add_argument(
        "--output", default=str(OUT),
        help="Where to write version.json (default: Source/releases/version.json)",
    )
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            build_manifest(args.version, args.repo, args.tag, args.notes, artifacts_dir),
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
