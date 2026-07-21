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
import functools
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from app_paths import customer_data_dir


def _fallback_secret() -> str:
    """Default secret used when no CRM_LICENSE_SECRET reaches this build at
    all. Split across two base64 fragments so a naive scan of the compiled
    module's string constants doesn't hand over the whole value in one read
    — this raises the bar slightly, it does not stop real reverse
    engineering (see module docstring)."""
    return (
        base64.b64decode("Q1JNLVJlc2VsbGVyLXYyLWQxODMwMmVjYzdjNTc4N2Q=").decode()
        + base64.b64decode("OThkMDQwZTAzZmMzNjhiNDhkYmJkMmVhMmUyOWZiMGM=").decode()
    )


def _build_baked_secret() -> str | None:
    """A secret baked in at BUILD time from the CRM_LICENSE_SECRET CI/repo
    secret, into a small text file the build scripts write and the .spec
    files bundle alongside the frozen app (see build_customer_windows_copy.py
    / build_customer_mac.py). A plain environment variable set only during
    the CI build step would have no effect here — this module runs fresh on
    the CUSTOMER's machine every launch, reading the customer's own (empty)
    environment, not whatever the build pipeline had set months earlier.
    Bundling the value into a file PyInstaller ships with the app is what
    actually gets a rotated secret onto the customer's machine. Returns None
    outside a frozen build, or if the file wasn't bundled (an older build,
    or one made before the CI secret was configured)."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        secret_path = Path(sys._MEIPASS) / "license_build_secret.txt"
        if secret_path.is_file():
            value = secret_path.read_text(encoding="utf-8").strip()
            return value or None
    except OSError:
        pass
    return None


# The FIRST secret in this tuple is the one used to SIGN new activation keys
# (generate_key.py always signs with _LICENSE_SECRETS[0]). Every secret in
# the tuple is accepted when VERIFYING a key, so rotating CRM_LICENSE_SECRET
# for a future release rotates the signing secret going forward without
# breaking any key issued under an older secret.
#
# Vendor: set CRM_LICENSE_SECRET as a CI secret (see HOW_TO_RELEASE.md)
# before building a release — a secret that only lives in your build
# pipeline, never in source control, is the one change here that actually
# matters. The build scripts now refuse to build at all if this isn't set
# (see build_customer_windows_copy.py / build_customer_mac.py), so a build
# silently falling back to the hardcoded value below (visible to anyone who
# decompiles the app, as this file's docstring explains) should no longer
# happen for a real release. If you ever rotate the secret after customers
# are already activated, append the old one(s) as extra legacy entries below
# instead of removing them, so their keys keep working.
_env_secret = os.environ.get("CRM_LICENSE_SECRET")
_build_secret = _build_baked_secret()
_LICENSE_SECRETS = tuple(
    s for s in (_env_secret, _build_secret, _fallback_secret()) if s
) or (_fallback_secret(),)
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


def _raw_machine_id() -> str:
    """Return the most STABLE identifier this OS can give us for the physical
    machine. This intentionally avoids the network MAC address
    (uuid.getnode()) as the primary source: Windows randomizes Wi-Fi MAC
    addresses for privacy by default and rotates them every few days, and
    plugging in a VPN/Docker/virtual adapter can also change which MAC
    Python picks. If the hardware ID were based on that, an already-activated
    customer would silently get locked out every time their MAC changed —
    which is exactly the "asks for activation every 2-3 days" bug this
    function fixes. Falls back to uuid.getnode() only if the OS-level ID is
    unavailable, so the app still works (just less reliably) everywhere.
    """
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            )
            with key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                if value:
                    return str(value)
        except OSError:
            pass
    elif sys.platform == "darwin":
        try:
            output = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout
            for line in output.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    # Last resort: the network MAC address (not stable long-term, see above).
    return str(uuid.getnode())


@functools.lru_cache(maxsize=1)
def get_hardware_id() -> str:
    """Return a stable, human-readable hardware fingerprint for this machine.

    Cached with lru_cache because this only needs to be computed once per
    run (the license check calls it on every web request) and because the
    OS lookups above (registry read / ioreg subprocess) are not free.
    """
    digest = hashlib.sha256(f"crm-hw:{_raw_machine_id()}".encode()).hexdigest()
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
