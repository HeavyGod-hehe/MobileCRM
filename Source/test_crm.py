#!/usr/bin/env python3
"""
Standalone stress-test utility — seeds 100 mock rows into all CRM tables.

Usage:
  python test_crm.py
  python test_crm.py --count 200
"""

from __future__ import annotations

import sys

from test_crm_performance import main as performance_main


def main() -> None:
    if "--count" not in sys.argv:
        sys.argv.extend(["--count", "100"])
    if "--mode" not in sys.argv:
        sys.argv.extend(["--mode", "db"])
    performance_main()


if __name__ == "__main__":
    main()
