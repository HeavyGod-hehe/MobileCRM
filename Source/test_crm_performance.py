#!/usr/bin/env python3
"""
Populate the iPhone Reseller CRM with realistic dummy data for performance testing.

Supports two modes:
  - db  (default): inserts directly via database.py — fast, no server required
  - api:           inserts via REST API with requests — requires `python app.py` running

Usage:
  python test_crm_performance.py
  python test_crm_performance.py --mode api --count 100
  python test_crm_performance.py --mode db --count 50
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Realistic seed data pools
# ---------------------------------------------------------------------------

IPHONE_MODELS = [
    "iPhone 11 64GB", "iPhone 11 128GB", "iPhone 12 64GB", "iPhone 12 128GB",
    "iPhone 12 Pro 128GB", "iPhone 13 128GB", "iPhone 13 Pro 256GB",
    "iPhone 14 128GB", "iPhone 14 Pro 128GB", "iPhone 14 Pro Max 256GB",
    "iPhone 15 128GB", "iPhone 15 Pro 128GB", "iPhone 15 Pro Max 256GB",
    "iPhone 16 128GB", "iPhone 16 Pro 128GB", "iPhone 16 Pro Max 256GB",
]

PHONE_TYPES = ("PTA", "NON-PTA", "JV")
PHONE_STATUSES = ("Bought", "Sold", "In Repair")
CONDITIONS = ["10/10", "10/9.5", "10/9", "10/8.5", "10/8", "10/7.5"]
BOX_STATUSES = ("With Box", "Without Box")
VARIANTS = ("Physical + eSIM", "eSIM + eSIM", "Dual Physical SIM")

SUPPLIERS = [
    ("Mobile Point Lahore", "03001234567"),
    ("Tech Hub Karachi", "03111234567"),
    ("iStore Islamabad", "03221234567"),
    ("Phone Zone Faisalabad", "03331234567"),
    ("Gadget World Multan", "03441234567"),
    ("Smart Devices Rawalpindi", "03551234567"),
]

BUYERS = [
    ("Ali Hassan", "03009876543"),
    ("Sara Ahmed", "03119876543"),
    ("Usman Malik", "03229876543"),
    ("Fatima Khan", "03339876543"),
    ("Bilal Sheikh", "03449876543"),
    ("Ayesha Raza", "03559876543"),
]

ACCOUNT_NAMES = [
    "Ahmed Traders", "Hassan Mobiles", "Karachi Electronics", "Lahore Gadgets",
    "Pindi Phone House", "Multan Mobile Mart", "Faisalabad Tech", "Sialkot Devices",
    "Gujranwala Phones", "Hyderabad Mobiles", "Quetta Cell Point", "Peshawar iStore",
    "Mirpur Mobile Zone", "Sargodha Tech Hub", "Bahawalpur Devices",
]

FIXED_EXPENSE_PURPOSES = [
    "Shop rent", "Electricity bill", "Internet / Wi-Fi", "Staff salary",
    "Marketing / ads", "Packaging supplies", "Courier charges", "Software subscription",
    "Shop maintenance", "Security camera service", "Water bill", "Tea & refreshments",
]

BANK_NAMES = [
    "HBL Business", "Meezan Current", "UBL Savings", "Allied Bank",
    "MCB Personal", "Bank Alfalah", "Faysal Bank", "JS Bank",
    "Standard Chartered", "Askari Bank",
]

CASH_NOTES_IN = [
    "Cash sale — walk-in customer", "Partial payment received", "Advance from buyer",
    "Partner capital deposit", "Refund from supplier",
]

CASH_NOTES_OUT = [
    "Supplier payment — cash", "Petty cash — packaging", "Courier payment",
    "Staff advance", "Shop supplies",
]

ENTRY_NOTES = [
    "Payment for iPhone purchase", "Partial settlement", "Monthly credit",
    "Repair charges", "Accessories payment", "Balance cleared",
]

DEFAULT_BASE_URL = "http://localhost:5050"


def random_imei(seed: int) -> str:
    """Generate a deterministic 15-digit IMEI-like string."""
    base = 860000000000000 + seed * 7919
    return str(base)[-15:].zfill(15)


def random_purchase_date(days_back: int = 180) -> str:
    offset = random.randint(0, days_back)
    return (date.today() - timedelta(days=offset)).isoformat()


def random_phone_payload(index: int, partner_ids: list[int]) -> dict:
    model = random.choice(IPHONE_MODELS)
    status = random.choices(PHONE_STATUSES, weights=[50, 35, 15])[0]
    supplier_name, supplier_contact = random.choice(SUPPLIERS)
    purchase_price = random.randint(85000, 450000)

    payload = {
        "model": f"{model} #{index + 1}",
        "type": random.choice(PHONE_TYPES),
        "purchase_price": purchase_price,
        "condition": random.choice(CONDITIONS),
        "status": status,
        "supplier_name": supplier_name,
        "supplier_contact": supplier_contact,
        "imei": random_imei(index),
        "box_status": random.choice(BOX_STATUSES),
        "battery_health": f"{random.randint(78, 100)}%",
        "variant": random.choice(VARIANTS),
        "purchase_date": random_purchase_date(),
    }

    if status == "Sold":
        buyer_name, buyer_contact = random.choice(BUYERS)
        sale_price = purchase_price + random.randint(5000, 80000)
        payload.update({
            "buyer_name": buyer_name,
            "buyer_contact": buyer_contact,
            "sale_price": sale_price,
            "receivable_amount": random.choice([0, 0, 0, random.randint(5000, 30000)]),
        })

    if status == "In Repair":
        payload["payable_amount"] = random.choice([0, random.randint(2000, 15000)])

    if partner_ids and random.random() < 0.6:
        p1 = random.choice(partner_ids)
        split = purchase_price // 2
        investments = [{"partner_id": p1, "amount": split}]
        others = [p for p in partner_ids if p != p1]
        if others and random.random() < 0.5:
            p2 = random.choice(others)
            investments.append({"partner_id": p2, "amount": purchase_price - split})
        payload["investments"] = investments

    if random.random() < 0.3:
        payload["expenses"] = [{
            "amount": random.randint(500, 8000),
            "description": random.choice([
                "Screen protector", "Back cover", "Battery replacement",
                "Face ID repair", "Charging port fix",
            ]),
        }]

    return payload


def random_account_payload(index: int) -> dict:
    base = random.choice(ACCOUNT_NAMES)
    return {
        "name": f"{base} #{index + 1}",
        "contact": f"03{random.randint(10, 99)}{random.randint(1000000, 9999999)}",
    }


def random_partner_payload(index: int) -> dict:
    names = [
        "Talha", "Shahir", "Hamza", "Zain", "Omar", "Saad", "Arslan",
        "Fahad", "Imran", "Kamran", "Waqas", "Nabeel", "Rizwan", "Asad",
    ]
    return {
        "name": f"{random.choice(names)} Partner #{index + 1}",
        "capital": random.randint(50000, 500000),
    }


def random_fixed_expense_payload(index: int) -> dict:
    purpose = random.choice(FIXED_EXPENSE_PURPOSES)
    return {
        "purpose": f"{purpose} — {index + 1}",
        "amount": random.randint(2000, 85000),
    }


def random_bank_payload(index: int) -> dict:
    name = random.choice(BANK_NAMES)
    return {
        "name": f"{name} #{index + 1}",
        "initial_balance": random.randint(10000, 500000),
    }


def random_cash_book_payload(index: int) -> dict:
    entry_type = random.choice(("in", "out"))
    notes = CASH_NOTES_IN if entry_type == "in" else CASH_NOTES_OUT
    return {
        "entry_type": entry_type,
        "amount": random.randint(1000, 150000),
        "note": f"{random.choice(notes)} #{index + 1}",
        "entry_date": random_purchase_date(90),
    }


def random_account_entry_payload(index: int) -> dict:
    return {
        "entry_type": random.choice(("credit", "debit")),
        "amount": random.randint(5000, 200000),
        "note": f"{random.choice(ENTRY_NOTES)} #{index + 1}",
    }


def random_bank_transaction_payload(index: int) -> dict:
    return {
        "transaction_type": random.choice(("credit", "debit")),
        "amount": random.randint(5000, 250000),
        "note": f"Transaction #{index + 1}",
    }


# ---------------------------------------------------------------------------
# Direct database seeding
# ---------------------------------------------------------------------------

def seed_via_db(count: int, username: str, password: str) -> dict[str, int]:
    import database as db

    print("Initializing database (migrations / default user)...")
    db.init_db()

    with db.db_session() as conn:
        user = db.verify_login(conn, username, password)
        if not user:
            print(f"ERROR: User '{username}' not found or password incorrect.")
            sys.exit(1)
        user_id = user["user_id"]
        print(f"Logged in as user_id={user_id} ({username})\n")

        stats: dict[str, int] = {}
        partner_ids: list[int] = []

        # --- Partners ---
        print(f"[1/6] Creating {count} partners...")
        for i in range(count):
            partner = db.create_partner(conn, user_id, random_partner_payload(i))
            partner_ids.append(partner["id"])
            if (i + 1) % 10 == 0 or i + 1 == count:
                print(f"       Partners: {i + 1}/{count}")
        stats["partners"] = count

        # --- Phones (inventory) ---
        print(f"\n[2/6] Creating {count} phones (inventory)...")
        for i in range(count):
            db.create_phone(conn, user_id, random_phone_payload(i, partner_ids))
            if (i + 1) % 10 == 0 or i + 1 == count:
                print(f"       Phones: {i + 1}/{count}")
        stats["phones"] = count

        # --- Accounts + ledger entries ---
        print(f"\n[3/6] Creating {count} accounts with ledger entries...")
        for i in range(count):
            account = db.create_account(conn, user_id, random_account_payload(i))
            db.create_entry(conn, account["id"], random_account_entry_payload(i))
            if (i + 1) % 10 == 0 or i + 1 == count:
                print(f"       Accounts: {i + 1}/{count}")
        stats["accounts"] = count
        stats["account_entries"] = count

        # --- Fixed expenses ---
        print(f"\n[4/6] Creating {count} fixed expenses...")
        for i in range(count):
            db.create_fixed_expense(conn, user_id, random_fixed_expense_payload(i))
            if (i + 1) % 10 == 0 or i + 1 == count:
                print(f"       Fixed expenses: {i + 1}/{count}")
        stats["fixed_expenses"] = count

        # --- Bank accounts + transactions ---
        print(f"\n[5/6] Creating {count} bank accounts with transactions...")
        for i in range(count):
            bank = db.create_bank(conn, user_id, random_bank_payload(i))
            db.create_bank_transaction(conn, bank["id"], random_bank_transaction_payload(i))
            if (i + 1) % 10 == 0 or i + 1 == count:
                print(f"       Bank accounts: {i + 1}/{count}")
        stats["bank_accounts"] = count
        stats["bank_transactions"] = count

        # --- Cash book ---
        print(f"\n[6/6] Creating {count} cash book entries...")
        for i in range(count):
            db.create_cash_book_entry(conn, user_id, random_cash_book_payload(i))
            if (i + 1) % 10 == 0 or i + 1 == count:
                print(f"       Cash book entries: {i + 1}/{count}")
        stats["cash_book_entries"] = count

    return stats


# ---------------------------------------------------------------------------
# REST API seeding
# ---------------------------------------------------------------------------

def seed_via_api(count: int, base_url: str, username: str, password: str) -> dict[str, int]:
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' is required for API mode. Install it with:")
        print("  pip install requests")
        sys.exit(1)

    session = requests.Session()
    login_url = f"{base_url}/api/auth/login"
    print(f"Logging in at {login_url}...")
    resp = session.post(login_url, json={"username": username, "password": password})
    if resp.status_code != 200:
        print(f"ERROR: Login failed ({resp.status_code}): {resp.text}")
        print("Make sure the Flask app is running:  python app.py")
        sys.exit(1)
    print(f"Logged in as {username}\n")

    stats: dict[str, int] = {}
    partner_ids: list[int] = []

    def post(path: str, payload: dict) -> dict:
        url = f"{base_url}{path}"
        r = session.post(url, json=payload)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"POST {path} failed ({r.status_code}): {r.text}")
        return r.json()

    # --- Partners ---
    print(f"[1/6] Creating {count} partners...")
    for i in range(count):
        result = post("/api/partners", random_partner_payload(i))
        partner_ids.append(result["id"])
        if (i + 1) % 10 == 0 or i + 1 == count:
            print(f"       Partners: {i + 1}/{count}")
    stats["partners"] = count

    # --- Phones ---
    print(f"\n[2/6] Creating {count} phones (inventory)...")
    for i in range(count):
        post("/api/phones", random_phone_payload(i, partner_ids))
        if (i + 1) % 10 == 0 or i + 1 == count:
            print(f"       Phones: {i + 1}/{count}")
    stats["phones"] = count

    # --- Accounts + entries ---
    print(f"\n[3/6] Creating {count} accounts with ledger entries...")
    for i in range(count):
        account = post("/api/accounts", random_account_payload(i))
        post(f"/api/accounts/{account['id']}/entries", random_account_entry_payload(i))
        if (i + 1) % 10 == 0 or i + 1 == count:
            print(f"       Accounts: {i + 1}/{count}")
    stats["accounts"] = count
    stats["account_entries"] = count

    # --- Fixed expenses ---
    print(f"\n[4/6] Creating {count} fixed expenses...")
    for i in range(count):
        post("/api/fixed-expenses", random_fixed_expense_payload(i))
        if (i + 1) % 10 == 0 or i + 1 == count:
            print(f"       Fixed expenses: {i + 1}/{count}")
    stats["fixed_expenses"] = count

    # --- Banks + transactions ---
    print(f"\n[5/6] Creating {count} bank accounts with transactions...")
    for i in range(count):
        bank = post("/api/banks", random_bank_payload(i))
        post(f"/api/banks/{bank['id']}/transactions", random_bank_transaction_payload(i))
        if (i + 1) % 10 == 0 or i + 1 == count:
            print(f"       Bank accounts: {i + 1}/{count}")
    stats["bank_accounts"] = count
    stats["bank_transactions"] = count

    # --- Cash book ---
    print(f"\n[6/6] Creating {count} cash book entries...")
    for i in range(count):
        post("/api/cash-book", random_cash_book_payload(i))
        if (i + 1) % 10 == 0 or i + 1 == count:
            print(f"       Cash book entries: {i + 1}/{count}")
    stats["cash_book_entries"] = count

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the iPhone Reseller CRM with performance-test dummy data.",
    )
    parser.add_argument(
        "--count", type=int, default=100,
        help="Number of records to create per section (default: 100)",
    )
    parser.add_argument(
        "--mode", choices=("db", "api"), default="db",
        help="Insertion method: 'db' (direct SQLite, fast) or 'api' (HTTP, needs server)",
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL,
        help=f"Flask base URL for API mode (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible data (default: 42)",
    )
    parser.add_argument(
        "--username",
        help="Username for login (will prompt if not provided)",
    )
    parser.add_argument(
        "--password",
        help="Password for login (will prompt if not provided)",
    )
    args = parser.parse_args()

    # Prompt for credentials if not provided
    username = args.username
    password = args.password
    if not username:
        username = input("Enter username: ")
    if not password:
        import getpass
        password = getpass.getpass("Enter password: ")

    random.seed(args.seed)

    print("=" * 60)
    print("  iPhone Reseller CRM — Performance Test Data Seeder")
    print("=" * 60)
    print(f"  Mode:   {args.mode.upper()}")
    print(f"  Count:  {args.count} records per section")
    print(f"  Seed:   {args.seed}")
    if args.mode == "api":
        print(f"  URL:    {args.base_url}")
    print("=" * 60)
    print()

    start = time.perf_counter()

    if args.mode == "db":
        stats = seed_via_db(args.count, username, password)
    else:
        stats = seed_via_api(args.count, args.base_url, username, password)

    elapsed = time.perf_counter() - start

    print()
    print("=" * 60)
    print("  SEED COMPLETE")
    print("=" * 60)
    total = 0
    for label, n in stats.items():
        print(f"  {label.replace('_', ' ').title():<22} {n:>5}")
        total += n
    print(f"  {'─' * 30}")
    print(f"  {'Total records':<22} {total:>5}")
    print(f"  {'Elapsed time':<22} {elapsed:>5.2f}s")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Start the app:     python app.py")
    print("  2. Open in browser:   http://localhost:5050")
    print(f"  3. Log in as:         {username}")
    print("  4. Browse each section and check for UI slowdown or glitches.")


if __name__ == "__main__":
    main()
