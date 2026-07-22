#!/usr/bin/env python3
"""Validate a version.json release manifest before it's published.

Bug #10: nothing checked version.json's shape before it was committed to
the public releases repo. A malformed manifest (missing field, bad URL,
wrong version format) wouldn't fail CI -- it would silently ship, and
every customer's in-app updater would either crash or silently stop
offering updates the next time it checked. This is meant to run in CI
right after generate_version_manifest.py and before that file is
committed, so a bad manifest fails the release job loudly instead.

Usage:
  python validate_release.py path/to/version.json
  python validate_release.py path/to/version.json --artifacts-dir dist
    (also verifies each download's sha256, if present, against the real
    zip file in that directory)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([.-][0-9A-Za-z]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_PLATFORMS = ("windows", "mac_intel", "mac_arm64")


class ManifestError(ValueError):
    """Raised for any manifest problem; message is shown to the CI log as-is."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_url_format(url, where: str) -> None:
    if not isinstance(url, str) or not url.strip():
        raise ManifestError(f"{where}: url is missing or not a string")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ManifestError(f"{where}: url is not a well-formed http(s) URL: {url!r}")


def validate_manifest(manifest, *, artifacts_dir: Path | None = None) -> list[str]:
    """Returns a list of warnings (non-fatal); raises ManifestError on
    anything that would actually break the updater."""
    warnings: list[str] = []

    if not isinstance(manifest, dict):
        raise ManifestError("Manifest root must be a JSON object")

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ManifestError("Missing or empty required field: version")
    if not SEMVER_RE.match(version.strip()):
        raise ManifestError(
            f"version {version!r} is not a valid semver-ish string (expected e.g. '2.4.12')"
        )

    for field in ("release_notes", "page_url"):
        if field in manifest and not isinstance(manifest[field], str):
            raise ManifestError(f"{field} must be a string if present")
    if "page_url" in manifest and manifest["page_url"]:
        _validate_url_format(manifest["page_url"], "page_url")

    downloads = manifest.get("downloads")
    if not isinstance(downloads, dict) or not downloads:
        raise ManifestError("Missing or empty required field: downloads (must be an object)")

    missing_platforms = [p for p in REQUIRED_PLATFORMS if p not in downloads]
    if missing_platforms:
        raise ManifestError(f"downloads is missing required platform(s): {missing_platforms}")

    for platform, entry in downloads.items():
        where = f"downloads.{platform}"
        if not isinstance(entry, dict):
            raise ManifestError(f"{where} must be an object, got {type(entry).__name__}")
        _validate_url_format(entry.get("url"), where)

        sha256 = entry.get("sha256")
        if sha256 is None:
            warnings.append(f"{where}: no sha256 checksum present (older manifest format)")
        elif not isinstance(sha256, str) or not SHA256_RE.match(sha256):
            raise ManifestError(f"{where}.sha256 is not a valid 64-character hex string: {sha256!r}")
        elif artifacts_dir:
            zip_name = entry["url"].rsplit("/", 1)[-1]
            zip_path = artifacts_dir / zip_name
            if not zip_path.is_file():
                warnings.append(
                    f"{where}: manifest has a checksum but {zip_path} wasn't found to verify it against"
                )
            else:
                actual = _sha256_file(zip_path)
                if actual != sha256:
                    raise ManifestError(
                        f"{where}: checksum mismatch -- manifest says {sha256}, "
                        f"actual file {zip_path.name} hashes to {actual}. "
                        "The release artifact does not match what the manifest promises."
                    )

    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_path", help="Path to version.json to validate")
    parser.add_argument(
        "--artifacts-dir", default=None,
        help="Folder with the actual release zips, to verify checksums against (optional)",
    )
    args = parser.parse_args()

    path = Path(args.manifest_path)
    if not path.is_file():
        print(f"ERROR: manifest not found: {path}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None
    try:
        warnings = validate_manifest(manifest, artifacts_dir=artifacts_dir)
    except ManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"WARNING: {w}")
    print(f"OK: {path} is a valid release manifest (version {manifest['version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
