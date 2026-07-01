# Mobile CRM — Phone Reseller CRM v2.1.1

Pakistani phone reseller CRM: inventory, accounts (khata), cash book, billing, WhatsApp receipts, Today dashboard.

## Folder layout

| Folder | Purpose |
|--------|---------|
| **Source/** | Full Python project — run with `python3 app.py` |
| **Customer Copy/** | Mac customer build — double-click `Phone Reseller CRM.app` |
| **Source/crm.db** | Sample / dev SQLite database (included) |

## Quick start (developer)

```bash
cd Source
pip install -r requirements.txt
python3 app.py
# → http://localhost:5050
```

## Rebuild customer app

```bash
cd Source
python3 build_customer_copy.py
# → outputs to ../Customer Copy/
```

## License keys (vendor only)

```bash
cd Source
python3 generate_key.py <HARDWARE_ID>
```

Never ship `generate_key.py` to customers — use **Customer Copy** only.
