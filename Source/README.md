# iPhone Reseller CRM

A lightweight, local web-based CRM and dashboard for a two-partner iPhone reselling business. Answers the critical question: **"How much money should be in my bank account right now?"**

## Quick Start

```bash
# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```

Open **http://localhost:5050** — three pages via the top navigation:

| Page | URL | Purpose |
|------|-----|---------|
| **Inventory** | `/` | Bought, In Repair & Sold phone sections |
| **Accounts** | `/accounts` | Digikhata-style credit/debit ledger per person |
| **Overview** | `/overview` | Financial reconciliation & monthly metrics |

## Features

- **Financial reconciliation dashboard** — partner capital, expected bank balance, receivables, active stock worth
- **Inventory ledger** — log purchases with supplier details, PTA/NON-PTA/JV type, and purchase price
- **Sales tracking** — mark items sold with buyer info, sale price, receivables, and auto-calculated net profit
- **Monthly analytics** — units sold, net profit, profit margin %, top-performing model

## Expected Bank Balance Formula

```
Expected Cash = Total Investment + Total Net Profit − Total Receivables − Active Stock Worth
```

Data is stored locally in `crm.db` (SQLite). No cloud, no accounts — single-terminal use.
