Cursor-Panga — Phone Reseller CRM v2.1
======================================

Folder layout:

  Source/           ← Full developer project (Python, templates, build scripts)
  Customer Copy/    ← Ship this folder to shopkeepers (no source code)

DEVELOPER (you)
───────────────
  cd Source
  python3 -m venv venv && source venv/bin/activate
  pip install flask werkzeug
  python3 app.py                    ← run locally at http://localhost:5050

  Rebuild customer app after changes:
  python3 build_customer_copy.py    ← outputs to ../Customer Copy/

  Generate license keys (never ship generate_key.py to customers):
  python3 generate_key.py <HARDWARE_ID>

CUSTOMER
────────
  Double-click: Customer Copy/Phone Reseller CRM.app
  Read: Customer Copy/START HERE.txt

NEW IN v2.1
───────────
  • Today dashboard (home screen)
  • WhatsApp invoice + account balance share
  • Gmail OTP forgot password (+ vendor WhatsApp fallback)
  • Backup restore button
  • Month report (print/PDF)
  • Profit column on inventory
  • IMEI camera scan (mobile browser)
  • One Shop Details settings section
  • Help guide for Cash Book / Accounts / Bank / Journal
