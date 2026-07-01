Phone Reseller CRM v2.3 — Folder layout
=======================================

  Source/                        ← Developer project (Python)
  Customer Copy Apple Silicon/   ← Mac M1/M2/M3/M4 customers
  Customer Copy Intel Mac/       ← Mac Intel customers
  Customer Windows Copy/         ← Windows customers
  CUSTOMER_COPIES.md             ← Which folder to use

DEVELOPER
─────────
  cd Source && pip install -r requirements.txt && python3 app.py

  Rebuild customer copies:
    python3 build_customer_mac.py --arch arm64
    python3 build_customer_mac.py --arch x86_64
    python build_customer_windows_copy.py   (Windows only)

CUSTOMER
────────
  See CUSTOMER_COPIES.md for the correct folder for your computer.
