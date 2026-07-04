"""License activation guard for Phone Reseller CRM.

Threat model note (read this before touching the secret logic below): this
is a client-side check in a program that runs entirely on the customer's own
machine. No secret embedded in a Python/PyInstaller build can be made
un-extractable to a sufficiently determined reverse engineer — decompiling a
frozen build with PyInstaller's own bundled tools takes only a few lines of
Python (verified). Nothing here claims to be uncrackable. What it does
protect against: casual copying/sharing, and it lets the vendor rotate the
signing secret on every release (via CRM_LICENSE_SECRET, set as a CI secret
— never committed to source) without ever invalidating keys already issued
to paying customers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from app_paths import customer_data_dir


def _fallback_secret() -> str:
    """Default secret used when CRM_LICENSE_SECRET isn't set. Split across
    two base64 fragments so a naive scan of the compiled module's string
    constants doesn't hand over the whole value in one read — this raises
    the bar slightly, it does not stop real reverse engineering (see module
    docstring)."""
    return (
        base64.b64decode("Q1JNLVJlc2VsbGVyLXYyLWQxODMwMmVjYzdjNTc4N2Q=").decode()
        + base64.b64decode("OThkMDQwZTAzZmMzNjhiNDhkYmJkMmVhMmUyOWZiMGM=").decode()
    )


# The FIRST secret in this tuple is the one used to SIGN new activation keys
# (generate_key.py always signs with _LICENSE_SECRETS[0]). Every secret in
# the tuple is accepted when VERIFYING a key, so changing CRM_LICENSE_SECRET
# for a future release rotates the signing secret going forward without
# breaking any key issued under an older secret.
#
# Vendor: set CRM_LICENSE_SECRET as a CI secret (see HOW_TO_RELEASE.md)
# before building a release — a secret that only lives in your build
# pipeline, never in source control, is the one change here that actually
# matters. Without it, every build silently falls back to the value below,
# which is visible to anyone who decompiles the app (as this file's
# docstring explains). If you ever add a NEW secret this way after
# customers are already activated, append the old one(s) as extra legacy
# entries below instead of removing them, so their keys keep working.
_env_secret = os.environ.get("CRM_LICENSE_SECRET")
_LICENSE_SECRETS = (_env_secret, _fallback_secret()) if _env_secret else (_fallback_secret(),)
_LICENSE_SECRET = _LICENSE_SECRETS[0]  # kept for any external reference to the active secret


def _license_dir() -> Path:
    if os.environ.get("CRM_LICENSE_PATH"):
        return Path(os.environ["CRM_LICENSE_PATH"]).expanduser().resolve().parent
    data_dir = customer_data_dir()
    if data_dir:
        return data_dir
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).parent


def _legacy_license_file() -> Path | None:
    home = Path.home()
    candidates = [
        home / "Library" / "Application Support" / "Phone Reseller CRM" / "license.json",
        Path(sys.executable).resolve().parent / "license.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


LICENSE_FILE = Path(
    os.environ.get("CRM_LICENSE_PATH", str(_license_dir() / "license.json"))
)


def get_hardware_id() -> str:
    """Return a stable, human-readable hardware fingerprint for this machine."""
    node = uuid.getnode()
    digest = hashlib.sha256(f"crm-hw:{node}".encode()).hexdigest()
    return digest[:16].upper()


def _sign_with(hardware_id: str, secret: str) -> str:
    hw = hardware_id.strip().upper()
    sig = hmac.new(secret.encode(), hw.encode(), hashlib.sha256).hexdigest()
    return f"{hw}-{sig[:24].upper()}"


def _sign_hardware_id(hardware_id: str) -> str:
    """Sign with the ACTIVE secret only — this is what generate_key.py calls
    to issue new keys."""
    return _sign_with(hardware_id, _LICENSE_SECRETS[0])


def verify_activation_key(hardware_id: str, activation_key: str) -> bool:
    """Accept a key signed with the active secret OR any legacy secret —
    lets the vendor rotate CRM_LICENSE_SECRET for future releases without
    invalidating keys already issued to customers under an older secret."""
    if not hardware_id or not activation_key:
        return False
    submitted = activation_key.strip().upper()
    return any(
        hmac.compare_digest(_sign_with(hardware_id, secret), submitted)
        for secret in _LICENSE_SECRETS
    )


def load_saved_license() -> dict | None:
    if not LICENSE_FILE.is_file():
        legacy = _legacy_license_file()
        if legacy and legacy.resolve() != LICENSE_FILE.resolve():
            LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, LICENSE_FILE)
    if not LICENSE_FILE.is_file():
        return None
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("activation_key"):
            return data
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return None


def save_license(activation_key: str) -> None:
    hw = get_hardware_id()
    if not verify_activation_key(hw, activation_key):
        raise ValueError("Invalid activation key for this machine")
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file and rename into place — a crash mid-write can't
    # leave a half-written, corrupted license.json this way (rename is atomic).
    tmp_path = LICENSE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps({"hardware_id": hw, "activation_key": activation_key.strip().upper()}, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(LICENSE_FILE)


def is_licensed() -> bool:
    saved = load_saved_license()
    if not saved:
        return False
    hw = get_hardware_id()
    return verify_activation_key(hw, saved.get("activation_key", ""))
