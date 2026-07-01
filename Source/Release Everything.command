#!/bin/bash
# Double-click: push to GitHub, start release build, rebuild Desktop app.

set -euo pipefail
clear
echo ""
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
python3 scripts/release_everything.py "$@"
echo ""
read -r -p "Press Enter to close…"
