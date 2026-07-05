#!/bin/bash
# Clears the macOS "downloaded from the internet" flag that triggers the
# "Apple could not verify this app is free of malware" warning, then opens
# the CRM. Safe to run every time — it's a no-op once the flag is gone.
cd "$(dirname "$0")"
xattr -cr "Phone Reseller CRM.app" 2>/dev/null
xattr -cr "FolderPicker" 2>/dev/null
open "Phone Reseller CRM.app"
