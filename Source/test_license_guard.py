"""Regression test for the "asks to activate every 2-3 days" bug.

What was wrong: get_hardware_id() used to be built from uuid.getnode(),
which reads the computer's network MAC address. Windows randomizes Wi-Fi MAC
addresses for privacy and rotates them every so often, and plugging in a
VPN/Docker/virtual network adapter can also change which MAC Python picks.
Every time that MAC changed, the "hardware ID" changed too, so the
customer's saved activation key (signed for the OLD hardware ID) stopped
matching -> the app thought the machine was never activated and asked again.

The fix (see license_guard.py) reads Windows' own stable per-install ID
(the registry MachineGuid) instead, which does not change when the network
changes. This test proves that: even if uuid.getnode() returns a different
value on every call (simulating MAC rotation), get_hardware_id() must still
return the SAME value every time.
"""

from __future__ import annotations

import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

import license_guard as lic  # noqa: E402


def test_hardware_id_is_stable_even_if_mac_address_changes(monkeypatch):
    # Make every call to uuid.getnode() return a different, random-looking
    # number - this simulates Windows rotating the Wi-Fi MAC address.
    fake_mac_values = iter([111111111111, 222222222222, 333333333333])
    monkeypatch.setattr(lic.uuid, "getnode", lambda: next(fake_mac_values))

    # A fresh, un-cached hardware ID computation must ignore the MAC and
    # come out the same every time, because it's now based on a value that
    # doesn't change with the network (MachineGuid on Windows, IOPlatformUUID
    # on Mac).
    lic.get_hardware_id.cache_clear()
    first = lic.get_hardware_id()
    lic.get_hardware_id.cache_clear()
    second = lic.get_hardware_id()
    lic.get_hardware_id.cache_clear()
    third = lic.get_hardware_id()

    assert first == second == third


def test_activation_key_survives_hardware_id_recompute(monkeypatch, tmp_path):
    # End-to-end version of the same bug: activate once, then simulate the
    # MAC changing, and confirm the saved key is STILL accepted.
    monkeypatch.setattr(lic, "LICENSE_FILE", tmp_path / "license.json")
    lic.get_hardware_id.cache_clear()

    hw = lic.get_hardware_id()
    key = lic._sign_hardware_id(hw)
    lic.save_license(key)
    assert lic.is_licensed() is True

    # Now simulate the network MAC changing (this used to break activation).
    monkeypatch.setattr(lic.uuid, "getnode", lambda: 999999999999)
    lic.get_hardware_id.cache_clear()

    assert lic.is_licensed() is True


def test_password_reset_code_verifies_for_matching_hwid_and_username():
    hw = "ABCD1234EF567890"
    code = lic.generate_password_reset_code(hw, "TalhaShop")
    assert lic.verify_password_reset_code(hw, "TalhaShop", code)
    # Username matching is case-insensitive (usernames are looked up
    # COLLATE NOCASE in the db layer), hardware ID matching is not case
    # sensitive either since it's always normalized to uppercase.
    assert lic.verify_password_reset_code(hw.lower(), "talhashop", code)


def test_password_reset_code_rejects_wrong_username_or_hwid_or_code():
    hw = "ABCD1234EF567890"
    code = lic.generate_password_reset_code(hw, "TalhaShop")
    assert not lic.verify_password_reset_code(hw, "SomeoneElse", code)
    assert not lic.verify_password_reset_code("1111222233334444", "TalhaShop", code)
    assert not lic.verify_password_reset_code(hw, "TalhaShop", code[:-1] + ("0" if code[-1] != "0" else "1"))


def test_password_reset_code_is_not_interchangeable_with_activation_key():
    # A license activation key for this hardware ID must NOT also verify as
    # a valid password-reset code, and vice versa — the "PWRESET:" prefix in
    # the signed message keeps the two domains separate even though both are
    # signed with the same secret tuple.
    hw = "ABCD1234EF567890"
    activation_key = lic._sign_hardware_id(hw)
    assert not lic.verify_password_reset_code(hw, "TalhaShop", activation_key)

    reset_code = lic.generate_password_reset_code(hw, "TalhaShop")
    assert not lic.verify_activation_key(hw, reset_code)
