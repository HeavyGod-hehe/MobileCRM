"""License activation guard for Phone Reseller CRM."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from app_paths import customer_data_dir

# Must match generate_key.py — change before distributing builds.
_LICENSE_SECRET = os.environ.get(
    "CRM_LICENSE_SECRET",
    "CRM-Reseller-v1-9f3a2b1c8d7e6f5a4b3c2d1e0f9a8b7",
)


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


def _sign_hardware_id(hardware_id: str) -> str:
    hw = hardware_id.strip().upper()
    sig = hmac.new(
        _LICENSE_SECRET.encode(),
        hw.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{hw}-{sig[:24].upper()}"


def verify_activation_key(hardware_id: str, activation_key: str) -> bool:
    if not hardware_id or not activation_key:
        return False
    expected = _sign_hardware_id(hardware_id)
    return hmac.compare_digest(expected, activation_key.strip().upper())


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
    LICENSE_FILE.write_text(
        json.dumps({"hardware_id": hw, "activation_key": activation_key.strip().upper()}, indent=2),
        encoding="utf-8",
    )


def is_licensed() -> bool:
    saved = load_saved_license()
    if not saved:
        return False
    hw = get_hardware_id()
    return verify_activation_key(hw, saved.get("activation_key", ""))
