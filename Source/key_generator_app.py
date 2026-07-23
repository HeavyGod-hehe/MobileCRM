#!/usr/bin/env python3
"""Interactive entry point for the packaged Serial Key Generator .exe.

generate_key.py itself is argparse/one-shot (built for scripting) and would
exit and close its console window the instant it prints a key — no good for
a double-clicked exe where the vendor needs to actually read and copy the
key. This wraps the same signing logic in a menu loop that stays open,
mirroring "Generate License Key.bat" (the source-tree equivalent).

VENDOR ONLY — never ship this exe or run it on a customer's machine.
"""

from __future__ import annotations

from generate_key import _log_issued_key, _normalize, _valid
from license_guard import _sign_hardware_id, generate_password_reset_code, get_hardware_id


def _generate_for(hw_raw: str, client: str) -> None:
    hw = _normalize(hw_raw)
    if not _valid(hw):
        print(
            f"\n  ERROR: '{hw_raw}' isn't a valid Hardware ID — it should be "
            "exactly 16 letters/numbers (0-9, A-F), copied exactly as shown "
            "on their Activation screen.\n"
        )
        return
    key = _sign_hardware_id(hw)
    _log_issued_key(hw, key, client)
    print()
    print("=" * 50)
    print(f"  Hardware ID:     {hw}")
    print(f"  Activation Key:  {key}")
    print("=" * 50)
    print("\n  Send the Activation Key above to the client.")
    print("  Saved to issued_keys.log (next to this exe) for your records.\n")


def _generate_reset_code_for(hw_raw: str, username: str, client: str) -> None:
    hw = _normalize(hw_raw)
    if not _valid(hw):
        print(
            f"\n  ERROR: '{hw_raw}' isn't a valid Hardware ID — it should be "
            "exactly 16 letters/numbers (0-9, A-F), copied exactly as shown "
            "on their login page's forgot-password screen.\n"
        )
        return
    username = username.strip()
    if not username:
        print("\n  ERROR: a username is required — the customer's exact CRM login name.\n")
        return
    code = generate_password_reset_code(hw, username)
    _log_issued_key(hw, f"PWRESET({username})={code}", client)
    print()
    print("=" * 50)
    print(f"  Hardware ID:   {hw}")
    print(f"  Username:      {username}")
    print(f"  Reset Code:    {code}")
    print("=" * 50)
    print("\n  Send the Reset Code above to the client.")
    print("  Saved to issued_keys.log (next to this exe) for your records.\n")


def main() -> None:
    print()
    print("  Phone Reseller CRM - Vendor License Key Generator")
    print("  =================================================")
    print()
    print("  VENDOR ONLY - do not share this program with customers.")

    while True:
        print()
        print("  1 - Generate key for THIS computer")
        print("  2 - Generate key for a CUSTOMER Hardware ID")
        print("  3 - Generate a PASSWORD RESET code for a customer")
        print("  Q - Quit")
        print()
        choice = input("  Choose an option (1, 2, 3, or Q): ").strip().upper()

        if choice == "Q":
            break
        elif choice == "1":
            print("\n  This computer:")
            print("  --------------")
            _generate_for(get_hardware_id(), "(this machine)")
        elif choice == "2":
            hwid = input("\n  Enter customer Hardware ID (16 hex characters): ").strip()
            if not hwid:
                print("  No Hardware ID entered.")
                continue
            client = input("  Client / shop name (optional, press Enter to skip): ").strip()
            print("\n  Customer license:")
            print("  -----------------")
            _generate_for(hwid, client)
        elif choice == "3":
            hwid = input("\n  Enter customer Hardware ID (from their login page): ").strip()
            if not hwid:
                print("  No Hardware ID entered.")
                continue
            username = input("  Customer's exact CRM username: ").strip()
            if not username:
                print("  No username entered.")
                continue
            client = input("  Client / shop name (optional, press Enter to skip): ").strip()
            print("\n  Password reset code:")
            print("  ---------------------")
            _generate_reset_code_for(hwid, username, client)
        else:
            print("  Invalid choice. Please enter 1, 2, 3, or Q.")
            continue

        again = input("  Generate another key? (Y/N): ").strip().upper()
        if again not in ("Y", "YES"):
            break

    print("\n  Done.\n")
    input("  Press Enter to exit...")


if __name__ == "__main__":
    main()
