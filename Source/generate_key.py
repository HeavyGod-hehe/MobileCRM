#!/usr/bin/env python3
"""Vendor-only tool: generate an activation key for a client's Hardware ID.

NEVER ship this file or run it on a customer's machine — it's excluded from
every customer build automatically (see build_customer_mac.py /
build_customer_windows_copy.py). Run it on your own computer only.

Usage:
    python3 generate_key.py                     # interactive — prompts you
    python3 generate_key.py AB12CD34EF56AB78     # one-shot, no prompt
    python3 generate_key.py AB12CD34EF56AB78 --client "Ali's Mobile Shop"

Every key you generate is appended to issued_keys.log next to this file
(never committed to git) so you have a record of who has what.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from license_guard import _sign_hardware_id, generate_password_reset_code, get_hardware_id

LOG_FILE = Path(__file__).parent / "issued_keys.log"


def _normalize(raw: str) -> str:
    """Strip whitespace/dashes and uppercase, so it doesn't matter how the
    client copy-pasted their Hardware ID (with dashes, lowercase, extra spaces)."""
    return raw.strip().upper().replace(" ", "").replace("-", "")


def _valid(hw: str) -> bool:
    """A real Hardware ID is always exactly 16 hex characters (see
    get_hardware_id() in license_guard.py) — anything else means it was
    mistyped or copied wrong."""
    return len(hw) == 16 and all(c in "0123456789ABCDEF" for c in hw)


def _log_issued_key(hw: str, key: str, client: str) -> None:
    """Append one line to issued_keys.log so the vendor has a paper trail of
    every key they've ever issued and to whom."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    label = client.strip() or "(no client name given)"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{label}\tHW={hw}\tKEY={key}\n")


def main() -> None:
    """CLI entry point — see the module docstring at the top of this file
    for usage examples. Handles both one-shot (args on the command line)
    and interactive (prompts) modes."""
    parser = argparse.ArgumentParser(
        description="Generate a CRM activation key for a buyer's Hardware ID.",
    )
    parser.add_argument(
        "hardware_id",
        nargs="?",
        help="Client's Hardware ID (16-char hex), shown on their Activation screen. "
        "Omit to be prompted for it.",
    )
    parser.add_argument(
        "--client",
        default="",
        help="Optional client/shop name, saved to issued_keys.log for your records.",
    )
    parser.add_argument(
        "--mine",
        action="store_true",
        help="Show THIS machine's own Hardware ID (for testing the licensing flow yourself).",
    )
    parser.add_argument(
        "--reset-password",
        metavar="USERNAME",
        default=None,
        help="Generate a password-reset code instead of an activation key, for a customer "
        "whose account has no email/OTP configured. Needs the customer's Hardware ID "
        "(same one shown on their login page's forgot-password screen) AND their exact "
        "CRM username.",
    )
    args = parser.parse_args()

    if args.mine:
        print(f"This machine's Hardware ID: {get_hardware_id()}")
        return

    raw = args.hardware_id
    client = args.client
    if not raw:
        raw = input("Paste the client's Hardware ID (from their Activation screen): ")
    if not client and not args.hardware_id:
        client = input("Client / shop name (optional, press Enter to skip): ")

    hw = _normalize(raw)
    if not _valid(hw):
        print(
            f"ERROR: '{raw}' isn't a valid Hardware ID — it should be exactly "
            "16 letters/numbers (0-9, A-F), copied exactly as shown on their screen.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.reset_password is not None:
        username = args.reset_password.strip() or input("Customer's exact CRM username: ").strip()
        code = generate_password_reset_code(hw, username)
        _log_issued_key(hw, f"PWRESET({username})={code}", client)
        print()
        print("=" * 50)
        print(f"Hardware ID:   {hw}")
        print(f"Username:      {username}")
        print(f"Reset Code:    {code}")
        print("=" * 50)
        print(f"\nSend the Reset Code above to the client. Saved to {LOG_FILE.name} for your records.")
        return

    key = _sign_hardware_id(hw)
    _log_issued_key(hw, key, client)

    print()
    print("=" * 50)
    print(f"Hardware ID:     {hw}")
    print(f"Activation Key:  {key}")
    print("=" * 50)
    print(f"\nSend the Activation Key above to the client. Saved to {LOG_FILE.name} for your records.")


if __name__ == "__main__":
    main()
