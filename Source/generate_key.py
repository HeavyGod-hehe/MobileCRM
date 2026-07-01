#!/usr/bin/env python3
"""Vendor-only utility: generate activation keys from a buyer's Hardware ID."""

from __future__ import annotations

import argparse
import sys

from license_guard import _sign_hardware_id, get_hardware_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a CRM activation key for a buyer's Hardware ID.",
    )
    parser.add_argument(
        "hardware_id",
        nargs="?",
        help="Buyer's Hardware ID (16-char hex). Omit to show this machine's ID.",
    )
    args = parser.parse_args()

    if args.hardware_id:
        hw = args.hardware_id.strip().upper()
        if len(hw) != 16 or not all(c in "0123456789ABCDEF" for c in hw):
            print("ERROR: Hardware ID must be 16 hexadecimal characters.", file=sys.stderr)
            sys.exit(1)
    else:
        hw = get_hardware_id()
        print(f"This machine Hardware ID: {hw}\n")

    key = _sign_hardware_id(hw)
    print(f"Activation Key: {key}")


if __name__ == "__main__":
    main()
