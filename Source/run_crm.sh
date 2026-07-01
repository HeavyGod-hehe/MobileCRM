#!/bin/bash
# Shared CRM launcher — used by .command, .app, and .bat (via git bash)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"
VENV="$SCRIPT_DIR/venv"
REQ="$SCRIPT_DIR/requirements.txt"
APP="$SCRIPT_DIR/app.py"

die() {
  echo ""
  echo "  ERROR: $1"
  echo ""
  exit 1
}

# macOS often blocks Terminal from reading Documents/Downloads without permission
if [ ! -r "$APP" ]; then
  echo ""
  echo "  macOS blocked access to this folder (common in Documents)."
  echo ""
  echo "  FIX — choose one:"
  echo "    A) System Settings → Privacy & Security → Files and Folders"
  echo "       → enable Terminal (or iTerm) → Documents"
  echo "    B) Move the CRM folder to your home folder:"
  echo "       ~/Phone Reseller CRM   (recommended — already set up if you ran setup)"
  echo ""
  die "Cannot read app.py in: $SCRIPT_DIR"
fi

# Prefer project virtualenv (avoids system pip permission issues)
if [ ! -x "$VENV/bin/python3" ]; then
  echo "  Creating virtual environment (first run only)..."
  if ! "$PYTHON" -m venv "$VENV" 2>/dev/null; then
    echo "  Could not create venv — trying system Python..."
  fi
fi

if [ -x "$VENV/bin/python3" ]; then
  PYTHON="$VENV/bin/python3"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi

if ! "$PYTHON" -c "import flask" 2>/dev/null; then
  echo "  Installing dependencies (first run only)..."
  if ! "$PYTHON" -m pip install -r "$REQ" -q 2>/dev/null; then
    echo ""
    echo "  pip install failed (macOS privacy restriction)."
    echo "  Open Terminal manually and run:"
    echo "    cd \"$SCRIPT_DIR\""
    echo "    python3 -m venv venv && source venv/bin/activate"
    echo "    pip install -r requirements.txt"
    echo "    python app.py"
    echo ""
    die "Dependency install failed"
  fi
fi

echo "  Starting server — browser opens at http://localhost:5050"
echo "  Keep this window open. Press Ctrl+C to stop."
echo ""

exec "$PYTHON" "$APP"
