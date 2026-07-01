# Mobile CRM — Phone Reseller CRM v2.1.1

Pakistani phone reseller CRM: inventory, accounts (khata), cash book, billing, WhatsApp receipts, Today dashboard.

## Folder layout

| Folder | Purpose |
|--------|---------|
| **Source/** | Full Python project — run with `python3 app.py` |
| **Customer Copy/** | Mac customer build — double-click `Phone Reseller CRM.app` |
| **Customer Windows Copy/** | Windows customer build — double-click `Phone Reseller CRM\Phone Reseller CRM.exe` |
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

### Windows customer build

On a Windows PC (or via GitHub Actions):

```bash
cd Source
python build_customer_windows_copy.py
# → outputs to ../Customer Windows Copy/
```

Or double-click `Download Customer Windows Copy.bat` after cloning (requires [GitHub CLI](https://cli.github.com/)).

## License keys (vendor only)

```bash
cd Source
python3 generate_key.py <HARDWARE_ID>
```

Never ship `generate_key.py` to customers — use **Customer Copy** only.
