#!/bin/bash
# Double-click this file on your Mac to build Phone Reseller CRM locally.
# Place the whole "Final Software" folder in ~/Downloads first.

set -euo pipefail

FINAL_DIR="${HOME}/Downloads/Final Software"
REPO_DIR="${FINAL_DIR}/MobileCRM"
SOURCE_DIR="${REPO_DIR}/Source"
OUT_DIR="${FINAL_DIR}/Phone Reseller CRM (Mac Universal)"

clear
echo ""
echo "  Phone Reseller CRM — Mac Builder"
echo "  ================================"
echo ""
echo "  This builds the app on YOUR Mac (Intel + Apple Silicon)."
echo "  Output: ${OUT_DIR}"
echo ""

if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERROR: This script only runs on macOS."
  read -r -p "Press Enter to close..."
  exit 1
fi

mkdir -p "${FINAL_DIR}"

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Source not found at:"
  echo "  ${SOURCE_DIR}"
  echo ""
  echo "Download the source zip from GitHub Releases and unzip it into:"
  echo "  ~/Downloads/Final Software/"
  echo ""
  read -r -p "Press Enter to close..."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not installed."
  echo "Install Python 3.12 from https://www.python.org/downloads/macos/"
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "Step 1/4 — Installing Python packages..."
python3 -m pip install --upgrade pip
python3 -m pip install -r "${SOURCE_DIR}/requirements.txt" pyinstaller

echo ""
echo "Step 2/4 — Building Apple Silicon + Intel slices (this takes a few minutes)..."
cd "${SOURCE_DIR}"

ARCH="$(uname -m)"
if [[ "${ARCH}" == "arm64" ]]; then
  python3 build_customer_mac.py --arch arm64
  echo ""
  echo "Step 3/4 — Building Intel slice via Rosetta..."
  if ! arch -x86_64 true 2>/dev/null; then
    echo "Installing Rosetta (one-time, needs your password)..."
    softwareupdate --install-rosetta --agree-to-license || true
  fi
  arch -x86_64 python3 -m pip install --upgrade pip
  arch -x86_64 python3 -m pip install -r requirements.txt pyinstaller
  arch -x86_64 python3 build_customer_mac.py --arch x86_64
  python3 build_customer_universal_mac.py \
    --arm64-dir "${REPO_DIR}/Customer Copy Apple Silicon" \
    --intel-dir "${REPO_DIR}/Customer Copy Intel Mac" \
    --out "${OUT_DIR}"
elif [[ "${ARCH}" == "x86_64" ]]; then
  python3 build_customer_mac.py --arch x86_64
  mkdir -p "${OUT_DIR}"
  rm -rf "${OUT_DIR}/Phone Reseller CRM.app" "${OUT_DIR}/FolderPicker" 2>/dev/null || true
  cp -R "${REPO_DIR}/Customer Copy Intel Mac/Phone Reseller CRM.app" "${OUT_DIR}/"
  cp "${REPO_DIR}/Customer Copy Intel Mac/FolderPicker" "${OUT_DIR}/" 2>/dev/null || true
  cp "${REPO_DIR}/Customer Copy Intel Mac/START HERE.txt" "${OUT_DIR}/" 2>/dev/null || true
  cp "${REPO_DIR}/Customer Copy Intel Mac/license.json" "${OUT_DIR}/" 2>/dev/null || true
  python3 -c "from mac_sign_app import prepare_mac_app; from pathlib import Path; prepare_mac_app(Path('${OUT_DIR}/Phone Reseller CRM.app'))"
else
  echo "ERROR: Unsupported Mac architecture: ${ARCH}"
  read -r -p "Press Enter to close..."
  exit 1
fi

echo ""
echo "Step 4/4 — Signing app for macOS..."
python3 -c "from mac_sign_app import prepare_mac_app; from pathlib import Path; prepare_mac_app(Path('${OUT_DIR}/Phone Reseller CRM.app'))"
if [[ -f "${OUT_DIR}/FolderPicker" ]]; then
  xattr -cr "${OUT_DIR}/FolderPicker" 2>/dev/null || true
  codesign --force --sign - "${OUT_DIR}/FolderPicker" 2>/dev/null || true
fi

echo ""
echo "  DONE"
echo "  ===="
echo ""
echo "  App built at:"
echo "    ${OUT_DIR}/Phone Reseller CRM.app"
echo ""
echo "  Double-click the app to start."
echo "  Browser opens at http://localhost:5050"
echo ""
read -r -p "Press Enter to close..."
