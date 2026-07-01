#!/usr/bin/env python3
"""Backward-compatible wrapper — builds Apple Silicon (M chip) customer copy."""

from build_customer_mac import build_mac_copy

if __name__ == "__main__":
    build_mac_copy("arm64")
