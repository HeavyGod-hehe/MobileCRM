#!/bin/bash
# Double-click to build the universal Mac CRM app (Intel + Apple Silicon).

set -euo pipefail

clear
echo ""
echo "  Phone Reseller CRM — Universal Mac Build"
echo "  ────────────────────────────────────────"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "  ERROR: python3 not found."
  exit 1
fi

echo "  Installing build tools (first run only)..."
"$PYTHON" -m pip install -q -r requirements.txt pyinstaller

echo ""
echo "  Building universal app — this can take several minutes..."
echo ""

"$PYTHON" build_customer_mac.py --arch universal

echo ""
echo "  Done. Open this folder:"
echo "    $(cd .. && pwd)/Customer Copy Universal Mac"
echo ""
read -r -p "Press Enter to close..."
