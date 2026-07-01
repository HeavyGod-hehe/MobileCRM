#!/bin/bash
# Double-click to start Phone Reseller CRM

clear
echo ""
echo "  Phone Reseller CRM"
echo "  ──────────────────"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/run_crm.sh"
