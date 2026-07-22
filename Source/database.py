"""Phone Reseller CRM - database layer (all business logic lives here).

BEGINNER'S MAP OF THIS FILE
----------------------------
This file owns the SQLite database and every rule about what's allowed to
happen to the data. app.py (the web layer) never talks to SQL directly - it
calls plain Python functions in here, e.g. create_phone(), delete_account(),
compute_dashboard(). That split means: the web/HTTP stuff lives in app.py,
and "what a sale actually does to the books" lives here.

THE LEDGER SYNC ENGINE (the trickiest part of this file)
----------------------------------------------------------
A phone reseller's books have three linked records for one real-world event.
Example: you sell a phone on credit (udhar) to a customer.
  1. The **phone** row changes status to "sold".
  2. A **cash book** entry may be created if any cash was received.
  3. An **account** (khata) entry is created for the customer, showing they
     now owe money.
These three must always agree - if you delete the phone sale, the cash book
and account entries must reverse too, otherwise the books would be wrong
forever. The "ledger_links" table is how this file remembers which records
belong together, so a delete/edit can find and fix all of them:
  - _record_ledger_link()          records that link
  - _create_cash_book_synced() /
    _create_account_entry_synced() create a cash-book/account entry AND
                                    link it in one step
  - _reverse_ledger_for_source()   undoes everything linked to one event
    (called when a phone/entry is deleted or edited)
  - _delete_*_cascade()            deletes one record and follows its links
                                    to reverse the others

SCHEMA MIGRATIONS
-------------------
init_db() runs on every app start and brings whatever database file exists
up to the current schema, one small versioned step at a time (the
_migrate_* functions). This means updating the app to a newer version never
requires the shop owner to do anything manually - their existing data file
is upgraded in place, with an automatic backup taken first (see
_backup_before_schema_migration).

The rest of the file is grouped by feature with "# --- Section ---" headers
(Auth, Partners, Phones, Bank Accounts, Cash Book, Accounts, Reports, ...) -
search for "# ---" to jump between them.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import sqlite3
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from app_paths import customer_data_dir, customer_install_dir, executable_dir, path_is_inside_app_bundle


def default_backup_dir() -> Path | None:
    data_dir = customer_data_dir()
    if not data_dir:
        return None
    return data_dir / "Backups"


def _resolve_db_path() -> Path:
    env_path = os.environ.get("CRM_DB_PATH")
    if env_path:
        return Path(env_path)
    if getattr(sys, "frozen", False):
        return customer_data_dir() / "crm.db"
    return Path(__file__).parent / "crm.db"


DB_PATH = _resolve_db_path()
_CUSTOMER_LAYOUT_READY = False
PASSWORD_HASH_METHOD = "pbkdf2:sha256"

PHONE_STATUSES = ("Bought", "Sold", "In Repair", "Returned to Supplier")
INVENTORY_STATUSES = ("Bought", "In Repair")
RETURN_TYPES = ("purchase", "sale")
ENTRY_TYPES = ("credit", "debit")
BANK_TX_TYPES = ("credit", "debit")
CASH_BOOK_TYPES = ("in", "out")
BOX_STATUS_OPTIONS = ("With Box", "Without Box")
VARIANT_OPTIONS = ("Physical + eSIM", "eSIM + eSIM", "Dual Physical SIM")

CONDITION_OPTIONS = [
    f"10/{v}" for v in [
        "10", "9.5", "9", "8.5", "8", "7.5", "7", "6.5", "6", "5.5", "5"
    ]
]

DEFAULT_SETTINGS = {
    "partner1_name": "",
    "partner1_capital": "0",
    "partner2_name": "",
    "partner2_capital": "0",
    "cash_in_hand": "0",
    "theme": "default-dark",
    "shop_name": "My Phone Shop",
    "shop_address": "",
    "shop_phones": "[]",
    "shop_logo": "",
    "local_backup_path": "",
    "last_backup_at": "",
    "auto_backup_enabled": "true",
    "shop_whatsapp": "",
    "vendor_whatsapp": "",
    "vendor_support_note": "Contact your CRM vendor with your Hardware ID to reset your password.",
    "gmail_smtp_user": "",
    "gmail_smtp_app_password": "",
    "invoice_counter": "1000",
}

USER_SCOPED_TABLES = (
    "phones", "accounts", "partners", "fixed_expenses",
    "bank_accounts", "cash_book_entries", "journal_vouchers",
)


def get_connection():
    """Open one connection to the CRM's database file.

    Two settings here matter a lot for a threaded Flask app like this one,
    where a single page load fires several API calls in parallel (each on
    its own connection) and a background thread does hourly auto-backups:

    - timeout=30: by default SQLite gives up and raises "database is
      locked" after just 5 seconds if another connection is mid-write.
      30 seconds means a connection *waits* for the other one to finish
      instead of failing outright — this is what was causing the
      intermittent "Database busy, please retry" errors during things
      like signup (which writes the new user, then immediately triggers a
      backup on another connection).
    - journal_mode=WAL: SQLite's default journal mode locks the *entire*
      file during a write, blocking every other connection (even ones that
      only want to read). WAL mode lets reads keep happening concurrently
      with a write, which is the common case here (several GETs firing
      alongside one POST) and removes most lock contention outright rather
      than just waiting it out.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _recover_crashed_table_rebuild(conn, live_table, staging_table):
    """If a previous run crashed between dropping `live_table` and renaming
    `staging_table` into place, finish the rename now — before any
    `CREATE TABLE IF NOT EXISTS` below can recreate `live_table` empty and
    strand the real data in the staging table forever."""
    if _table_exists(conn, staging_table) and not _table_exists(conn, live_table):
        conn.execute(f"ALTER TABLE {staging_table} RENAME TO {live_table}")


# --- Versioned schema migrations ---
#
# Everything above this point (the legacy `_migrate_*` chain called at the
# bottom of init_db) is the schema as it existed before this versioning
# system was introduced — it's already tested and stays as-is.
#
# From here on, every future schema change should be added as a new entry
# in SCHEMA_MIGRATIONS instead of another ad-hoc `_migrate_*` call. Each
# migration is tracked via SQLite's built-in `PRAGMA user_version`, so:
#   - it runs exactly once per database, ever (not on every launch)
#   - a timestamped backup of the whole .db file is taken automatically,
#     right before ANY pending migration touches the schema
#   - if a migration ever raises, the whole init_db() transaction rolls
#     back (see db_session()), so a failed migration can't leave the
#     schema half-changed — the untouched backup is still there either way
#
# To add a new migration later: write a function `def _migrate_v2_whatever
# (conn): ...`, add `(2, _migrate_v2_whatever)` to SCHEMA_MIGRATIONS, and
# bump CURRENT_SCHEMA_VERSION to 2. Never reuse or renumber an existing
# version once it's shipped to a customer.
CURRENT_SCHEMA_VERSION = 1
SCHEMA_MIGRATIONS = (
    # (2, _migrate_v2_whatever),
)


def _backup_before_schema_migration(conn, from_version: int, to_version: int) -> Path | None:
    """Save a timestamped copy of the database before a schema change is
    applied, using SQLite's own backup API (not a raw file copy — see
    backup_service.py for why that matters). Skipped for a brand-new,
    not-yet-created database since there's nothing to protect yet.

    Reads the file path from `conn` itself (PRAGMA database_list) rather
    than the global DB_PATH, so this also works correctly when migrating a
    scratch copy of a restored backup (see restore_database_from_backup),
    not just the one live app database."""
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    if not db_file or not Path(db_file).is_file():
        return None
    db_file_path = Path(db_file)
    backup_dir = db_file_path.parent / "pre_migration_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"crm_pre_v{from_version}_to_v{to_version}_{stamp}.db"
    backup_conn = sqlite3.connect(str(dest))
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()
    return dest


def _run_schema_migrations(conn) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == 0:
        # First time this database is seen under version tracking — it has
        # already been brought up to CURRENT_SCHEMA_VERSION's baseline by
        # the legacy migration chain above, so just record that, rather
        # than treating every future migration as "pending" retroactively.
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        return
    pending = sorted((v, fn) for v, fn in SCHEMA_MIGRATIONS if v > current)
    if not pending:
        return
    _backup_before_schema_migration(conn, current, pending[-1][0])
    for version, migrate in pending:
        migrate(conn)
        conn.execute(f"PRAGMA user_version = {version}")


def _init_schema(conn) -> None:
    """Create every table and run every migration, bringing whatever
    database `conn` points at up to CURRENT_SCHEMA_VERSION.

    Deliberately excludes ensure_customer_data_layout(), which touches the
    global live app paths (DB_PATH, customer_data_dir()) and must never run
    against a scratch/temp connection — see restore_database_from_backup(),
    which calls this on a throwaway copy of a backup file to bring it up to
    the current schema before importing rows from it."""
    _recover_crashed_table_rebuild(conn, "phones", "phones_migrated")
    _recover_crashed_table_rebuild(conn, "phones", "phones_status_migrated")
    conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                condition TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL CHECK(type IN ('PTA', 'NON-PTA', 'JV')),
                purchase_price REAL NOT NULL,
                supplier_name TEXT NOT NULL DEFAULT '',
                supplier_contact TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Bought'
                    CHECK(status IN ('Bought', 'Sold', 'In Repair')),
                payable_amount REAL NOT NULL DEFAULT 0,
                advance_received REAL NOT NULL DEFAULT 0,
                buyer_name TEXT NOT NULL DEFAULT '',
                buyer_contact TEXT NOT NULL DEFAULT '',
                sale_price REAL,
                receivable_amount REAL NOT NULL DEFAULT 0,
                sold_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                contact TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS account_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                entry_type TEXT NOT NULL CHECK(entry_type IN ('credit', 'debit')),
                amount REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                capital REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS phone_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_id INTEGER NOT NULL REFERENCES phones(id) ON DELETE CASCADE,
                amount REAL NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS phone_investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_id INTEGER NOT NULL REFERENCES phones(id) ON DELETE CASCADE,
                partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                amount REAL NOT NULL DEFAULT 0,
                UNIQUE(phone_id, partner_id)
            );

            CREATE TABLE IF NOT EXISTS fixed_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purpose TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bank_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
                transaction_type TEXT NOT NULL CHECK(transaction_type IN ('credit', 'debit')),
                amount REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS cash_book_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL CHECK(entry_type IN ('in', 'out')),
                amount REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                entry_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
    _migrate_phones_table(conn)
    _migrate_phone_columns(conn)
    _migrate_phone_statuses(conn)
    _migrate_returns_table(conn)
    _migrate_cash_book_account(conn)
    _migrate_journal_vouchers(conn)
    _migrate_side_investments(conn)
    _migrate_cursor_panga(conn)
    _migrate_payment_methods(conn)
    _migrate_account_entry_payments(conn)
    _migrate_more_fixes(conn)
    _migrate_ledger_sync(conn)
    _migrate_fixed_expense_ledger(conn)

    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    _migrate_multi_user(conn)
    _migrate_purchase_invoices(conn)
    _migrate_indexes(conn)
    _migrate_unique_invoice_numbers(conn)
    _run_schema_migrations(conn)


def init_db():
    with db_session() as conn:
        _init_schema(conn)
        ensure_customer_data_layout(conn)


def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _run_migration_script(conn, script, staging_table=None):
    """Run a table-rebuild migration; tolerate leftover staging tables."""
    if staging_table:
        conn.execute(f"DROP TABLE IF EXISTS {staging_table}")
    try:
        conn.executescript(script)
    except sqlite3.OperationalError as exc:
        if "already exists" not in str(exc).lower():
            raise
        if staging_table:
            conn.execute(f"DROP TABLE IF EXISTS {staging_table}")


def _verify_and_swap_table(conn, source_table, staging_table):
    """Abort (instead of silently losing data) if the rebuild dropped rows or
    columns the live table currently has, then drop the old table and rename
    the staging table into place. Guards against a migration's hardcoded
    column list going stale after later migrations add new columns."""
    source_cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({source_table})").fetchall()}
    staging_cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({staging_table})").fetchall()}
    missing_cols = source_cols - staging_cols
    if missing_cols:
        raise RuntimeError(
            f"Migration aborted: rebuilding '{source_table}' would drop column(s) "
            f"{sorted(missing_cols)} that still have data. Not proceeding — "
            "your existing data has not been touched."
        )
    source_count = conn.execute(f"SELECT COUNT(*) AS c FROM {source_table}").fetchone()["c"]
    staging_count = conn.execute(f"SELECT COUNT(*) AS c FROM {staging_table}").fetchone()["c"]
    if staging_count != source_count:
        raise RuntimeError(
            f"Migration aborted: rebuilding '{source_table}' produced {staging_count} rows, "
            f"expected {source_count}. Not proceeding — your existing data has not been touched."
        )
    conn.execute(f"DROP TABLE {source_table}")
    conn.execute(f"ALTER TABLE {staging_table} RENAME TO {source_table}")


def _migrate_phone_columns(conn):
    columns = {
        "imei": "TEXT NOT NULL DEFAULT ''",
        "box_status": "TEXT NOT NULL DEFAULT ''",
        "battery_health": "TEXT NOT NULL DEFAULT ''",
        "variant": "TEXT NOT NULL DEFAULT ''",
        "purchase_date": "TEXT NOT NULL DEFAULT ''",
    }
    for col, typedef in columns.items():
        if not _column_exists(conn, "phones", col):
            conn.execute(f"ALTER TABLE phones ADD COLUMN {col} {typedef}")


def _migrate_phones_table(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='phones'"
    ).fetchone()
    if not row or not row[0]:
        return
    ddl = row[0]
    if "'Bought'" in ddl and "In Stock" not in ddl:
        conn.execute("DROP TABLE IF EXISTS phones_migrated")
        return

    # Carry forward every column the live table currently has (not just the
    # columns known when this migration was first written), so columns added
    # by later migrations (IMEI, bank links, etc.) are never silently dropped
    # if this legacy rebuild ever fires again on a mid-upgrade database.
    base_cols = (
        "id", "model", "condition", "type", "purchase_price",
        "supplier_name", "supplier_contact", "status",
        "payable_amount", "advance_received",
        "buyer_name", "buyer_contact", "sale_price", "receivable_amount",
        "sold_at", "created_at",
    )
    existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(phones)").fetchall()]
    extra_cols = [c for c in existing_cols if c not in base_cols]
    extra_defs = "".join(f",\n            {c} TEXT" for c in extra_cols)
    extra_list = "".join(f", {c}" for c in extra_cols)

    _run_migration_script(
        conn,
        f"""
        CREATE TABLE phones_migrated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            condition TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL CHECK(type IN ('PTA', 'NON-PTA', 'JV')),
            purchase_price REAL NOT NULL,
            supplier_name TEXT NOT NULL DEFAULT '',
            supplier_contact TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Bought'
                CHECK(status IN ('Bought', 'Sold', 'In Repair')),
            payable_amount REAL NOT NULL DEFAULT 0,
            advance_received REAL NOT NULL DEFAULT 0,
            buyer_name TEXT NOT NULL DEFAULT '',
            buyer_contact TEXT NOT NULL DEFAULT '',
            sale_price REAL,
            receivable_amount REAL NOT NULL DEFAULT 0,
            sold_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')){extra_defs}
        );

        INSERT INTO phones_migrated (
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at{extra_list}
        )
        SELECT
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact,
            CASE
                WHEN status = 'In Stock' THEN 'Bought'
                WHEN status IN ('Sold', 'In Repair') THEN status
                ELSE 'Bought'
            END,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at{extra_list}
        FROM phones;
        """,
        staging_table="phones_migrated",
    )
    _verify_and_swap_table(conn, "phones", "phones_migrated")


def _migrate_phone_statuses(conn):
    """Add 'Returned to Supplier' to phones status CHECK if missing."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='phones'"
    ).fetchone()
    if not row or not row[0]:
        return
    ddl = row[0]
    if "Returned to Supplier" in ddl:
        conn.execute("DROP TABLE IF EXISTS phones_status_migrated")
        return

    base_cols = (
        "id", "model", "condition", "type", "purchase_price",
        "supplier_name", "supplier_contact", "status",
        "payable_amount", "advance_received",
        "buyer_name", "buyer_contact", "sale_price", "receivable_amount",
        "sold_at", "created_at", "imei", "box_status", "battery_health",
        "variant", "purchase_date",
    )
    existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(phones)").fetchall()]
    extra_cols = [c for c in existing_cols if c not in base_cols]
    extra_defs = "".join(f",\n            {c} TEXT" for c in extra_cols)
    extra_list = "".join(f", {c}" for c in extra_cols)

    _run_migration_script(
        conn,
        f"""
        CREATE TABLE phones_status_migrated (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            condition TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL CHECK(type IN ('PTA', 'NON-PTA', 'JV')),
            purchase_price REAL NOT NULL,
            supplier_name TEXT NOT NULL DEFAULT '',
            supplier_contact TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Bought'
                CHECK(status IN ('Bought', 'Sold', 'In Repair', 'Returned to Supplier')),
            payable_amount REAL NOT NULL DEFAULT 0,
            advance_received REAL NOT NULL DEFAULT 0,
            buyer_name TEXT NOT NULL DEFAULT '',
            buyer_contact TEXT NOT NULL DEFAULT '',
            sale_price REAL,
            receivable_amount REAL NOT NULL DEFAULT 0,
            sold_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            imei TEXT NOT NULL DEFAULT '',
            box_status TEXT NOT NULL DEFAULT '',
            battery_health TEXT NOT NULL DEFAULT '',
            variant TEXT NOT NULL DEFAULT '',
            purchase_date TEXT NOT NULL DEFAULT ''{extra_defs}
        );

        INSERT INTO phones_status_migrated (
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at, imei, box_status, battery_health, variant,
            purchase_date{extra_list}
        )
        SELECT
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at, imei, box_status, battery_health, variant,
            purchase_date{extra_list}
        FROM phones;
        """,
        staging_table="phones_status_migrated",
    )
    _verify_and_swap_table(conn, "phones", "phones_status_migrated")


def _migrate_returns_table(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS return_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            return_type TEXT NOT NULL CHECK(return_type IN ('purchase', 'sale')),
            phone_id INTEGER REFERENCES phones(id) ON DELETE SET NULL,
            imei TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            party_name TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _migrate_cash_book_account(conn):
    if not _column_exists(conn, "cash_book_entries", "account_id"):
        conn.execute(
            "ALTER TABLE cash_book_entries ADD COLUMN account_id INTEGER REFERENCES accounts(id)"
        )


def _migrate_payment_methods(conn):
    if not _column_exists(conn, "cash_book_entries", "payment_source"):
        conn.execute(
            "ALTER TABLE cash_book_entries ADD COLUMN payment_source TEXT NOT NULL DEFAULT 'cash'"
        )
    if not _column_exists(conn, "cash_book_entries", "bank_account_id"):
        conn.execute(
            "ALTER TABLE cash_book_entries ADD COLUMN bank_account_id INTEGER REFERENCES bank_accounts(id)"
        )
    for col, typedef in (
        ("purchase_payment_method", "TEXT NOT NULL DEFAULT 'cash'"),
        ("purchase_bank_id", "INTEGER REFERENCES bank_accounts(id)"),
        ("sale_payment_method", "TEXT NOT NULL DEFAULT 'cash'"),
        ("sale_bank_id", "INTEGER REFERENCES bank_accounts(id)"),
    ):
        if not _column_exists(conn, "phones", col):
            conn.execute(f"ALTER TABLE phones ADD COLUMN {col} {typedef}")


def _migrate_account_entry_payments(conn):
    if not _column_exists(conn, "account_entries", "payment_source"):
        conn.execute(
            "ALTER TABLE account_entries ADD COLUMN payment_source TEXT NOT NULL DEFAULT ''"
        )
    if not _column_exists(conn, "account_entries", "bank_account_id"):
        conn.execute(
            "ALTER TABLE account_entries ADD COLUMN bank_account_id INTEGER REFERENCES bank_accounts(id)"
        )


def _migrate_more_fixes(conn):
    """imei2, supplier account link, phone expense accounts, return refunds."""
    if not _column_exists(conn, "phones", "imei2"):
        conn.execute("ALTER TABLE phones ADD COLUMN imei2 TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "phones", "supplier_account_id"):
        conn.execute(
            "ALTER TABLE phones ADD COLUMN supplier_account_id INTEGER REFERENCES accounts(id)"
        )
    for col, sql in (
        ("account_id", "ALTER TABLE phone_expenses ADD COLUMN account_id INTEGER REFERENCES accounts(id)"),
        ("expense_date", "ALTER TABLE phone_expenses ADD COLUMN expense_date TEXT NOT NULL DEFAULT ''"),
        (
            "cash_book_entry_id",
            "ALTER TABLE phone_expenses ADD COLUMN cash_book_entry_id INTEGER REFERENCES cash_book_entries(id)",
        ),
    ):
        if not _column_exists(conn, "phone_expenses", col):
            conn.execute(sql)
    if not _column_exists(conn, "return_logs", "refund_amount"):
        conn.execute(
            "ALTER TABLE return_logs ADD COLUMN refund_amount REAL NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "return_logs", "account_id"):
        conn.execute(
            "ALTER TABLE return_logs ADD COLUMN account_id INTEGER REFERENCES accounts(id)"
        )


def _migrate_fixed_expense_ledger(conn):
    """Link fixed expenses to cash book for overview shop costs."""
    if not _column_exists(conn, "fixed_expenses", "cash_book_entry_id"):
        conn.execute(
            "ALTER TABLE fixed_expenses ADD COLUMN cash_book_entry_id INTEGER REFERENCES cash_book_entries(id)"
        )


def _migrate_ledger_sync(conn):
    """Cross-module ledger links, borrow phones, synced deletes."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ledger_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            cash_book_entry_id INTEGER REFERENCES cash_book_entries(id),
            account_entry_id INTEGER REFERENCES account_entries(id),
            bank_transaction_id INTEGER REFERENCES bank_transactions(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_links_source
            ON ledger_links(user_id, source_type, source_id);
        """
    )
    for col, sql in (
        ("acquisition_type", "ALTER TABLE phones ADD COLUMN acquisition_type TEXT NOT NULL DEFAULT 'purchase'"),
        ("buyer_account_id", "ALTER TABLE phones ADD COLUMN buyer_account_id INTEGER REFERENCES accounts(id)"),
        ("purchase_cash_book_entry_id", "ALTER TABLE phones ADD COLUMN purchase_cash_book_entry_id INTEGER REFERENCES cash_book_entries(id)"),
        ("sale_cash_book_entry_id", "ALTER TABLE phones ADD COLUMN sale_cash_book_entry_id INTEGER REFERENCES cash_book_entries(id)"),
        ("purchase_account_entry_id", "ALTER TABLE phones ADD COLUMN purchase_account_entry_id INTEGER REFERENCES account_entries(id)"),
        ("sale_account_entry_id", "ALTER TABLE phones ADD COLUMN sale_account_entry_id INTEGER REFERENCES account_entries(id)"),
    ):
        if not _column_exists(conn, "phones", col):
            conn.execute(sql)
    if not _column_exists(conn, "phone_expenses", "account_entry_id"):
        conn.execute("ALTER TABLE phone_expenses ADD COLUMN account_entry_id INTEGER REFERENCES account_entries(id)")
    if not _column_exists(conn, "account_entries", "linked_cash_book_entry_id"):
        conn.execute("ALTER TABLE account_entries ADD COLUMN linked_cash_book_entry_id INTEGER REFERENCES cash_book_entries(id)")
    if not _column_exists(conn, "cash_book_entries", "linked_bank_transaction_id"):
        conn.execute("ALTER TABLE cash_book_entries ADD COLUMN linked_bank_transaction_id INTEGER REFERENCES bank_transactions(id)")
    if not _column_exists(conn, "cash_book_entries", "linked_account_entry_id"):
        conn.execute("ALTER TABLE cash_book_entries ADD COLUMN linked_account_entry_id INTEGER REFERENCES account_entries(id)")
    if not _column_exists(conn, "journal_vouchers", "debit_entry_id"):
        conn.execute("ALTER TABLE journal_vouchers ADD COLUMN debit_entry_id INTEGER REFERENCES account_entries(id)")
    if not _column_exists(conn, "journal_vouchers", "credit_entry_id"):
        conn.execute("ALTER TABLE journal_vouchers ADD COLUMN credit_entry_id INTEGER REFERENCES account_entries(id)")


def _record_ledger_link(
    conn, user_id, source_type, source_id, *,
    cash_book_entry_id=None, account_entry_id=None, bank_transaction_id=None,
):
    """Remember that a cash-book/account/bank row belongs to one real-world
    event (source_type + source_id, e.g. ("phone_sale", 42)), so it can be
    found and reversed later if that event is edited or deleted. This is the
    core building block of the ledger sync engine described at the top of
    this file.
    """
    conn.execute(
        """
        INSERT INTO ledger_links (
            user_id, source_type, source_id,
            cash_book_entry_id, account_entry_id, bank_transaction_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, source_type, source_id, cash_book_entry_id, account_entry_id, bank_transaction_id),
    )


def _insert_account_entry(conn, account_id, entry_type, amount, note, *, linked_cash_book_entry_id=None):
    cursor = conn.execute(
        """
        INSERT INTO account_entries (
            account_id, entry_type, amount, note, payment_source, bank_account_id,
            linked_cash_book_entry_id
        ) VALUES (?, ?, ?, ?, '', NULL, ?)
        """,
        (account_id, entry_type, amount, note, linked_cash_book_entry_id),
    )
    return cursor.lastrowid


def _delete_account_entry_raw(conn, entry_id):
    """Delete one account (khata) entry and clear every other table's
    pointer to it first, so nothing is left referencing a row that no
    longer exists. "Raw" means this does NOT reverse cash book/bank
    entries linked to the same event - callers that need the full
    reversal use _reverse_ledger_for_source() instead.
    """
    if entry_id:
        conn.execute(
            "UPDATE phones SET purchase_account_entry_id = NULL WHERE purchase_account_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE phones SET sale_account_entry_id = NULL WHERE sale_account_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE phone_expenses SET account_entry_id = NULL WHERE account_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE cash_book_entries SET linked_account_entry_id = NULL WHERE linked_account_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE journal_vouchers SET debit_entry_id = NULL WHERE debit_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE journal_vouchers SET credit_entry_id = NULL WHERE credit_entry_id = ?",
            (entry_id,),
        )
        conn.execute("DELETE FROM account_entries WHERE id = ?", (entry_id,))


def _delete_cash_book_raw(conn, user_id, entry_id):
    """Same idea as _delete_account_entry_raw() but for a cash book entry:
    clear every pointer to it, then delete the row itself.
    """
    if entry_id:
        conn.execute(
            "UPDATE phones SET purchase_cash_book_entry_id = NULL WHERE purchase_cash_book_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE phones SET sale_cash_book_entry_id = NULL WHERE sale_cash_book_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE phone_expenses SET cash_book_entry_id = NULL WHERE cash_book_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE fixed_expenses SET cash_book_entry_id = NULL WHERE cash_book_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "UPDATE account_entries SET linked_cash_book_entry_id = NULL WHERE linked_cash_book_entry_id = ?",
            (entry_id,),
        )
        conn.execute(
            "DELETE FROM cash_book_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        )


def _delete_bank_tx_raw(conn, tx_id):
    if tx_id:
        conn.execute(
            "UPDATE cash_book_entries SET linked_bank_transaction_id = NULL WHERE linked_bank_transaction_id = ?",
            (tx_id,),
        )
        conn.execute(
            "UPDATE ledger_links SET bank_transaction_id = NULL WHERE bank_transaction_id = ?",
            (tx_id,),
        )
        conn.execute("DELETE FROM bank_transactions WHERE id = ?", (tx_id,))


def _reverse_ledger_for_source(conn, user_id, source_type, source_id):
    """Undo everything that was created for one event.

    Looks up every ledger_links row recorded for (source_type, source_id)
    by _record_ledger_link(), and deletes the cash book / account / bank
    entries they point to. This is what makes "delete a phone sale" (or
    edit one in a way that changes its money side) safe: the linked
    entries elsewhere in the books get cleaned up automatically instead of
    being left behind as orphans that would make totals wrong.
    """
    links = conn.execute(
        """
        SELECT * FROM ledger_links
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        ORDER BY id DESC
        """,
        (user_id, source_type, source_id),
    ).fetchall()
    conn.execute(
        """
        DELETE FROM ledger_links
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (user_id, source_type, source_id),
    )
    seen_cb, seen_ac, seen_bank = set(), set(), set()
    for link in links:
        cb_id = link["cash_book_entry_id"]
        ac_id = link["account_entry_id"]
        bank_id = link["bank_transaction_id"]
        if bank_id and bank_id not in seen_bank:
            _delete_bank_tx_raw(conn, bank_id)
            seen_bank.add(bank_id)
        if cb_id and cb_id not in seen_cb:
            row = conn.execute(
                "SELECT linked_bank_transaction_id, linked_account_entry_id FROM cash_book_entries WHERE id = ?",
                (cb_id,),
            ).fetchone()
            if row:
                if row["linked_bank_transaction_id"] and row["linked_bank_transaction_id"] not in seen_bank:
                    _delete_bank_tx_raw(conn, row["linked_bank_transaction_id"])
                    seen_bank.add(row["linked_bank_transaction_id"])
                if row["linked_account_entry_id"] and row["linked_account_entry_id"] not in seen_ac:
                    _delete_account_entry_raw(conn, row["linked_account_entry_id"])
                    seen_ac.add(row["linked_account_entry_id"])
            _delete_cash_book_raw(conn, user_id, cb_id)
            seen_cb.add(cb_id)
        if ac_id and ac_id not in seen_ac:
            _delete_account_entry_raw(conn, ac_id)
            seen_ac.add(ac_id)


class NegativeBalanceWarning(ValueError):
    """Bug #11: raised instead of posting a cash/bank movement that would
    take the balance below zero, unless the caller passes force=True. A
    subclass of ValueError so existing `except ValueError` handlers still
    catch it (never crashes a route that hasn't been updated yet) -- routes
    that want to offer a confirm-and-retry UI can catch this specific type
    first and surface its structured fields instead of just str(e).

    This is deliberately a soft, force-overridable guard, not a hard block:
    shopkeepers legitimately record entries out of order sometimes (e.g. a
    purchase logged before that morning's cash deposit is entered), and a
    hard block would be more disruptive than the problem it prevents."""

    def __init__(self, target: str, *, current_balance: float, amount: float, name: str = ""):
        self.target = target  # "cash" or "bank"
        self.current_balance = round(current_balance, 2)
        self.amount = round(amount, 2)
        self.resulting_balance = round(current_balance - amount, 2)
        self.name = name
        label = f"{name} " if name else ""
        super().__init__(
            f"This would take {label}{target} balance to "
            f"{self.resulting_balance:,.2f} (currently {self.current_balance:,.2f}). "
            "Confirm to proceed anyway."
        )


def _check_cash_not_negative(conn, user_id, amount, force: bool) -> None:
    if force or amount <= 0:
        return
    current = cash_in_hand_balance(conn, user_id)
    if current - amount < 0:
        raise NegativeBalanceWarning("cash", current_balance=current, amount=amount)


def _check_bank_not_negative(conn, user_id, bank_id, amount, force: bool) -> None:
    if force or amount <= 0:
        return
    current = _bank_balance(conn, bank_id)
    if current - amount < 0:
        bank = get_bank(conn, user_id, bank_id) if user_id else None
        raise NegativeBalanceWarning(
            "bank", current_balance=current, amount=amount,
            name=(bank["name"] if bank else ""),
        )


def _create_cash_book_synced(
    conn, user_id, data, source_type=None, source_id=None, *,
    account_entry_type=None, link_account=True, force=False,
):
    """Create one cash book (physical cash) entry, and - depending on
    payment_source/account_id - also create the matching bank transaction
    and/or account (khata) entry that goes with it, linking all of them
    together via _record_ledger_link() so they can be found and reversed
    as a group later. This is the function almost every "money moved"
    action in the app funnels through, rather than each caller inserting
    raw cash_book_entries rows by hand.
    """
    entry_type = data["entry_type"]
    if entry_type not in CASH_BOOK_TYPES:
        raise ValueError("Invalid entry type")

    payment_source = data.get("payment_source") or "cash"
    if payment_source not in ("cash", "bank"):
        raise ValueError("Payment source must be cash or bank")

    bank_account_id = data.get("bank_account_id")
    if payment_source == "bank":
        if not bank_account_id:
            raise ValueError("Select a bank account")
        bank_account_id = int(bank_account_id)
        if not get_bank(conn, user_id, bank_account_id):
            raise ValueError("Bank account not found")
    else:
        bank_account_id = None

    account_id = data.get("account_id")
    if account_id:
        account_id = int(account_id)
        if not get_account(conn, user_id, account_id):
            raise ValueError("Selected account not found")

    note = data.get("note", "")
    amount = float(data["amount"])
    entry_date = data.get("entry_date") or _local_date(conn)

    if entry_type == "out":
        if payment_source == "cash":
            _check_cash_not_negative(conn, user_id, amount, force)
        elif payment_source == "bank":
            _check_bank_not_negative(conn, user_id, bank_account_id, amount, force)

    cursor = conn.execute(
        """
        INSERT INTO cash_book_entries (
            entry_type, amount, note, entry_date, user_id, account_id,
            payment_source, bank_account_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (entry_type, amount, note, entry_date, user_id, account_id, payment_source, bank_account_id),
    )
    entry_id = cursor.lastrowid
    bank_tx_id = None
    account_entry_id = None

    if payment_source == "bank":
        # force=True here: the bank-negative check for this movement was
        # already done above (with the caller's real `force` value) before
        # any row was written -- this internal post must not re-check and
        # potentially reject a request the caller already confirmed.
        tx = create_bank_transaction(conn, bank_account_id, {
            "transaction_type": "credit" if entry_type == "in" else "debit",
            "amount": amount,
            "note": note or f"Cash book {entry_type} — entry #{entry_id}",
        }, user_id=user_id, force=True)
        bank_tx_id = tx["id"]
        conn.execute(
            "UPDATE cash_book_entries SET linked_bank_transaction_id = ? WHERE id = ?",
            (bank_tx_id, entry_id),
        )

    if account_id and link_account:
        if account_entry_type is None:
            account_entry_type = "credit" if entry_type == "out" else "debit"
        acct_note = note or f"Cash book {entry_type} — entry #{entry_id}"
        account_entry_id = _insert_account_entry(
            conn, account_id, account_entry_type, amount, acct_note,
            linked_cash_book_entry_id=entry_id,
        )
        conn.execute(
            "UPDATE cash_book_entries SET linked_account_entry_id = ? WHERE id = ?",
            (account_entry_id, entry_id),
        )

    if source_type and source_id is not None:
        _record_ledger_link(
            conn, user_id, source_type, source_id,
            cash_book_entry_id=entry_id,
            account_entry_id=account_entry_id,
            bank_transaction_id=bank_tx_id,
        )

    row = conn.execute("SELECT * FROM cash_book_entries WHERE id = ?", (entry_id,)).fetchone()
    result = dict(row)
    result["cash_book_entry_id"] = entry_id
    result["account_entry_id"] = account_entry_id
    result["bank_transaction_id"] = bank_tx_id
    return result


def _create_account_entry_synced(
    conn, user_id, account_id, entry_type, amount, note, *,
    source_type=None, source_id=None, payment_source="", bank_account_id=None,
    mirror_cash_book=False, cash_book_entry_type="in", force=False,
):
    """Create one account (khata) entry - and, if mirror_cash_book=True,
    also create the matching cash book entry (e.g. a "wasool" collection
    both reduces what a customer owes AND adds cash to the till), linking
    the two so a later delete/edit reverses both sides together.
    """
    account_entry_id = _insert_account_entry(conn, account_id, entry_type, amount, note)
    cash_book_entry_id = None
    bank_tx_id = None

    if mirror_cash_book and payment_source == "cash":
        cb = _create_cash_book_synced(conn, user_id, {
            "entry_type": cash_book_entry_type,
            "amount": amount,
            "note": note,
            "payment_source": "cash",
            "entry_date": _local_date(conn),
        }, link_account=False, force=force)
        cash_book_entry_id = cb["cash_book_entry_id"]
        conn.execute(
            "UPDATE account_entries SET payment_source = 'cash', linked_cash_book_entry_id = ? WHERE id = ?",
            (cash_book_entry_id, account_entry_id),
        )
        _record_ledger_link(
            conn, user_id, "account_payment", account_entry_id,
            cash_book_entry_id=cash_book_entry_id,
        )
    elif mirror_cash_book and payment_source == "bank" and bank_account_id:
        cb = _create_cash_book_synced(conn, user_id, {
            "entry_type": cash_book_entry_type,
            "amount": amount,
            "note": note,
            "payment_source": "bank",
            "bank_account_id": bank_account_id,
            "entry_date": _local_date(conn),
        }, link_account=False, force=force)
        cash_book_entry_id = cb["cash_book_entry_id"]
        conn.execute(
            "UPDATE account_entries SET payment_source = 'bank', bank_account_id = ?, linked_cash_book_entry_id = ? WHERE id = ?",
            (bank_account_id, cash_book_entry_id, account_entry_id),
        )
        _record_ledger_link(
            conn, user_id, "account_payment", account_entry_id,
            cash_book_entry_id=cash_book_entry_id,
        )

    if source_type and source_id is not None:
        _record_ledger_link(
            conn, user_id, source_type, source_id,
            account_entry_id=account_entry_id,
            cash_book_entry_id=cash_book_entry_id,
            bank_transaction_id=bank_tx_id,
        )

    row = conn.execute("SELECT * FROM account_entries WHERE id = ?", (account_entry_id,)).fetchone()
    return dict(row)


def _reverse_phone_ledger(conn, user_id, phone_id):
    """Reverse all financial entries tied to a phone."""
    phone = get_phone(conn, user_id, phone_id)
    if not phone:
        return
    conn.execute(
        """
        UPDATE phones SET
            purchase_cash_book_entry_id = NULL,
            sale_cash_book_entry_id = NULL,
            purchase_account_entry_id = NULL,
            sale_account_entry_id = NULL
        WHERE id = ? AND user_id = ?
        """,
        (phone_id, user_id),
    )
    conn.execute(
        """
        UPDATE phone_expenses SET cash_book_entry_id = NULL, account_entry_id = NULL
        WHERE phone_id = ?
        """,
        (phone_id,),
    )
    for source in ("phone_purchase", "phone_sale", "phone_borrow", "phone_receivable", "phone_payable"):
        _reverse_ledger_for_source(conn, user_id, source, phone_id)
    expenses = conn.execute(
        "SELECT id FROM phone_expenses WHERE phone_id = ?", (phone_id,)
    ).fetchall()
    for exp in expenses:
        _reverse_ledger_for_source(conn, user_id, "phone_expense", exp["id"])


def _delete_cash_book_entry_cascade(conn, user_id, entry_id, *, skip_account_entry_id=None):
    """Delete cash book row and linked account/bank rows without double-deleting."""
    if not entry_id:
        return
    row = conn.execute(
        "SELECT * FROM cash_book_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    ).fetchone()
    if not row:
        return

    acct_id = row["linked_account_entry_id"]
    if acct_id and acct_id != skip_account_entry_id:
        _delete_account_entry_cascade(conn, user_id, acct_id, skip_cash_book_id=entry_id)

    bank_id = row["linked_bank_transaction_id"]
    if bank_id:
        _delete_bank_tx_raw(conn, bank_id)

    conn.execute(
        "DELETE FROM ledger_links WHERE cash_book_entry_id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    conn.execute(
        "UPDATE phones SET purchase_cash_book_entry_id = NULL WHERE purchase_cash_book_entry_id = ?",
        (entry_id,),
    )
    conn.execute(
        "UPDATE phones SET sale_cash_book_entry_id = NULL WHERE sale_cash_book_entry_id = ?",
        (entry_id,),
    )
    conn.execute(
        "UPDATE phone_expenses SET cash_book_entry_id = NULL WHERE cash_book_entry_id = ?",
        (entry_id,),
    )
    _delete_cash_book_raw(conn, user_id, entry_id)


def _delete_account_entry_cascade(conn, user_id, entry_id, *, skip_cash_book_id=None):
    """Delete account entry and any mirrored cash book / bank rows."""
    if not entry_id:
        return
    row = conn.execute(
        """
        SELECT ae.* FROM account_entries ae
        JOIN accounts a ON a.id = ae.account_id
        WHERE ae.id = ? AND a.user_id = ?
        """,
        (entry_id, user_id),
    ).fetchone()
    if not row:
        return

    cb_id = row["linked_cash_book_entry_id"]
    if cb_id and cb_id != skip_cash_book_id:
        _delete_cash_book_entry_cascade(conn, user_id, cb_id, skip_account_entry_id=entry_id)

    for cb in conn.execute(
        """
        SELECT id FROM cash_book_entries
        WHERE linked_account_entry_id = ? AND user_id = ?
        """,
        (entry_id, user_id),
    ).fetchall():
        if cb["id"] != skip_cash_book_id:
            _delete_cash_book_entry_cascade(conn, user_id, cb["id"], skip_account_entry_id=entry_id)

    conn.execute(
        "DELETE FROM ledger_links WHERE account_entry_id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    _delete_account_entry_raw(conn, entry_id)


def _local_datetime(conn) -> str:
    return conn.execute("SELECT datetime('now', 'localtime')").fetchone()[0]


def _local_date(conn) -> str:
    return conn.execute("SELECT date('now', 'localtime')").fetchone()[0]


def _normalize_datetime(value, conn, *, date_only=False) -> str:
    if not value:
        return _local_date(conn) if date_only else _local_datetime(conn)
    text = str(value).strip().replace("T", " ")
    if date_only:
        return text[:10]
    if len(text) == 10:
        return f"{text} {_local_datetime(conn)[11:19]}"
    if len(text) == 16:
        return f"{text}:00"
    return text[:19]


def _sold_profit(conn, row) -> float:
    return phone_to_dict(conn, row)["net_profit"] or 0.0


def _migrate_cursor_panga(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number INTEGER NOT NULL,
            customer_name TEXT NOT NULL DEFAULT '',
            customer_phone TEXT NOT NULL DEFAULT '',
            phone_id INTEGER,
            model TEXT NOT NULL DEFAULT '',
            variant TEXT NOT NULL DEFAULT '',
            imei TEXT NOT NULL DEFAULT '',
            phone_type TEXT NOT NULL DEFAULT '',
            condition TEXT NOT NULL DEFAULT '',
            amount REAL NOT NULL DEFAULT 0,
            warranty TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            invoice_date TEXT NOT NULL DEFAULT (date('now')),
            user_id INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _migrate_journal_vouchers(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS journal_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_date TEXT NOT NULL,
            reference TEXT NOT NULL DEFAULT '',
            narration TEXT NOT NULL DEFAULT '',
            debit_account_id INTEGER NOT NULL REFERENCES accounts(id),
            credit_account_id INTEGER NOT NULL REFERENCES accounts(id),
            amount REAL NOT NULL,
            user_id INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _migrate_side_investments(conn):
    """Bug #8: add_side_investment() used to link its cash/bank entry with
    source_id=partner_id -- fine for the link itself, but since every top-up
    a partner ever makes shares that same partner_id, a future "reverse this
    side investment" feature calling the generic _reverse_ledger_for_source()
    with (source_type='side_investment', source_id=partner_id) would delete
    EVERY top-up that partner ever made, not just one. This table gives each
    top-up its own row id to use as source_id instead, so it's unambiguous.
    Existing ledger_links rows from before this fix (source_id=partner_id)
    are deliberately left as-is -- there's no way to retroactively figure out
    which individual top-up each one was -- reverse_side_investment() below
    detects and refuses to touch those instead of guessing."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS side_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL REFERENCES partners(id),
            amount REAL NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            investment_date TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _migrate_multi_user(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            shop_name TEXT NOT NULL DEFAULT 'My Phone Shop',
            theme TEXT NOT NULL DEFAULT 'default-dark',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        """
    )

    for table in USER_SCOPED_TABLES:
        if not _column_exists(conn, table, "user_id"):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )

    user_row = conn.execute(
        "SELECT id FROM users ORDER BY id ASC LIMIT 1"
    ).fetchone()
    if user_row:
        default_user_id = user_row["id"]
        for table in USER_SCOPED_TABLES:
            conn.execute(
                f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
                (default_user_id,),
            )


def _migrate_purchase_invoices(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS purchase_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number INTEGER NOT NULL,
            supplier_name TEXT NOT NULL DEFAULT '',
            supplier_contact TEXT NOT NULL DEFAULT '',
            phone_id INTEGER,
            model TEXT NOT NULL DEFAULT '',
            variant TEXT NOT NULL DEFAULT '',
            imei TEXT NOT NULL DEFAULT '',
            phone_type TEXT NOT NULL DEFAULT '',
            condition TEXT NOT NULL DEFAULT '',
            amount REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            invoice_date TEXT NOT NULL DEFAULT (date('now')),
            user_id INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _migrate_indexes(conn):
    """Add indexes on the columns every list/report screen filters or joins
    on. Missing until now — fine with a handful of phones, but every screen
    becomes a full table scan as a shop's history grows into the thousands
    of rows. Purely additive, no data is touched."""
    indexes = (
        ("idx_phones_user_id", "phones", "user_id"),
        ("idx_phones_imei", "phones", "imei"),
        ("idx_phones_imei2", "phones", "imei2"),
        ("idx_accounts_user_id", "accounts", "user_id"),
        ("idx_account_entries_account_id", "account_entries", "account_id"),
        ("idx_cash_book_user_id", "cash_book_entries", "user_id"),
        ("idx_cash_book_account_id", "cash_book_entries", "account_id"),
        ("idx_cash_book_bank_account_id", "cash_book_entries", "bank_account_id"),
        ("idx_phone_expenses_phone_id", "phone_expenses", "phone_id"),
        ("idx_phone_expenses_account_id", "phone_expenses", "account_id"),
        ("idx_bank_transactions_bank_account_id", "bank_transactions", "bank_account_id"),
        ("idx_journal_vouchers_user_id", "journal_vouchers", "user_id"),
        ("idx_invoices_user_id", "invoices", "user_id"),
        ("idx_purchase_invoices_user_id", "purchase_invoices", "user_id"),
        ("idx_side_investments_user_id", "side_investments", "user_id"),
        ("idx_side_investments_partner_id", "side_investments", "partner_id"),
    )
    for name, table, column in indexes:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({column})")


def _dedupe_invoice_numbers(conn, table: str) -> None:
    """Bug #7: invoice_number was never unique per user — duplicates were
    possible (e.g. the billing/purchase-invoice forms pre-fill this field
    from an existing invoice when you view/reprint it, and re-submitting
    creates a second row with the same number). Run before adding the
    UNIQUE(user_id, invoice_number) index below so that index creation can
    never fail on a customer database that already has some: for each
    duplicate group, the oldest row keeps its number and every later
    duplicate is renumbered to the next free number for that user."""
    dupe_groups = conn.execute(
        f"""
        SELECT user_id, invoice_number FROM {table}
        GROUP BY user_id, invoice_number
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for group in dupe_groups:
        user_id, number = group["user_id"], group["invoice_number"]
        rows = conn.execute(
            f"""
            SELECT id FROM {table}
            WHERE user_id = ? AND invoice_number = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, number),
        ).fetchall()
        next_free = conn.execute(
            f"SELECT COALESCE(MAX(invoice_number), 0) + 1 AS n FROM {table} WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]
        for row in rows[1:]:  # rows[0] (oldest) keeps its original number
            conn.execute(
                f"UPDATE {table} SET invoice_number = ? WHERE id = ?",
                (next_free, row["id"]),
            )
            print(
                f"[invoice dedupe] {table}: user {user_id} invoice #{number} "
                f"(row id {row['id']}) was a duplicate — renumbered to #{next_free}"
            )
            next_free += 1


def _migrate_unique_invoice_numbers(conn) -> None:
    """Repair any existing duplicates, then enforce uniqueness going forward.
    Runs unconditionally every startup like _migrate_indexes() above (not
    gated behind the versioned SCHEMA_MIGRATIONS system): a brand-new
    database has zero rows so dedup is a no-op and the index is created
    fresh; an existing database gets deduped first so the index creation
    itself can never fail on data that predates this fix."""
    for table in ("invoices", "purchase_invoices"):
        _dedupe_invoice_numbers(conn, table)
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_user_invoice_unique "
            f"ON {table}(user_id, invoice_number)"
        )


def _copy_legacy_settings_to_user(conn, user_id, legacy=None):
    legacy = legacy or {}
    for key in ("partner1_name", "partner1_capital", "partner2_name", "partner2_capital", "cash_in_hand"):
        value = legacy.get(key, DEFAULT_SETTINGS.get(key, ""))
        conn.execute(
            """
            INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
            """,
            (user_id, key, str(value)),
        )


def _seed_user_partners(conn, user_id, settings=None):
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM partners WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    if count > 0:
        return
    settings = settings or get_user_settings(conn, user_id)
    partners = [
        (settings.get("partner1_name", "Partner 1"), float(settings.get("partner1_capital", 0))),
        (settings.get("partner2_name", "Partner 2"), float(settings.get("partner2_capital", 0))),
    ]
    for name, capital in partners:
        if name:
            conn.execute(
                "INSERT INTO partners (name, capital, user_id) VALUES (?, ?, ?)",
                (name, capital, user_id),
            )


def get_user(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def backup_username_slug(conn, user_id: int) -> str:
    user = get_user(conn, user_id)
    if not user:
        return "user"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (user.get("username") or "user").strip())
    return (slug[:32] or "user").lower()


def ensure_user_backup_path(conn, user_id: int) -> str:
    settings = get_user_settings(conn, user_id)
    current = (settings.get("local_backup_path") or "").strip()
    desired = str(default_backup_dir()) if default_backup_dir() else ""
    if current and path_is_inside_app_bundle(current) and desired:
        update_user_settings(conn, user_id, {"local_backup_path": desired})
        return desired
    if current:
        return current
    if not desired:
        return ""
    Path(desired).mkdir(parents=True, exist_ok=True)
    update_user_settings(conn, user_id, {"local_backup_path": desired})
    return desired


def ensure_customer_data_layout(conn) -> None:
    """Create Data/Backups for Customer Copy and migrate legacy crm.db if needed."""
    global _CUSTOMER_LAYOUT_READY
    if _CUSTOMER_LAYOUT_READY or not getattr(sys, "frozen", False):
        return

    data_dir = customer_data_dir()
    backup_dir = default_backup_dir()
    if not data_dir or not backup_dir:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    install_dir = customer_install_dir()
    legacy_candidates = [
        install_dir / "crm.db",
        executable_dir() / "crm.db",
        executable_dir() / "Data" / "crm.db",
    ]
    for legacy_db in legacy_candidates:
        if not legacy_db.is_file():
            continue
        if legacy_db.resolve() == DB_PATH.resolve():
            continue
        if not DB_PATH.is_file():
            shutil.move(str(legacy_db), str(DB_PATH))
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(legacy_db, backup_dir / f"legacy_crm_backup_{stamp}.db")

    users = conn.execute("SELECT id FROM users").fetchall()
    for row in users:
        ensure_user_backup_path(conn, row["id"])

    _CUSTOMER_LAYOUT_READY = True


def get_user_settings(conn, user_id):
    settings = dict(DEFAULT_SETTINGS)
    rows = conn.execute(
        "SELECT key, value FROM user_settings WHERE user_id = ?", (user_id,)
    ).fetchall()
    for row in rows:
        settings[row["key"]] = row["value"]
    user = get_user(conn, user_id)
    if user:
        settings["shop_name"] = user["shop_name"]
        settings["theme"] = user["theme"]
    return settings


def get_shop_info(conn, user_id):
    """Shop letterhead details for printed invoices."""
    settings = get_user_settings(conn, user_id)
    phones_raw = settings.get("shop_phones", "[]")
    try:
        phones = json.loads(phones_raw) if phones_raw else []
    except json.JSONDecodeError:
        phones = []
    if not isinstance(phones, list):
        phones = []
    return {
        "shop_name": settings.get("shop_name", DEFAULT_SETTINGS["shop_name"]),
        "shop_address": settings.get("shop_address", ""),
        "shop_phones": [str(p).strip() for p in phones if str(p).strip()],
        "shop_whatsapp": settings.get("shop_whatsapp", ""),
        "shop_logo": settings.get("shop_logo", ""),
    }


def get_storage_settings(conn, user_id):
    """Return database path and user-configured backup preferences."""
    if getattr(sys, "frozen", False):
        ensure_user_backup_path(conn, user_id)
    settings = get_user_settings(conn, user_id)
    backup_path = (settings.get("local_backup_path") or "").strip()
    if not backup_path and default_backup_dir():
        backup_path = str(default_backup_dir())
    return {
        "database_path": str(DB_PATH.resolve()),
        "local_backup_path": backup_path,
        "auto_backup_enabled": settings.get("auto_backup_enabled", "true") == "true",
        "last_backup_at": settings.get("last_backup_at", ""),
        "auto_backup_interval_hours": 1,
    }


def update_storage_settings(conn, user_id, data):
    """Persist backup path and auto-backup toggle.

    Bug #17: this used to also carry a "Google Drive sync" setting that had
    no real sync logic behind it anywhere and no UI to toggle it either --
    a dead placeholder promising something that didn't exist. Removed
    entirely rather than left half-wired. If real cloud sync is ever built,
    see the backlog (Changes To Be Done.txt / artifacts/AI_HANDOFF_NOTES.md)
    for the "Google Drive sync is a dead placeholder" note and design it properly
    then, rather than resurrecting this toggle."""
    payload = {}
    if "local_backup_path" in data:
        payload["local_backup_path"] = str(data.get("local_backup_path") or "").strip()
    if "auto_backup_enabled" in data:
        payload["auto_backup_enabled"] = "true" if data.get("auto_backup_enabled") else "false"
    if payload:
        update_user_settings(conn, user_id, payload)
    return get_storage_settings(conn, user_id)


def update_user_settings(conn, user_id, data):
    allowed = {
        "partner1_name", "partner1_capital", "partner2_name", "partner2_capital",
        "cash_in_hand", "theme", "shop_name", "shop_address", "shop_phones", "shop_logo",
        "local_backup_path",
        "last_backup_at", "auto_backup_enabled",
        "shop_whatsapp", "vendor_whatsapp", "vendor_support_note",
        "gmail_smtp_user", "gmail_smtp_app_password", "invoice_counter",
        "purchase_invoice_counter", "profit_reinvested_total",
    }
    # Bug #14: this used to silently `continue` past any key not in
    # `allowed` -- which is exactly how purchase_invoice_counter's own save
    # (a few lines below, in _next_purchase_invoice_number) went missing
    # for who knows how long without a single error anywhere. An unknown
    # key is now loud instead: a future settings key added here without
    # updating this set fails immediately, not silently.
    unknown = [k for k in data if k not in allowed]
    if unknown:
        raise ValueError(f"Unknown setting key(s): {', '.join(sorted(unknown))}")
    user_fields = {}
    for key, value in data.items():
        if key in ("theme", "shop_name"):
            user_fields[key] = str(value)
        elif key == "shop_phones":
            if isinstance(value, list):
                stored = json.dumps([str(p).strip() for p in value if str(p).strip()])
            else:
                stored = str(value or "[]")
            conn.execute(
                """
                INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
                """,
                (user_id, key, stored),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
                """,
                (user_id, key, str(value)),
            )
    if user_fields:
        if "shop_name" in user_fields:
            conn.execute(
                "UPDATE users SET shop_name = ? WHERE id = ?",
                (user_fields["shop_name"], user_id),
            )
        if "theme" in user_fields:
            conn.execute(
                "UPDATE users SET theme = ? WHERE id = ?",
                (user_fields["theme"], user_id),
            )


# --- Auth ---

def auth_is_configured(conn):
    return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] > 0


def get_auth_config(conn, user_id=None):
    if user_id:
        user = get_user(conn, user_id)
        if not user:
            return {"configured": auth_is_configured(conn)}
        return {
            "configured": True,
            "username": user["username"],
            "shop_name": user["shop_name"],
            "theme": user["theme"],
            **get_shop_info(conn, user_id),
        }
    return {"configured": auth_is_configured(conn)}


def verify_login(conn, username, password):
    """Check a username/password against the stored hash. Returns the user
    row on success, None on failure. Passwords are never stored as plain
    text - check_password_hash compares against a one-way hash created by
    register_user()'s generate_password_hash() call, so even someone with
    direct access to the database file can't read anyone's actual password.
    """
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    return {
        "user_id": row["id"],
        "username": row["username"],
        "shop_name": row["shop_name"],
        "theme": row["theme"],
    }


def register_user(conn, username, password, email="", shop_name=""):
    username = username.strip()
    email = email.strip()
    shop_name = shop_name.strip() or DEFAULT_SETTINGS["shop_name"]
    if not username or not password:
        raise ValueError("Username and password are required")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()
    if existing:
        raise ValueError("Username already taken")
    cursor = conn.execute(
        """
        INSERT INTO users (username, password_hash, email, shop_name)
        VALUES (?, ?, ?, ?)
        """,
        (username, generate_password_hash(password, method=PASSWORD_HASH_METHOD), email, shop_name),
    )
    user_id = cursor.lastrowid
    user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if user_count == 1:
        legacy = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM settings").fetchall()
        }
        _copy_legacy_settings_to_user(conn, user_id, legacy)
        _seed_user_partners(conn, user_id, legacy)
        for table in USER_SCOPED_TABLES:
            conn.execute(
                f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
                (user_id,),
            )
        seed_expense_accounts(conn, user_id)
    else:
        _copy_legacy_settings_to_user(conn, user_id)
        _seed_user_partners(conn, user_id)
    seed_expense_accounts(conn, user_id)
    ensure_user_backup_path(conn, user_id)
    user = get_user(conn, user_id)
    return {
        "user_id": user["id"],
        "username": user["username"],
        "shop_name": user["shop_name"],
        "theme": user["theme"],
    }


def get_email_settings(conn, user_id=None):
    """Global SMTP settings (first admin user or specified user)."""
    if user_id is None:
        row = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
        user_id = row["id"] if row else None
    if not user_id:
        return {"gmail_smtp_user": "", "gmail_configured": False}
    settings = get_user_settings(conn, user_id)
    user = settings.get("gmail_smtp_user", "")
    pwd = settings.get("gmail_smtp_app_password", "")
    return {
        "gmail_smtp_user": user,
        "gmail_configured": bool(user and pwd),
        "vendor_whatsapp": settings.get("vendor_whatsapp", ""),
        "vendor_support_note": settings.get(
            "vendor_support_note", DEFAULT_SETTINGS["vendor_support_note"]
        ),
    }


def get_vendor_reset_info(conn):
    settings = get_email_settings(conn)
    return {
        "vendor_whatsapp": settings.get("vendor_whatsapp", ""),
        "vendor_support_note": settings.get("vendor_support_note", ""),
        "gmail_configured": settings.get("gmail_configured", False),
    }


# --- OTP rate limiting (bug #16) ---
#
# A 6-digit OTP is only as safe as the number of guesses an attacker gets.
# In-memory is fine here: this is a single local desktop process per shop,
# not a multi-worker web server where state would need to be shared.
_OTP_ATTEMPT_WINDOW_SECONDS = 15 * 60
_OTP_MAX_ATTEMPTS = 5
_OTP_LOCKOUT_SECONDS = 15 * 60
_OTP_EXPIRY_MINUTES = 10

_otp_rate_lock = threading.Lock()
_otp_attempts: dict[str, list[float]] = {}
_otp_lockout_until: dict[str, float] = {}


def _otp_rate_limit_check(email: str) -> None:
    """Raises ValueError if this email identifier is currently locked out
    from OTP verification attempts."""
    now = time.time()
    with _otp_rate_lock:
        lockout_until = _otp_lockout_until.get(email)
        if lockout_until and now < lockout_until:
            wait_minutes = max(1, int((lockout_until - now) // 60) + 1)
            raise ValueError(
                f"Too many incorrect attempts — try again in about {wait_minutes} minute(s)."
            )


def _otp_rate_limit_record_attempt(email: str) -> None:
    """Record one failed verification attempt; locks the identifier out for
    _OTP_LOCKOUT_SECONDS once _OTP_MAX_ATTEMPTS is reached within the
    rolling _OTP_ATTEMPT_WINDOW_SECONDS window."""
    now = time.time()
    with _otp_rate_lock:
        attempts = [t for t in _otp_attempts.get(email, []) if now - t < _OTP_ATTEMPT_WINDOW_SECONDS]
        attempts.append(now)
        _otp_attempts[email] = attempts
        if len(attempts) >= _OTP_MAX_ATTEMPTS:
            _otp_lockout_until[email] = now + _OTP_LOCKOUT_SECONDS


def _otp_rate_limit_clear(email: str) -> None:
    """Reset rate-limit state for this identifier after a successful reset."""
    with _otp_rate_lock:
        _otp_attempts.pop(email, None)
        _otp_lockout_until.pop(email, None)


def request_password_reset(conn, email):
    email = email.strip().lower()
    if not email:
        raise ValueError("Email is required")
    row = conn.execute(
        "SELECT id, shop_name FROM users WHERE lower(email) = ?", (email,)
    ).fetchone()
    if not row:
        raise ValueError("No account found with that email")

    # Use the REQUESTING user's own SMTP settings, never another account's —
    # this used to always resolve to user id 1's Gmail credentials regardless
    # of who was actually requesting the reset, silently sending (or failing
    # to send) OTPs using a stranger's mailbox. The generic vendor-contact
    # fallback below stays global by design (it's the vendor's own WhatsApp/
    # support note, shown on the login page before anyone is authenticated,
    # not a personal credential).
    email_cfg = get_email_settings(conn, row["id"])
    if not email_cfg["gmail_configured"]:
        info = get_vendor_reset_info(conn)
        wa = info.get("vendor_whatsapp") or ""
        msg = info.get("vendor_support_note") or "Contact your vendor to reset your password."
        if wa:
            msg += f" WhatsApp: {wa}"
        return {
            "ok": True,
            "email_sent": False,
            "vendor_fallback": True,
            "vendor_whatsapp": wa,
            "message": msg,
        }

    otp = f"{random.randint(100000, 999999)}"
    expires = (datetime.utcnow() + timedelta(minutes=_OTP_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0",
        (row["id"],),
    )
    conn.execute(
        """
        INSERT INTO password_reset_tokens (user_id, email, otp, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (row["id"], email, otp, expires),
    )

    import email_service
    requester_settings = get_user_settings(conn, row["id"])
    email_service.send_otp_email(
        email,
        otp,
        smtp_user=requester_settings["gmail_smtp_user"],
        smtp_password=requester_settings["gmail_smtp_app_password"],
        shop_name=row["shop_name"] or requester_settings.get("shop_name", "Phone Reseller CRM"),
    )
    return {
        "ok": True,
        "email_sent": True,
        "vendor_fallback": False,
        "message": f"OTP sent to {email}. Check your inbox (and spam folder).",
    }


def verify_otp_and_reset_password(conn, email, otp, new_password):
    email = email.strip().lower()
    otp = (otp or "").strip()
    if not email or not otp:
        raise ValueError("Email and OTP are required")
    if not new_password or len(new_password) < 6:
        raise ValueError("New password must be at least 6 characters")

    # Bug #16: check BEFORE touching the DB, so a locked-out identifier
    # can't keep spending guesses just because each individual check below
    # is cheap -- the lockout itself has to be the first gate.
    _otp_rate_limit_check(email)

    user = conn.execute(
        "SELECT id FROM users WHERE lower(email) = ?", (email,)
    ).fetchone()
    if not user:
        _otp_rate_limit_record_attempt(email)
        raise ValueError("Invalid email or OTP")

    token = conn.execute(
        """
        SELECT * FROM password_reset_tokens
        WHERE user_id = ? AND lower(email) = ? AND otp = ? AND used = 0
        ORDER BY id DESC LIMIT 1
        """,
        (user["id"], email, otp),
    ).fetchone()
    if not token:
        _otp_rate_limit_record_attempt(email)
        raise ValueError("Invalid or expired OTP")

    if token["expires_at"] < datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        _otp_rate_limit_record_attempt(email)
        raise ValueError("OTP has expired — request a new one")

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password, method=PASSWORD_HASH_METHOD), user["id"]),
    )
    conn.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE id = ?",
        (token["id"],),
    )
    _otp_rate_limit_clear(email)
    return {"ok": True, "message": "Password updated. You can sign in now."}


def update_auth_credentials(conn, user_id, data):
    user = get_user(conn, user_id)
    if not user:
        raise ValueError("User not found")
    current_password = data.get("current_password", "")
    if not current_password or not check_password_hash(user["password_hash"], current_password):
        raise ValueError("Current password is incorrect")

    new_username = (data.get("username") or "").strip()
    new_password = data.get("new_password")
    shop_name = data.get("shop_name")

    if new_username and new_username.lower() != user["username"].lower():
        taken = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE AND id != ?",
            (new_username, user_id),
        ).fetchone()
        if taken:
            raise ValueError("Username already taken")
        conn.execute(
            "UPDATE users SET username = ? WHERE id = ?",
            (new_username, user_id),
        )
    if new_password:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password, method=PASSWORD_HASH_METHOD), user_id),
        )
    if shop_name is not None:
        conn.execute(
            "UPDATE users SET shop_name = ? WHERE id = ?",
            (shop_name.strip(), user_id),
        )
    return get_auth_config(conn, user_id)


# --- Partners ---

def list_partners(conn, user_id):
    rows = conn.execute(
        "SELECT * FROM partners WHERE user_id = ? ORDER BY id ASC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_partner(conn, user_id, partner_id):
    row = conn.execute(
        "SELECT * FROM partners WHERE id = ? AND user_id = ?",
        (partner_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def create_partner(conn, user_id, data):
    cursor = conn.execute(
        "INSERT INTO partners (name, capital, user_id) VALUES (?, ?, ?)",
        (data["name"], float(data.get("capital", 0)), user_id),
    )
    return get_partner(conn, user_id, cursor.lastrowid)


def update_partner(conn, user_id, partner_id, data):
    existing = get_partner(conn, user_id, partner_id)
    if not existing:
        return None
    fields, values = [], []
    for field in ("name", "capital"):
        if field in data:
            fields.append(f"{field} = ?")
            val = data[field]
            if field == "capital":
                val = float(val) if val not in (None, "") else 0
            values.append(val)
    if fields:
        values.extend([partner_id, user_id])
        conn.execute(
            f"UPDATE partners SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
    return get_partner(conn, user_id, partner_id)


def delete_partner(conn, user_id, partner_id):
    investment = conn.execute(
        "SELECT COUNT(*) AS c FROM phone_investments WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()
    if investment["c"] > 0:
        raise ValueError(
            f"Can't delete this partner — they're linked to {investment['c']} phone "
            "investment record(s), and deleting would erase that history. "
            "Remove those investment links first if you're sure."
        )
    conn.execute(
        "DELETE FROM partners WHERE id = ? AND user_id = ?",
        (partner_id, user_id),
    )


def reinvest_profit(conn, user_id, data):
    """Move available profit into a partner's invested capital."""
    if not conn.in_transaction:
        # Same read-then-write race as create_phone/update_phone: without this
        # lock, two near-simultaneous reinvest calls could both read the same
        # stale "available profit" and both pass the check, over-reinvesting.
        conn.execute("BEGIN IMMEDIATE")
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    partner_id = int(data["partner_id"])
    partner = get_partner(conn, user_id, partner_id)
    if not partner:
        raise ValueError("Partner not found")

    sold = conn.execute(
        """
        SELECT purchase_price, sale_price FROM phones
        WHERE status = 'Sold' AND user_id = ?
        """,
        (user_id,),
    ).fetchall()
    total_net_profit = sum(_sold_profit(conn, r) for r in sold)
    settings = get_user_settings(conn, user_id)
    reinvested = float(settings.get("profit_reinvested_total") or 0)
    available = round(total_net_profit - reinvested, 2)
    if amount > available + 0.01:
        raise ValueError(f"Only {available:,.0f} profit available to reinvest")

    new_capital = round(partner["capital"] + amount, 2)
    update_partner(conn, user_id, partner_id, {"capital": new_capital})
    update_user_settings(conn, user_id, {
        "profit_reinvested_total": str(round(reinvested + amount, 2)),
    })
    return {
        "partner": get_partner(conn, user_id, partner_id),
        "amount_reinvested": round(amount, 2),
        "profit_reinvested_total": round(reinvested + amount, 2),
        "available_profit": round(available - amount, 2),
    }


def add_side_investment(conn, user_id, data):
    """Record a partner injecting fresh capital into the business at any
    time, separate from any specific phone purchase. Unlike reinvest_profit
    (an internal transfer of already-earned profit), this is real money
    entering the business, so it also posts a bank/cash credit.

    Each call gets its own side_investments row, and THAT row's id (not the
    partner's id) is what's used as the ledger_links source_id -- so each
    top-up is independently identifiable and reversible (see
    reverse_side_investment below). Using partner_id here directly would
    mean every top-up a partner ever makes shares one identity, and
    reversing one could reverse all of them."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    amount = float(data.get("amount") or 0)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    partner_id = int(data["partner_id"])
    partner = get_partner(conn, user_id, partner_id)
    if not partner:
        raise ValueError("Partner not found")

    payment_method = data.get("payment_method") or "cash"
    bank_id = data.get("bank_id")
    entry_date = _normalize_datetime(data.get("investment_date"), conn, date_only=True)
    note = data.get("note") or f"Side investment from {partner['name']}"

    cursor = conn.execute(
        """
        INSERT INTO side_investments (partner_id, amount, note, investment_date, user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (partner_id, amount, note, entry_date, user_id),
    )
    investment_id = cursor.lastrowid

    _post_payment_transaction(
        conn, user_id, payment_method, bank_id, "in", amount, note, entry_date,
        source_type="side_investment", source_id=investment_id,
    )

    new_capital = round(partner["capital"] + amount, 2)
    update_partner(conn, user_id, partner_id, {"capital": new_capital})
    return {
        "partner": get_partner(conn, user_id, partner_id),
        "investment_id": investment_id,
        "amount": round(amount, 2),
    }


def reverse_side_investment(conn, user_id, investment_id):
    """Undo exactly one side-investment top-up: reverses its cash/bank
    ledger entry and subtracts it back off the partner's capital.

    The safety check is keyed directly off ledger_links, not off whether a
    side_investments row exists for this id -- refuses (raises ValueError)
    unless (source_type='side_investment', source_id=investment_id) resolves
    to EXACTLY one linked transaction. For any investment created after this
    fix that's always true (_post_payment_transaction / _create_cash_book_synced
    create exactly one ledger_links row per call), since its source_id is
    this row's own unique id. For a legacy row from before this fix --
    where source_id was the partner's own id, shared by every top-up that
    partner ever made -- this count will usually be 0 or >1 and gets
    refused instead of guessing which cash book entry to delete."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")

    links = conn.execute(
        """
        SELECT * FROM ledger_links
        WHERE user_id = ? AND source_type = 'side_investment' AND source_id = ?
        """,
        (user_id, investment_id),
    ).fetchall()
    if len(links) != 1:
        raise ValueError(
            "Cannot safely reverse this side investment: its ledger data is "
            "ambiguous or missing (predates per-event tracking and may be "
            "shared with other top-ups for this partner). Reverse the "
            "linked Cash Book or Bank Account entry manually instead."
        )

    cb_id = links[0]["cash_book_entry_id"]
    cb_row = conn.execute(
        "SELECT amount FROM cash_book_entries WHERE id = ? AND user_id = ?",
        (cb_id, user_id),
    ).fetchone() if cb_id else None
    if not cb_row:
        raise ValueError("Cannot safely reverse this side investment: its cash book entry is missing")
    amount = cb_row["amount"]

    investment = conn.execute(
        "SELECT * FROM side_investments WHERE id = ? AND user_id = ?",
        (investment_id, user_id),
    ).fetchone()
    partner_id = investment["partner_id"] if investment else None

    _reverse_ledger_for_source(conn, user_id, "side_investment", investment_id)
    if investment:
        conn.execute("DELETE FROM side_investments WHERE id = ?", (investment_id,))

    if partner_id:
        partner = get_partner(conn, user_id, partner_id)
        if partner:
            new_capital = round(partner["capital"] - amount, 2)
            update_partner(conn, user_id, partner_id, {"capital": new_capital})

    return {"ok": True, "reversed_amount": round(amount, 2)}


# --- Phones ---

def _phone_expense_total(conn, phone_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM phone_expenses WHERE phone_id = ?",
        (phone_id,),
    ).fetchone()
    return round(row["total"] or 0, 2)


def _phone_investments(conn, phone_id):
    rows = conn.execute(
        """
        SELECT pi.*, p.name AS partner_name
        FROM phone_investments pi
        JOIN partners p ON p.id = pi.partner_id
        WHERE pi.phone_id = ?
        ORDER BY pi.id ASC
        """,
        (phone_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _phone_expenses(conn, phone_id):
    rows = conn.execute(
        "SELECT * FROM phone_expenses WHERE phone_id = ? ORDER BY created_at DESC, id DESC",
        (phone_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def phone_to_dict(conn, row, include_details=False):
    d = dict(row)
    purchase = d["purchase_price"] or 0
    sale = d["sale_price"] or 0
    expense_total = _phone_expense_total(conn, d["id"])
    d["expense_total"] = expense_total
    d["total_costing"] = round(purchase + expense_total, 2)
    d["net_profit"] = round(sale - purchase - expense_total, 2) if d["status"] == "Sold" else None
    if include_details:
        d["expenses"] = _phone_expenses(conn, d["id"])
        d["investments"] = _phone_investments(conn, d["id"])
    return d


def list_phones(conn, user_id):
    rows = conn.execute(
        "SELECT * FROM phones WHERE user_id = ? ORDER BY created_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    return [phone_to_dict(conn, r) for r in rows]


def get_phone(conn, user_id, phone_id, include_details=False):
    row = conn.execute(
        "SELECT * FROM phones WHERE id = ? AND user_id = ?",
        (phone_id, user_id),
    ).fetchone()
    return phone_to_dict(conn, row, include_details) if row else None


def _build_phone_insert_values(conn, data, status=None):
    status = status or data.get("status", "Bought")
    if status not in PHONE_STATUSES:
        status = "Bought"

    sale_price = None
    receivable = 0.0
    buyer_name = ""
    buyer_contact = ""
    if status == "Sold":
        sale_price = float(data.get("sale_price") or 0)
        receivable = float(data.get("receivable_amount") or 0)
        buyer_name = data.get("buyer_name", "")
        buyer_contact = data.get("buyer_contact", "")

    return (
        data["model"],
        data.get("condition", ""),
        data["type"],
        float(data["purchase_price"]),
        data.get("supplier_name", ""),
        data.get("supplier_contact", ""),
        status,
        float(data.get("payable_amount", 0)),
        float(data.get("advance_received", 0)),
        buyer_name,
        buyer_contact,
        sale_price,
        receivable,
        _normalize_datetime(data.get("sold_at"), conn) if status == "Sold" else None,
        data.get("imei", ""),
        data.get("imei2", ""),
        data.get("box_status", ""),
        data.get("battery_health", ""),
        data.get("variant", ""),
        _normalize_datetime(data.get("purchase_date"), conn, date_only=True),
    )


def _save_phone_extras(conn, user_id, phone_id, data):
    expenses = data.get("expenses") or []
    for exp in expenses:
        if float(exp.get("amount") or 0) > 0:
            add_phone_expense(conn, user_id, phone_id, {
                "amount": exp["amount"],
                "description": exp.get("description", ""),
                "expense_date": exp.get("expense_date") or "",
                "account_id": exp.get("account_id"),
            })

    investments = data.get("investments") or []
    for inv in investments:
        partner_id = inv.get("partner_id")
        amount = float(inv.get("amount") or 0)
        if partner_id and amount > 0:
            conn.execute(
                """
                INSERT INTO phone_investments (phone_id, partner_id, amount)
                VALUES (?, ?, ?)
                ON CONFLICT(phone_id, partner_id) DO UPDATE SET amount = excluded.amount
                """,
                (phone_id, partner_id, amount),
            )


def _post_payment_transaction(
    conn, user_id, payment_method, bank_id, entry_type, amount, note, entry_date,
    *, source_type=None, source_id=None, account_id=None, account_entry_type=None,
    force=False,
):
    """Record cash book or bank movement with optional account link."""
    if amount <= 0:
        return None
    data = {
        "entry_type": entry_type,
        "amount": amount,
        "note": note,
        "entry_date": entry_date,
        "payment_source": "bank" if payment_method == "bank" else "cash",
        "bank_account_id": int(bank_id) if payment_method == "bank" and bank_id else None,
        "account_id": account_id,
    }
    if payment_method == "bank" and not bank_id:
        raise ValueError("Select a bank account for bank payment")
    if payment_method == "bank" and not get_bank(conn, user_id, int(bank_id)):
        raise ValueError("Bank account not found")
    return _create_cash_book_synced(
        conn, user_id, data,
        source_type=source_type, source_id=source_id,
        account_entry_type=account_entry_type,
        force=force,
    )


def _post_purchase_ledger(conn, user_id, phone_id, data):
    """Sync purchase/borrow to cash book and supplier account."""
    force = bool(data.get("force"))
    acquisition = (data.get("acquisition_type") or "purchase").strip().lower()
    purchase_price = float(data.get("purchase_price") or 0)
    payable = float(data.get("payable_amount") or 0)
    supplier_account_id = data.get("supplier_account_id")
    if supplier_account_id not in (None, "", 0):
        supplier_account_id = int(supplier_account_id)
    else:
        supplier_account_id = None

    if acquisition == "borrow":
        if not supplier_account_id:
            raise ValueError("Select a shopkeeper account when borrowing a phone")
        payable = purchase_price
        data = {**data, "payable_amount": payable}

    paid_now = max(0.0, purchase_price - payable)
    model = data.get("model", "Phone")
    entry_date = _normalize_datetime(data.get("purchase_date"), conn, date_only=True)
    method = data.get("purchase_payment_method") or "cash"
    bank_id = data.get("purchase_bank_id")

    purchase_cb_id = None
    purchase_acct_id = None

    if paid_now > 0:
        cb = _post_payment_transaction(
            conn, user_id, method, bank_id, "out", paid_now,
            f"Purchase: {model} (#{phone_id})", entry_date,
            source_type="phone_purchase", source_id=phone_id,
            account_id=supplier_account_id,
            account_entry_type="credit" if supplier_account_id else None,
            force=force,
        )
        if cb:
            purchase_cb_id = cb.get("cash_book_entry_id") or cb.get("id")

    if payable > 0 and supplier_account_id:
        note = f"{'Borrow' if acquisition == 'borrow' else 'Udhar'}: {model} (#{phone_id})"
        acct_type = "debit"
        purchase_acct_id = _insert_account_entry(
            conn, supplier_account_id, acct_type, payable, note,
        )
        _record_ledger_link(
            conn, user_id,
            "phone_borrow" if acquisition == "borrow" else "phone_payable",
            phone_id, account_entry_id=purchase_acct_id,
        )

    if purchase_cb_id or purchase_acct_id:
        conn.execute(
            """
            UPDATE phones SET
                purchase_cash_book_entry_id = COALESCE(?, purchase_cash_book_entry_id),
                purchase_account_entry_id = COALESCE(?, purchase_account_entry_id),
                payable_amount = ?,
                acquisition_type = ?
            WHERE id = ? AND user_id = ?
            """,
            (purchase_cb_id, purchase_acct_id, payable, acquisition, phone_id, user_id),
        )


def _post_sale_ledger(conn, user_id, phone_id, data):
    """Sync sale payment and receivable to cash book and buyer account."""
    sale_price = float(data.get("sale_price") or 0)
    receivable = float(data.get("receivable_amount") or 0)
    received_now = max(0.0, sale_price - receivable)
    buyer_account_id = data.get("buyer_account_id")
    if buyer_account_id not in (None, "", 0):
        buyer_account_id = int(buyer_account_id)
    else:
        buyer_account_id = None

    model = data.get("model", "Phone")
    entry_date = _normalize_datetime(data.get("sold_at"), conn, date_only=True)
    method = data.get("sale_payment_method") or "cash"
    bank_id = data.get("sale_bank_id")

    sale_cb_id = None
    sale_acct_id = None

    if received_now > 0:
        cb = _post_payment_transaction(
            conn, user_id, method, bank_id, "in", received_now,
            f"Sale: {model} (#{phone_id})", entry_date,
            source_type="phone_sale", source_id=phone_id,
            account_id=buyer_account_id,
            account_entry_type="debit" if buyer_account_id else None,
        )
        if cb:
            sale_cb_id = cb.get("cash_book_entry_id") or cb.get("id")

    if receivable > 0:
        acct_id = buyer_account_id
        if not acct_id:
            raise ValueError("Select a buyer account when recording sale udhar (receivable)")
        note = f"Sale udhar: {model} (#{phone_id})"
        sale_acct_id = _insert_account_entry(conn, acct_id, "credit", receivable, note)
        _record_ledger_link(
            conn, user_id, "phone_receivable", phone_id, account_entry_id=sale_acct_id,
        )

    conn.execute(
        """
        UPDATE phones SET
            sale_cash_book_entry_id = ?,
            sale_account_entry_id = ?,
            buyer_account_id = ?,
            receivable_amount = ?
        WHERE id = ? AND user_id = ?
        """,
        (sale_cb_id, sale_acct_id, buyer_account_id, receivable, phone_id, user_id),
    )


def _normalize_imei(value) -> str:
    return re.sub(r"\D", "", str(value or "").strip())


def _check_imei_duplicate(conn, user_id, imei, imei2, *, exclude_phone_id=None):
    """Reject duplicate IMEI across active inventory (not returned-to-supplier)."""
    for raw in (imei, imei2):
        normalized = _normalize_imei(raw)
        if not normalized:
            continue
        row = conn.execute(
            """
            SELECT id FROM phones
            WHERE user_id = ?
              AND id != COALESCE(?, -1)
              AND status != 'Returned to Supplier'
              AND (
                replace(replace(replace(imei, '-', ''), ' ', ''), '.', '') = ?
                OR replace(replace(replace(imei2, '-', ''), ' ', ''), '.', '') = ?
              )
            LIMIT 1
            """,
            (user_id, exclude_phone_id, normalized, normalized),
        ).fetchone()
        if row:
            raise ValueError(f"IMEI {raw} is already used on phone #{row['id']}")


def _field_changed(old, new, field):
    numeric = {
        "purchase_price", "payable_amount", "advance_received",
        "sale_price", "receivable_amount",
    }
    int_fields = {"purchase_bank_id", "sale_bank_id", "supplier_account_id", "buyer_account_id"}
    if field in int_fields:
        old_v = int(old) if old not in (None, "", 0) else None
        new_v = int(new) if new not in (None, "", 0) else None
        return old_v != new_v
    if field in numeric:
        return round(float(old or 0), 2) != round(float(new or 0), 2)
    return (old or "") != (new or "")


PURCHASE_LEDGER_FIELDS = frozenset({
    "purchase_price", "payable_amount", "purchase_payment_method", "purchase_bank_id",
    "supplier_account_id", "acquisition_type", "purchase_date",
})
SALE_LEDGER_FIELDS = frozenset({
    "sale_price", "receivable_amount", "sale_payment_method", "sale_bank_id",
    "buyer_account_id", "sold_at",
})


def _reverse_phone_sale_ledger(conn, user_id, phone_id):
    for source in ("phone_sale", "phone_receivable"):
        _reverse_ledger_for_source(conn, user_id, source, phone_id)
    conn.execute(
        """
        UPDATE phones SET
            sale_cash_book_entry_id = NULL,
            sale_account_entry_id = NULL
        WHERE id = ? AND user_id = ?
        """,
        (phone_id, user_id),
    )


def _reverse_phone_purchase_ledger(conn, user_id, phone_id):
    for source in ("phone_purchase", "phone_borrow", "phone_payable"):
        _reverse_ledger_for_source(conn, user_id, source, phone_id)
    conn.execute(
        """
        UPDATE phones SET
            purchase_cash_book_entry_id = NULL,
            purchase_account_entry_id = NULL
        WHERE id = ? AND user_id = ?
        """,
        (phone_id, user_id),
    )


def _validate_phone_payments(conn, user_id, data, status):
    if "purchase_price" in data and float(data.get("purchase_price") or 0) < 0:
        raise ValueError("Purchase price cannot be negative")
    if "payable_amount" in data and float(data.get("payable_amount") or 0) < 0:
        raise ValueError("Payable amount cannot be negative")
    if "sale_price" in data and data.get("sale_price") not in (None, "") and float(data["sale_price"]) < 0:
        raise ValueError("Sale price cannot be negative")
    if "receivable_amount" in data and float(data.get("receivable_amount") or 0) < 0:
        raise ValueError("Receivable amount cannot be negative")
    if status in ("Bought", "In Repair"):
        acquisition = (data.get("acquisition_type") or "purchase").strip().lower()
        if acquisition == "borrow":
            return
        method = data.get("purchase_payment_method") or "cash"
        if method not in ("cash", "bank"):
            raise ValueError("Purchase payment method must be Cash or Bank")
        if method == "bank" and not data.get("purchase_bank_id"):
            raise ValueError("Select a bank account for purchase payment")
        if method == "bank" and not get_bank(conn, user_id, int(data["purchase_bank_id"])):
            raise ValueError("Selected bank account not found")
        payable = float(data.get("payable_amount") or 0)
        purchase_price = float(data.get("purchase_price") or 0)
        if payable > purchase_price:
            raise ValueError("Payable amount cannot exceed purchase price")
    if status == "Sold":
        method = data.get("sale_payment_method") or "cash"
        if method not in ("cash", "bank"):
            raise ValueError("Sale payment method must be Cash or Bank")
        if method == "bank" and not data.get("sale_bank_id"):
            raise ValueError("Select a bank account for sale payment")
        if method == "bank" and not get_bank(conn, user_id, int(data["sale_bank_id"])):
            raise ValueError("Selected bank account not found")
        receivable = float(data.get("receivable_amount") or 0)
        sale_price = float(data.get("sale_price") or 0)
        if receivable > sale_price:
            raise ValueError("Receivable cannot exceed sale price")
        if receivable > 0 and not data.get("buyer_account_id"):
            raise ValueError("Select a buyer account when recording sale udhar (receivable)")


def create_phone(conn, user_id, data):
    """Add a new phone to inventory, and post whatever ledger entries its
    starting status implies:
      - status "Bought"/"In Repair" -> posts a purchase entry (money owed
        to/paid to the supplier).
      - status "Sold" -> posts BOTH a purchase entry (how the shop got the
        phone) and a sale entry (money owed by/received from the buyer) in
        the same call, since a phone entered as already-sold still needs a
        purchase record for accurate profit/stock accounting.
    See _post_purchase_ledger / _post_sale_ledger for what "posts a ledger
    entry" actually creates.
    """
    if not conn.in_transaction:
        # Grab SQLite's write lock before the duplicate-IMEI check runs, so two
        # near-simultaneous saves (two staff, two tabs) can't both pass the
        # check before either commits — the second one now waits here and
        # re-checks against the first's already-committed row.
        conn.execute("BEGIN IMMEDIATE")
    status = data.get("status", "Bought")
    _validate_phone_payments(conn, user_id, data, status)
    _check_imei_duplicate(conn, user_id, data.get("imei"), data.get("imei2"))
    values = _build_phone_insert_values(conn, data)
    purchase_pm = data.get("purchase_payment_method") or "cash"
    purchase_bank = data.get("purchase_bank_id")
    sale_pm = data.get("sale_payment_method") or "cash"
    sale_bank = data.get("sale_bank_id")
    supplier_account_id = data.get("supplier_account_id")
    if supplier_account_id not in (None, "", 0):
        supplier_account_id = int(supplier_account_id)
        if not get_account(conn, user_id, supplier_account_id):
            raise ValueError("Supplier account not found")
    else:
        supplier_account_id = None
    buyer_account_id = data.get("buyer_account_id")
    if buyer_account_id not in (None, "", 0):
        buyer_account_id = int(buyer_account_id)
        if not get_account(conn, user_id, buyer_account_id):
            raise ValueError("Buyer account not found")
    else:
        buyer_account_id = None
    acquisition_type = (data.get("acquisition_type") or "purchase").strip().lower()
    if acquisition_type not in ("purchase", "borrow"):
        acquisition_type = "purchase"
    cursor = conn.execute(
        """
        INSERT INTO phones (
            model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, imei, imei2, box_status, battery_health, variant, purchase_date,
            purchase_payment_method, purchase_bank_id, sale_payment_method, sale_bank_id,
            supplier_account_id, buyer_account_id, acquisition_type, user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            *values,
            purchase_pm,
            int(purchase_bank) if purchase_bank else None,
            sale_pm,
            int(sale_bank) if sale_bank else None,
            supplier_account_id,
            buyer_account_id,
            acquisition_type,
            user_id,
        ),
    )
    phone_id = cursor.lastrowid
    _save_phone_extras(conn, user_id, phone_id, data)
    if status in ("Bought", "In Repair"):
        _post_purchase_ledger(conn, user_id, phone_id, {**data, "supplier_account_id": supplier_account_id})
    if status == "Sold":
        _post_purchase_ledger(conn, user_id, phone_id, {**data, "supplier_account_id": supplier_account_id})
        _post_sale_ledger(conn, user_id, phone_id, {**data, "buyer_account_id": buyer_account_id})
    return get_phone(conn, user_id, phone_id, include_details=True)


def create_phones_bulk(conn, user_id, data):
    quantity = int(data.get("quantity") or 1)
    imeis = data.get("imeis") or []
    imei2s = data.get("imei2s") or []
    unit_price = float(data.get("purchase_price") or 0)
    created = []
    for i in range(quantity):
        phone_data = dict(data)
        phone_data["purchase_price"] = unit_price
        if i < len(imeis) and isinstance(imeis[i], dict):
            unit = imeis[i]
            phone_data["imei"] = unit.get("imei", "")
            phone_data["imei2"] = unit.get("imei2", "")
            for field in ("condition", "box_status", "battery_health", "variant"):
                if (unit.get(field) or "").strip():
                    phone_data[field] = unit[field]
        else:
            phone_data["imei"] = imeis[i] if i < len(imeis) else ""
            phone_data["imei2"] = imei2s[i] if i < len(imei2s) else ""
        phone_data.pop("quantity", None)
        phone_data.pop("imeis", None)
        phone_data.pop("imei2s", None)
        if quantity > 1 and i > 0:
            phone_data["expenses"] = []
            phone_data["investments"] = []
        created.append(create_phone(conn, user_id, phone_data))
    return created


def update_phone(conn, user_id, phone_id, data):
    """Edit a phone's details and, if its status or money fields changed in
    a way that affects the books, reverse the old ledger entries and post
    new ones (see the diffing further down that compares old vs new
    purchase/sale amounts). Guards against two illegal status transitions
    (see the two ValueError checks below) and against two people editing
    the same phone at once (see the locking comment right below).
    """
    if not conn.in_transaction:
        # Grab the write lock before reading the phone's current status, not just
        # for IMEI changes — two near-simultaneous status-changing edits (e.g. two
        # "mark Sold" clicks) both read the pre-edit status and decide what to post
        # in Python before writing, so without an early lock both can pass the
        # decision and each post a full ledger entry (double revenue / double
        # refund). Taking the lock first forces the second call to wait and
        # re-read the already-committed state.
        conn.execute("BEGIN IMMEDIATE")
    existing = conn.execute(
        "SELECT * FROM phones WHERE id = ? AND user_id = ?",
        (phone_id, user_id),
    ).fetchone()
    if not existing:
        return None

    new_status = data.get("status", existing["status"])
    if existing["status"] == "Returned to Supplier" and new_status != "Returned to Supplier":
        raise ValueError(
            "This phone was returned to the supplier — its purchase record was already "
            "settled, so it can't be marked Sold/Bought/In Repair again. Add it as a new "
            "phone if you got it back into stock."
        )
    if new_status == "Returned to Supplier" and existing["status"] != "Returned to Supplier":
        raise ValueError(
            "Use the Returns page to return a phone to its supplier — that properly "
            "reverses the purchase payable/cash entry and logs the refund. Setting this "
            "status directly would leave the supplier payable orphaned."
        )
    merged_input = {**dict(existing), **data}
    _validate_phone_payments(conn, user_id, merged_input, new_status)
    if "imei" in data or "imei2" in data:
        _check_imei_duplicate(
            conn, user_id,
            data.get("imei", existing["imei"]),
            data.get("imei2", existing["imei2"]),
            exclude_phone_id=phone_id,
        )
    if new_status != "Sold":
        data = {k: v for k, v in data.items() if k not in (
            "buyer_name", "buyer_contact", "sale_price", "receivable_amount"
        )}
        data["buyer_name"] = ""
        data["buyer_contact"] = ""
        data["sale_price"] = None
        data["receivable_amount"] = 0

    fields = []
    values = []

    simple_fields = [
        "model", "condition", "type", "purchase_price",
        "supplier_name", "supplier_contact", "status",
        "payable_amount", "advance_received",
        "buyer_name", "buyer_contact", "sale_price", "receivable_amount",
        "imei", "imei2", "box_status", "battery_health", "variant", "purchase_date",
        "purchase_payment_method", "purchase_bank_id", "sale_payment_method", "sale_bank_id",
        "supplier_account_id", "sold_at", "buyer_account_id", "acquisition_type",
    ]
    numeric_fields = {
        "purchase_price", "payable_amount", "advance_received",
        "sale_price", "receivable_amount",
    }
    int_nullable_fields = {"purchase_bank_id", "sale_bank_id", "supplier_account_id", "buyer_account_id"}
    for field in simple_fields:
        if field in data:
            fields.append(f"{field} = ?")
            val = data[field]
            if field in int_nullable_fields:
                val = int(val) if val not in (None, "", 0) else None
            elif field in numeric_fields:
                val = float(val) if val not in (None, "") else 0
            elif field in ("purchase_date", "sold_at") and val:
                val = _normalize_datetime(val, conn, date_only=(field == "purchase_date"))
            values.append(val)

    if new_status == "Sold" and existing["status"] != "Sold":
        if "sold_at" not in data:
            fields.append("sold_at = ?")
            values.append(_local_datetime(conn))
    elif new_status != "Sold":
        fields.append("sold_at = NULL")

    if fields:
        values.extend([phone_id, user_id])
        conn.execute(
            f"UPDATE phones SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )

    if "investments" in data:
        conn.execute("DELETE FROM phone_investments WHERE phone_id = ?", (phone_id,))
        _save_phone_extras(conn, user_id, phone_id, {"investments": data["investments"]})

    if new_status == "Sold" and existing["status"] != "Sold":
        merged = {**dict(existing), **data}
        _post_sale_ledger(conn, user_id, phone_id, merged)
    elif existing["status"] == "Sold" and new_status != "Sold":
        _reverse_phone_sale_ledger(conn, user_id, phone_id)
    elif existing["status"] == "Sold" and new_status == "Sold":
        if any(_field_changed(existing[f], data.get(f, existing[f]), f) for f in SALE_LEDGER_FIELDS if f in data):
            refreshed = conn.execute(
                "SELECT * FROM phones WHERE id = ? AND user_id = ?",
                (phone_id, user_id),
            ).fetchone()
            merged = {**dict(refreshed), **data}
            _reverse_phone_sale_ledger(conn, user_id, phone_id)
            _post_sale_ledger(conn, user_id, phone_id, merged)

    # Purchase-side ledger is independent of the sale-status transition above
    # (a phone keeps its purchase entry whether it's Bought, In Repair, or
    # already Sold) — reconcile it on its own whenever a purchase field
    # changes, instead of only when status stays within INVENTORY_STATUSES.
    # "Returned to Supplier" phones are settled by process_purchase_return,
    # not this generic edit path, so leave those alone.
    if "Returned to Supplier" not in (existing["status"], new_status):
        if any(_field_changed(existing[f], data.get(f, existing[f]), f) for f in PURCHASE_LEDGER_FIELDS if f in data):
            refreshed = conn.execute(
                "SELECT * FROM phones WHERE id = ? AND user_id = ?",
                (phone_id, user_id),
            ).fetchone()
            merged = {**dict(refreshed), **data}
            _reverse_phone_purchase_ledger(conn, user_id, phone_id)
            _post_purchase_ledger(conn, user_id, phone_id, merged)

    return get_phone(conn, user_id, phone_id, include_details=True)


def delete_phone(conn, user_id, phone_id):
    if not get_phone(conn, user_id, phone_id):
        return
    # Bug #18: invoices.phone_id / purchase_invoices.phone_id have no FK
    # constraint at all (unlike return_logs.phone_id, which is
    # ON DELETE SET NULL), so a hard delete used to silently orphan any
    # printed invoice referencing this phone. Block the delete instead of
    # cascading through a real paper trail -- the shop owner should
    # explicitly decide what happens to invoices already handed to a
    # customer/supplier, not have them silently reference a phone that no
    # longer exists.
    invoice_count = conn.execute(
        "SELECT COUNT(*) c FROM invoices WHERE phone_id = ? AND user_id = ?",
        (phone_id, user_id),
    ).fetchone()["c"]
    purchase_invoice_count = conn.execute(
        "SELECT COUNT(*) c FROM purchase_invoices WHERE phone_id = ? AND user_id = ?",
        (phone_id, user_id),
    ).fetchone()["c"]
    if invoice_count or purchase_invoice_count:
        parts = []
        if invoice_count:
            parts.append(f"{invoice_count} sale invoice(s)")
        if purchase_invoice_count:
            parts.append(f"{purchase_invoice_count} purchase invoice(s)")
        raise ValueError(
            f"Can't delete this phone — it has {' and '.join(parts)} on record. "
            "Mark it as Returned to Supplier instead, or delete those invoices "
            "first if they were created by mistake."
        )
    _reverse_phone_ledger(conn, user_id, phone_id)
    conn.execute(
        "DELETE FROM phones WHERE id = ? AND user_id = ?",
        (phone_id, user_id),
    )


def bulk_delete_phones(conn, user_id, phone_ids):
    deleted = 0
    errors = []
    for phone_id in phone_ids:
        phone_id = int(phone_id)
        existing = conn.execute(
            "SELECT id FROM phones WHERE id = ? AND user_id = ?",
            (phone_id, user_id),
        ).fetchone()
        if not existing:
            continue
        try:
            delete_phone(conn, user_id, phone_id)
            deleted += 1
        except ValueError as e:
            # Same pattern as bulk_mark_sold: one phone with linked invoices
            # shouldn't block deleting the rest of the batch -- collect it
            # and keep going.
            errors.append(f"Phone #{phone_id}: {e}")
    return {"deleted": deleted, "errors": errors}


def bulk_mark_sold(conn, user_id, items, default_sale_price=None):
    """Mark multiple phones sold; each item can have its own sale_price."""
    updated = []
    errors = []
    default_price = float(default_sale_price or 0)
    for item in items:
        phone_id = int(item["phone_id"])
        sale_price = float(item.get("sale_price") or default_price or 0)
        if sale_price <= 0:
            errors.append(f"Phone #{phone_id}: sale price required")
            continue
        existing = conn.execute(
            "SELECT * FROM phones WHERE id = ? AND user_id = ?",
            (phone_id, user_id),
        ).fetchone()
        if not existing:
            errors.append(f"Phone #{phone_id}: not found")
            continue
        if existing["status"] == "Sold":
            errors.append(f"Phone #{phone_id}: already sold")
            continue
        data = {
            "status": "Sold",
            "sale_price": sale_price,
            "receivable_amount": float(item.get("receivable_amount") or 0),
            "buyer_name": item.get("buyer_name") or "",
            "buyer_contact": item.get("buyer_contact") or "",
            "sale_payment_method": item.get("sale_payment_method") or "cash",
            "sale_bank_id": item.get("sale_bank_id"),
            "buyer_account_id": item.get("buyer_account_id"),
            "sold_at": item.get("sold_at"),
        }
        receivable = data["receivable_amount"]
        if receivable > sale_price:
            errors.append(f"Phone #{phone_id}: receivable cannot exceed sale price")
            continue
        if receivable > 0 and not data.get("buyer_account_id"):
            errors.append(f"Phone #{phone_id}: buyer account required for udhar")
            continue
        try:
            phone = update_phone(conn, user_id, phone_id, data)
        except ValueError as exc:
            errors.append(f"Phone #{phone_id}: {exc}")
            continue
        if phone:
            updated.append(phone)
    if errors and not updated:
        raise ValueError("; ".join(errors))
    return {"updated": updated, "errors": errors}


def add_phone_expense(conn, user_id, phone_id, data):
    phone = get_phone(conn, user_id, phone_id)
    if not phone:
        return None
    amount = float(data["amount"])
    description = data.get("description", "")
    expense_date = _normalize_datetime(data.get("expense_date"), conn, date_only=True)
    account_id = data.get("account_id")
    if account_id not in (None, "", 0):
        account_id = int(account_id)
        if not get_account(conn, user_id, account_id):
            raise ValueError("Account not found")
    else:
        account_id = None

    cursor = conn.execute(
        """
        INSERT INTO phone_expenses (phone_id, amount, description, expense_date, account_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (phone_id, amount, description, expense_date, account_id),
    )
    expense_id = cursor.lastrowid
    cash_book_entry_id = None
    account_entry_id = None
    if amount > 0:
        cb = _create_cash_book_synced(conn, user_id, {
            "entry_type": "out",
            "amount": amount,
            "note": description or f"Phone expense: {phone['model']} (#{phone_id})",
            "entry_date": expense_date,
            "account_id": account_id,
            "payment_source": data.get("payment_source") or "cash",
            "bank_account_id": data.get("bank_account_id"),
        }, source_type="phone_expense", source_id=expense_id,
           account_entry_type="debit" if account_id else None,
           force=bool(data.get("force")))
        cash_book_entry_id = cb.get("cash_book_entry_id") or cb.get("id")
        account_entry_id = cb.get("account_entry_id")
        conn.execute(
            """
            UPDATE phone_expenses
            SET cash_book_entry_id = ?, account_entry_id = ?
            WHERE id = ?
            """,
            (cash_book_entry_id, account_entry_id, expense_id),
        )
    row = conn.execute(
        "SELECT * FROM phone_expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    return dict(row)


def update_phone_expense(conn, user_id, phone_id, expense_id, data):
    phone = get_phone(conn, user_id, phone_id)
    if not phone:
        return None
    row = conn.execute(
        "SELECT * FROM phone_expenses WHERE id = ? AND phone_id = ?",
        (expense_id, phone_id),
    ).fetchone()
    if not row:
        return None

    amount = float(data.get("amount", row["amount"]))
    description = data.get("description", row["description"])
    # row["created_at"] is stored in UTC (see _init_schema); a bare string
    # slice of it would misclassify expenses recorded near local midnight
    # onto the wrong calendar day, so localize it before falling back to it.
    created_at_local = conn.execute(
        "SELECT date(?, 'localtime')", (row["created_at"],)
    ).fetchone()[0]
    expense_date = _normalize_datetime(
        data.get("expense_date") or row["expense_date"] or created_at_local,
        conn,
        date_only=True,
    )
    account_id = data.get("account_id", row["account_id"])
    if account_id in (None, "", 0):
        account_id = None
    else:
        account_id = int(account_id)
        if not get_account(conn, user_id, account_id):
            raise ValueError("Account not found")

    conn.execute(
        """
        UPDATE phone_expenses
        SET amount = ?, description = ?, expense_date = ?, account_id = ?
        WHERE id = ? AND phone_id = ?
        """,
        (amount, description, expense_date, account_id, expense_id, phone_id),
    )

    _reverse_ledger_for_source(conn, user_id, "phone_expense", expense_id)

    cash_book_entry_id = None
    account_entry_id = None
    if amount > 0:
        cb = _create_cash_book_synced(conn, user_id, {
            "entry_type": "out",
            "amount": amount,
            "note": description or f"Phone expense: {phone['model']} (#{phone_id})",
            "entry_date": expense_date,
            "account_id": account_id,
            "payment_source": data.get("payment_source") or "cash",
            "bank_account_id": data.get("bank_account_id"),
        }, source_type="phone_expense", source_id=expense_id,
           account_entry_type="debit" if account_id else None,
           force=bool(data.get("force")))
        cash_book_entry_id = cb.get("cash_book_entry_id") or cb.get("id")
        account_entry_id = cb.get("account_entry_id")
        conn.execute(
            """
            UPDATE phone_expenses
            SET cash_book_entry_id = ?, account_entry_id = ?
            WHERE id = ?
            """,
            (cash_book_entry_id, account_entry_id, expense_id),
        )

    updated = conn.execute(
        "SELECT * FROM phone_expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    return dict(updated)


def delete_phone_expense(conn, user_id, phone_id, expense_id):
    row = conn.execute(
        "SELECT * FROM phone_expenses WHERE id = ? AND phone_id = ?",
        (expense_id, phone_id),
    ).fetchone()
    if not row:
        return False
    _reverse_ledger_for_source(conn, user_id, "phone_expense", expense_id)
    conn.execute("DELETE FROM phone_expenses WHERE id = ?", (expense_id,))
    return True


def find_phone_by_imei(conn, user_id, imei):
    imei = (imei or "").strip()
    if not imei:
        return None
    row = conn.execute(
        """
        SELECT * FROM phones
        WHERE user_id = ?
          AND (imei = ? COLLATE NOCASE OR imei2 = ? COLLATE NOCASE)
        """,
        (user_id, imei, imei),
    ).fetchone()
    return phone_to_dict(conn, row) if row else None


def list_phones_for_billing(conn, user_id):
    """Phones available for invoicing (in stock or sold)."""
    rows = conn.execute(
        """
        SELECT * FROM phones
        WHERE user_id = ? AND status IN ('Bought', 'Sold', 'In Repair')
        ORDER BY model COLLATE NOCASE, imei COLLATE NOCASE
        """,
        (user_id,),
    ).fetchall()
    return [phone_to_dict(conn, r) for r in rows]


def list_phones_for_purchase_return(conn, user_id):
    rows = conn.execute(
        """
        SELECT * FROM phones
        WHERE user_id = ? AND status IN ('Bought', 'In Repair')
        ORDER BY model COLLATE NOCASE, imei COLLATE NOCASE
        """,
        (user_id,),
    ).fetchall()
    return [phone_to_dict(conn, r) for r in rows]


def list_phones_for_sale_return(conn, user_id):
    rows = conn.execute(
        """
        SELECT * FROM phones
        WHERE user_id = ? AND status = 'Sold'
        ORDER BY sold_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    return [phone_to_dict(conn, r) for r in rows]


def list_return_logs(conn, user_id, return_type=None):
    if return_type:
        rows = conn.execute(
            """
            SELECT * FROM return_logs
            WHERE user_id = ? AND return_type = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id, return_type),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM return_logs
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def process_purchase_return(conn, user_id, data):
    """Send a phone the shop bought back to its supplier: marks it
    "Returned to Supplier" and posts a refund entry (what the shop gets
    back), defaulting the refund to whatever was already paid unless a
    different amount is given.
    """
    if not conn.in_transaction:
        # Same read-then-write race as update_phone: this checks the phone's
        # status before flipping it and posting a refund, so two near-simultaneous
        # returns of the same phone could otherwise both pass the check and both
        # refund. Lock first so the second call waits and re-reads the real state.
        conn.execute("BEGIN IMMEDIATE")
    phone_id = data.get("phone_id")
    imei = (data.get("imei") or "").strip()
    note = (data.get("note") or "").strip()

    phone = None
    if phone_id:
        phone = get_phone(conn, user_id, phone_id)
    elif imei:
        phone = find_phone_by_imei(conn, user_id, imei)

    if not phone:
        raise ValueError("Phone not found — select a phone from bought inventory")
    if phone["status"] not in INVENTORY_STATUSES:
        raise ValueError("Only Bought or In Repair items can be returned to supplier")

    paid_now = max(0.0, float(phone.get("purchase_price") or 0) - float(phone.get("payable_amount") or 0))
    already_refunded = conn.execute(
        "SELECT COALESCE(SUM(refund_amount), 0) AS s FROM return_logs WHERE phone_id = ? AND return_type = 'purchase'",
        (phone["id"],),
    ).fetchone()["s"]
    max_refundable = round(paid_now - already_refunded, 2)
    refund = float(
        data.get("refund_amount")
        if data.get("refund_amount") not in (None, "")
        else max_refundable
    )
    if refund < 0:
        raise ValueError("Refund amount cannot be negative")
    if refund > max_refundable + 0.01:
        raise ValueError(
            f"Refund cannot exceed what was actually paid to the supplier — "
            f"maximum refundable is {max_refundable:,.2f}"
        )
    account_id = data.get("account_id") or phone.get("supplier_account_id")
    if account_id in (None, "", 0):
        account_id = None
    else:
        account_id = int(account_id)
        if not get_account(conn, user_id, account_id):
            raise ValueError("Account not found")

    return_date = _normalize_datetime(data.get("return_date"), conn, date_only=True)

    conn.execute(
        """
        UPDATE phones SET status = 'Returned to Supplier'
        WHERE id = ? AND user_id = ?
        """,
        (phone["id"], user_id),
    )

    # Cancel any outstanding debt owed to the supplier for this phone (udhar/borrow).
    # Do NOT reverse the original "phone_purchase" cash entry or phone_expenses —
    # that cash already left the drawer / was spent, and is real history. The refund
    # posted below is what accounts for money coming back, on top of that history.
    _reverse_ledger_for_source(conn, user_id, "phone_payable", phone["id"])
    _reverse_ledger_for_source(conn, user_id, "phone_borrow", phone["id"])
    conn.execute(
        "UPDATE phones SET purchase_account_entry_id = NULL WHERE id = ? AND user_id = ?",
        (phone["id"], user_id),
    )

    cursor = conn.execute(
        """
        INSERT INTO return_logs (
            user_id, return_type, phone_id, imei, model, party_name, note,
            refund_amount, account_id, created_at
        )
        VALUES (?, 'purchase', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            phone["id"],
            phone.get("imei") or imei,
            phone["model"],
            phone.get("supplier_name") or "",
            note,
            refund,
            account_id,
            _normalize_datetime(data.get("return_date"), conn),
        ),
    )
    log_id = cursor.lastrowid

    if refund > 0:
        _create_cash_book_synced(conn, user_id, {
            "entry_type": "in",
            "amount": refund,
            "note": note or f"Purchase return refund: {phone['model']} (#{phone['id']})",
            "entry_date": return_date,
            "account_id": account_id,
            "payment_source": data.get("payment_source") or "cash",
            "bank_account_id": data.get("bank_account_id"),
        }, source_type="purchase_return", source_id=log_id,
           account_entry_type="credit" if account_id else None)

    log = conn.execute(
        "SELECT * FROM return_logs WHERE id = ?", (log_id,)
    ).fetchone()
    return dict(log)


def process_sale_return(conn, user_id, data):
    """A customer returns a phone they bought: puts the phone back into
    saleable inventory and posts a refund entry (what the shop pays back),
    the mirror image of process_purchase_return() above.
    """
    if not conn.in_transaction:
        # Same read-then-write race as update_phone: this checks phone["status"]
        # == "Sold" before flipping it back and posting a refund, so two
        # near-simultaneous returns of the same sale could otherwise both pass
        # the check and both refund the customer. Lock first so the second call
        # waits and re-reads the real (already-reversed) state.
        conn.execute("BEGIN IMMEDIATE")
    phone_id = data.get("phone_id")
    imei = (data.get("imei") or "").strip()
    note = (data.get("note") or "").strip()
    party_name = (data.get("party_name") or "").strip()

    phone = None
    if phone_id:
        phone = get_phone(conn, user_id, phone_id, include_details=True)
    elif imei:
        phone = find_phone_by_imei(conn, user_id, imei)

    if not phone:
        raise ValueError("Phone not found — select a sold phone from the list")
    if phone["status"] != "Sold":
        raise ValueError("Only sold items can be processed as sale returns")

    received_now = max(0.0, float(phone.get("sale_price") or 0) - float(phone.get("receivable_amount") or 0))
    already_refunded = conn.execute(
        "SELECT COALESCE(SUM(refund_amount), 0) AS s FROM return_logs WHERE phone_id = ? AND return_type = 'sale'",
        (phone["id"],),
    ).fetchone()["s"]
    max_refundable = round(received_now - already_refunded, 2)
    refund = float(
        data.get("refund_amount")
        if data.get("refund_amount") not in (None, "")
        else max_refundable
    )
    if refund < 0:
        raise ValueError("Refund amount cannot be negative")
    if refund > max_refundable + 0.01:
        raise ValueError(
            f"Refund cannot exceed what the customer actually paid — "
            f"maximum refundable is {max_refundable:,.2f}"
        )
    account_id = data.get("account_id")
    if account_id in (None, "", 0):
        account_id = None
    else:
        account_id = int(account_id)
        if not get_account(conn, user_id, account_id):
            raise ValueError("Account not found")

    return_date = _normalize_datetime(data.get("return_date"), conn, date_only=True)

    conn.execute(
        """
        UPDATE phones SET
            status = 'Bought',
            buyer_name = '',
            buyer_contact = '',
            sale_price = NULL,
            receivable_amount = 0,
            sold_at = NULL,
            sale_cash_book_entry_id = NULL,
            sale_account_entry_id = NULL,
            buyer_account_id = NULL
        WHERE id = ? AND user_id = ?
        """,
        (phone["id"], user_id),
    )

    # Cancel the buyer's outstanding receivable (they no longer owe anything for a
    # returned phone). Do NOT reverse "phone_sale" — the cash actually received at
    # sale time is real history; the refund posted below accounts for giving it back.
    _reverse_ledger_for_source(conn, user_id, "phone_receivable", phone["id"])

    cursor = conn.execute(
        """
        INSERT INTO return_logs (
            user_id, return_type, phone_id, imei, model, party_name, note,
            refund_amount, account_id, created_at
        )
        VALUES (?, 'sale', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            phone["id"],
            phone.get("imei") or imei,
            phone["model"],
            party_name or phone.get("buyer_name") or "",
            note,
            refund,
            account_id,
            _normalize_datetime(data.get("return_date"), conn),
        ),
    )
    log_id = cursor.lastrowid

    if refund > 0:
        _create_cash_book_synced(conn, user_id, {
            "entry_type": "out",
            "amount": refund,
            "note": note or f"Sale return refund: {phone['model']} (#{phone['id']})",
            "entry_date": return_date,
            "account_id": account_id,
            "payment_source": data.get("payment_source") or "cash",
            "bank_account_id": data.get("bank_account_id"),
        }, source_type="sale_return", source_id=log_id,
           account_entry_type="debit" if account_id else None,
           force=bool(data.get("force")))

    log = conn.execute(
        "SELECT * FROM return_logs WHERE id = ?", (log_id,)
    ).fetchone()
    return dict(log)


# --- Fixed Expenses ---

def list_fixed_expenses(conn, user_id):
    rows = conn.execute(
        """
        SELECT * FROM fixed_expenses
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def expense_summary(conn, user_id, start_date=None, end_date=None):
    """Combined view of per-phone expenses and fixed (overhead) expenses."""
    phone_rows = conn.execute(
        """
        SELECT pe.id, pe.amount, pe.description,
               COALESCE(NULLIF(pe.expense_date, ''), date(pe.created_at, 'localtime')) AS expense_date,
               p.model AS phone_model, p.id AS phone_id
        FROM phone_expenses pe
        JOIN phones p ON p.id = pe.phone_id
        WHERE p.user_id = ?
        ORDER BY expense_date DESC
        """,
        (user_id,),
    ).fetchall()
    fixed_rows = conn.execute(
        """
        SELECT id, amount, purpose AS description, date(created_at, 'localtime') AS expense_date
        FROM fixed_expenses
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()

    def _in_range(date_str):
        if not (start_date and end_date):
            return True
        return start_date <= (date_str or "")[:10] <= end_date

    phone_expenses = [
        {**dict(r), "category": "Phone Expense"} for r in phone_rows if _in_range(r["expense_date"])
    ]
    fixed_expenses = [
        {**dict(r), "category": "Fixed Expense"} for r in fixed_rows if _in_range(r["expense_date"])
    ]
    combined = sorted(phone_expenses + fixed_expenses, key=lambda x: x["expense_date"] or "", reverse=True)
    total_phone = round(sum(r["amount"] for r in phone_expenses), 2)
    total_fixed = round(sum(r["amount"] for r in fixed_expenses), 2)
    return {
        "entries": combined,
        "total_phone_expenses": total_phone,
        "total_fixed_expenses": total_fixed,
        "total_expenses": round(total_phone + total_fixed, 2),
    }


def create_fixed_expense(conn, user_id, data):
    amount = float(data["amount"])
    purpose = data["purpose"]
    cursor = conn.execute(
        "INSERT INTO fixed_expenses (purpose, amount, user_id) VALUES (?, ?, ?)",
        (purpose, amount, user_id),
    )
    expense_id = cursor.lastrowid
    cash_book_entry_id = None
    if amount > 0:
        cb = _create_cash_book_synced(conn, user_id, {
            "entry_type": "out",
            "amount": amount,
            "note": f"Fixed expense: {purpose}",
            "entry_date": conn.execute("SELECT date('now','localtime')").fetchone()[0],
            "payment_source": data.get("payment_source") or "cash",
            "bank_account_id": data.get("bank_account_id"),
        }, source_type="fixed_expense", source_id=expense_id, force=bool(data.get("force")))
        cash_book_entry_id = cb.get("cash_book_entry_id") or cb.get("id")
        conn.execute(
            "UPDATE fixed_expenses SET cash_book_entry_id = ? WHERE id = ?",
            (cash_book_entry_id, expense_id),
        )
    row = conn.execute(
        "SELECT * FROM fixed_expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    return dict(row)


def delete_fixed_expense(conn, user_id, expense_id):
    row = conn.execute(
        "SELECT * FROM fixed_expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    ).fetchone()
    if row:
        _reverse_ledger_for_source(conn, user_id, "fixed_expense", expense_id)
    conn.execute(
        "DELETE FROM fixed_expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    )


# --- Bank Accounts ---

def _bank_balance(conn, bank_id):
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN transaction_type = 'credit' THEN amount ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN transaction_type = 'debit' THEN amount ELSE 0 END), 0) AS balance
        FROM bank_transactions WHERE bank_account_id = ?
        """,
        (bank_id,),
    ).fetchone()
    return round(row["balance"] or 0, 2)


def bank_to_dict(conn, row):
    d = dict(row)
    d["balance"] = _bank_balance(conn, d["id"])
    return d


def list_banks(conn, user_id):
    rows = conn.execute(
        "SELECT * FROM bank_accounts WHERE user_id = ? ORDER BY name COLLATE NOCASE",
        (user_id,),
    ).fetchall()
    return [bank_to_dict(conn, r) for r in rows]


def get_bank(conn, user_id, bank_id):
    row = conn.execute(
        "SELECT * FROM bank_accounts WHERE id = ? AND user_id = ?",
        (bank_id, user_id),
    ).fetchone()
    return bank_to_dict(conn, row) if row else None


def create_bank(conn, user_id, data):
    initial = None
    if "initial_balance" in data and data["initial_balance"] is not None and str(data["initial_balance"]).strip() != "":
        initial = float(data["initial_balance"])
        if initial < 0:
            raise ValueError("Opening balance cannot be negative")

    cursor = conn.execute(
        "INSERT INTO bank_accounts (name, user_id) VALUES (?, ?)",
        (data["name"], user_id),
    )
    bank_id = cursor.lastrowid
    if initial is not None:
        if initial != 0:
            conn.execute(
                """
                INSERT INTO bank_transactions (bank_account_id, transaction_type, amount, note)
                VALUES (?, 'credit', ?, 'Opening balance')
                """,
                (bank_id, initial),
            )
    return get_bank(conn, user_id, bank_id)


def update_bank(conn, user_id, bank_id, data):
    if not get_bank(conn, user_id, bank_id):
        return None
    if "name" in data:
        conn.execute(
            "UPDATE bank_accounts SET name = ? WHERE id = ? AND user_id = ?",
            (data["name"], bank_id, user_id),
        )
    return get_bank(conn, user_id, bank_id)


def _bank_still_referenced(conn, bank_id):
    checks = [
        ("phones", "purchase_bank_id", "one or more phones list it as the purchase payment bank"),
        ("phones", "sale_bank_id", "one or more phones list it as the sale payment bank"),
        ("account_entries", "bank_account_id", "it's linked to an account entry"),
    ]
    for table, column, reason in checks:
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (bank_id,)
        ).fetchone()
        if row:
            return reason
    return None


def delete_bank(conn, user_id, bank_id):
    if not get_bank(conn, user_id, bank_id):
        return
    still_used = _bank_still_referenced(conn, bank_id)
    if still_used:
        raise ValueError(f"Can't delete this bank account — {still_used}. Remove that first.")
    linked_cash = conn.execute(
        """
        SELECT id FROM cash_book_entries
        WHERE user_id = ? AND bank_account_id = ?
        """,
        (user_id, bank_id),
    ).fetchall()
    for row in linked_cash:
        _delete_cash_book_entry_cascade(conn, user_id, row["id"])
    conn.execute(
        "DELETE FROM bank_accounts WHERE id = ? AND user_id = ?",
        (bank_id, user_id),
    )


def list_bank_transactions(conn, bank_id):
    rows = conn.execute(
        """
        SELECT * FROM bank_transactions
        WHERE bank_account_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (bank_id,),
    ).fetchall()
    balance = 0.0
    entries = []
    for row in rows:
        d = dict(row)
        if d["transaction_type"] == "credit":
            balance += d["amount"]
        else:
            balance -= d["amount"]
        d["balance"] = round(balance, 2)
        entries.append(d)
    return list(reversed(entries))


def _mirror_bank_tx_to_cash_book(
    conn, user_id, bank_id, bank_tx_id, tx_type, amount, note, *,
    entry_date=None, source_type=None, source_id=None, force=False,
):
    """Record a manual bank Deposit/Withdrawal as the real cash movement it is:
    a Deposit moves cash out of the drawer into the bank (cash 'out'), a
    Withdrawal moves cash from the bank into the drawer (cash 'in'). Tagged
    payment_source='cash' (not 'bank') so it actually lands in Cash in Hand —
    previously this was recorded as another bank-side row, so Cash in Hand
    never moved and a Withdrawal looked like it did nothing."""
    entry_type = "out" if tx_type == "credit" else "in"
    if entry_type == "out":
        # A Deposit pulls this amount out of the physical drawer -- soft-guard
        # it the same way every other cash outflow is guarded.
        _check_cash_not_negative(conn, user_id, amount, force)
    bank = get_bank(conn, user_id, bank_id)
    bank_name = bank["name"] if bank else "bank"
    label = f"Deposit to {bank_name}" if tx_type == "credit" else f"Withdrawal from {bank_name}"
    full_note = f"{label}: {note}" if note else label
    cursor = conn.execute(
        """
        INSERT INTO cash_book_entries (
            entry_type, amount, note, entry_date, user_id,
            payment_source, bank_account_id, linked_bank_transaction_id
        ) VALUES (?, ?, ?, ?, ?, 'cash', NULL, ?)
        """,
        (
            entry_type,
            float(amount),
            full_note,
            entry_date or _local_date(conn),
            user_id,
            bank_tx_id,
        ),
    )
    entry_id = cursor.lastrowid
    if source_type and source_id is not None:
        _record_ledger_link(
            conn, user_id, source_type, source_id,
            cash_book_entry_id=entry_id,
            bank_transaction_id=bank_tx_id,
        )
    return entry_id


def create_bank_transaction(conn, bank_id, data, user_id=None, *, mirror_cash_book=False, force=False):
    tx_type = data["transaction_type"]
    if tx_type not in BANK_TX_TYPES:
        raise ValueError("Invalid transaction type")
    amount = float(data["amount"])
    note = data.get("note", "")

    if tx_type == "debit":
        # A debit decreases this bank's own balance (a withdrawal, or any
        # other bank-side outflow) -- soft-guard it the same way cash
        # outflows are guarded in _create_cash_book_synced.
        _check_bank_not_negative(conn, user_id, bank_id, amount, force)

    cursor = conn.execute(
        """
        INSERT INTO bank_transactions (bank_account_id, transaction_type, amount, note)
        VALUES (?, ?, ?, ?)
        """,
        (bank_id, tx_type, amount, note),
    )
    tx_id = cursor.lastrowid
    if mirror_cash_book and user_id is not None:
        _mirror_bank_tx_to_cash_book(
            conn, user_id, bank_id, tx_id, tx_type, amount, note,
            entry_date=data.get("entry_date"),
            source_type="bank_transaction",
            source_id=tx_id,
            force=force,
        )
    row = conn.execute(
        "SELECT * FROM bank_transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    return dict(row)


def update_bank_transaction(conn, tx_id, data, user_id=None):
    existing = conn.execute(
        "SELECT * FROM bank_transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if not existing:
        return None
    fields, values = [], []
    for field in ("transaction_type", "amount", "note"):
        if field in data:
            fields.append(f"{field} = ?")
            val = data[field]
            if field == "amount":
                val = float(val)
            values.append(val)
    if fields:
        values.append(tx_id)
        conn.execute(
            f"UPDATE bank_transactions SET {', '.join(fields)} WHERE id = ?",
            values,
        )
    row = conn.execute(
        "SELECT * FROM bank_transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    if user_id and row:
        cb = conn.execute(
            """
            SELECT id FROM cash_book_entries
            WHERE linked_bank_transaction_id = ? AND user_id = ?
            """,
            (tx_id, user_id),
        ).fetchone()
        if cb and ("amount" in data or "transaction_type" in data or "note" in data):
            cb_update = {}
            if "amount" in data:
                cb_update["amount"] = float(data["amount"])
            if "note" in data:
                cb_update["note"] = data["note"]
            if "transaction_type" in data:
                # Cash moves opposite to the bank side — see _mirror_bank_tx_to_cash_book.
                cb_update["entry_type"] = "out" if data["transaction_type"] == "credit" else "in"
            update_cash_book_entry(conn, user_id, cb["id"], cb_update, _sync_linked=False)
    return dict(row) if row else None


def delete_bank_transaction(conn, tx_id, user_id=None):
    if user_id is not None:
        cb = conn.execute(
            """
            SELECT id FROM cash_book_entries
            WHERE linked_bank_transaction_id = ? AND user_id = ?
            """,
            (tx_id, user_id),
        ).fetchone()
        if cb:
            _delete_cash_book_entry_cascade(conn, user_id, cb["id"])
            return
    _delete_bank_tx_raw(conn, tx_id)


def total_bank_balance(conn, user_id):
    banks = list_banks(conn, user_id)
    return round(sum(b["balance"] for b in banks), 2)


# --- Cash Book ---

def _cash_base_opening(conn, user_id) -> float:
    """Starting cash in hand from settings (used before the first cash-book row)."""
    settings = get_user_settings(conn, user_id)
    return float(settings.get("cash_in_hand") or 0)


def _cash_book_running(conn, user_id):
    rows = conn.execute(
        """
        SELECT cbe.*, a.name AS account_name, b.name AS bank_name
        FROM cash_book_entries cbe
        LEFT JOIN accounts a ON a.id = cbe.account_id
        LEFT JOIN bank_accounts b ON b.id = cbe.bank_account_id
        WHERE cbe.user_id = ?
        ORDER BY cbe.entry_date ASC, cbe.created_at ASC, cbe.id ASC
        """,
        (user_id,),
    ).fetchall()
    balance = _cash_base_opening(conn, user_id)
    entries = []
    for row in rows:
        d = dict(row)
        source = d.get("payment_source") or "cash"
        if source == "cash":
            if d["entry_type"] == "in":
                balance += d["amount"]
            else:
                balance -= d["amount"]
        d["balance"] = round(balance, 2)
        d["payment_label"] = (
            f"Bank: {d['bank_name']}" if source == "bank" and d.get("bank_name")
            else ("Bank" if source == "bank" else "Cash")
        )
        if source == "bank":
            d["entry_type_label"] = "Bank In" if d["entry_type"] == "in" else "Bank Out"
        else:
            d["entry_type_label"] = "Cash In" if d["entry_type"] == "in" else "Cash Out"
        entries.append(d)
    return list(reversed(entries))


def list_cash_book(conn, user_id):
    return _cash_book_running(conn, user_id)


def create_cash_book_entry(conn, user_id, data):
    result = _create_cash_book_synced(conn, user_id, data, force=bool(data.get("force")))
    account_id = data.get("account_id")
    if account_id:
        result["account_name"] = get_account(conn, user_id, int(account_id))["name"]
    bank_account_id = data.get("bank_account_id")
    if bank_account_id:
        result["bank_name"] = get_bank(conn, user_id, int(bank_account_id))["name"]
    payment_source = data.get("payment_source") or "cash"
    result["payment_label"] = (
        f"Bank: {result['bank_name']}" if payment_source == "bank"
        else "Cash"
    )
    return result


def update_cash_book_entry(conn, user_id, entry_id, data, *, _sync_linked=True):
    existing = conn.execute(
        "SELECT * FROM cash_book_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    ).fetchone()
    if not existing:
        return None

    fields, values = [], []
    for field in ("entry_type", "amount", "note", "entry_date"):
        if field in data:
            fields.append(f"{field} = ?")
            val = data[field]
            if field == "amount":
                val = float(val)
            values.append(val)
    if fields:
        values.extend([entry_id, user_id])
        conn.execute(
            f"UPDATE cash_book_entries SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )

    if _sync_linked:
        row = conn.execute(
            "SELECT * FROM cash_book_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row:
            entry_type = row["entry_type"]
            amount = float(row["amount"])
            note = row["note"]
            if row["linked_bank_transaction_id"]:
                tx_type = "credit" if entry_type == "in" else "debit"
                conn.execute(
                    """
                    UPDATE bank_transactions
                    SET transaction_type = ?, amount = ?, note = ?
                    WHERE id = ?
                    """,
                    (tx_type, amount, note, row["linked_bank_transaction_id"]),
                )
            if row["linked_account_entry_id"]:
                acct_type = "credit" if entry_type == "out" else "debit"
                conn.execute(
                    """
                    UPDATE account_entries
                    SET entry_type = ?, amount = ?, note = ?
                    WHERE id = ?
                    """,
                    (acct_type, amount, note, row["linked_account_entry_id"]),
                )

    row = conn.execute(
        "SELECT * FROM cash_book_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return dict(row)


def delete_cash_book_entry(conn, user_id, entry_id):
    _delete_cash_book_entry_cascade(conn, user_id, entry_id)


def cash_book_daily_summary(conn, user_id, start_date=None, end_date=None):
    settings_opening = _cash_base_opening(conn, user_id)
    rows = conn.execute(
        """
        SELECT entry_date,
            SUM(CASE WHEN entry_type = 'in' AND COALESCE(payment_source, 'cash') = 'cash'
                THEN amount ELSE 0 END) AS cash_in,
            SUM(CASE WHEN entry_type = 'out' AND COALESCE(payment_source, 'cash') = 'cash'
                THEN amount ELSE 0 END) AS cash_out,
            SUM(CASE WHEN entry_type = 'in' AND payment_source = 'bank'
                THEN amount ELSE 0 END) AS bank_in,
            SUM(CASE WHEN entry_type = 'out' AND payment_source = 'bank'
                THEN amount ELSE 0 END) AS bank_out
        FROM cash_book_entries
        WHERE user_id = ?
        GROUP BY entry_date
        ORDER BY entry_date ASC
        """,
        (user_id,),
    ).fetchall()

    summaries = []
    prev_closing = settings_opening
    for r in rows:
        d = dict(r)
        opening = round(prev_closing, 2)
        cash_in = round(d["cash_in"] or 0, 2)
        cash_out = round(d["cash_out"] or 0, 2)
        closing = round(opening + cash_in - cash_out, 2)
        d["opening_balance"] = opening
        d["closing_balance"] = closing
        d["cash_in"] = cash_in
        d["cash_out"] = cash_out
        d["bank_in"] = round(d.get("bank_in") or 0, 2)
        d["bank_out"] = round(d.get("bank_out") or 0, 2)
        summaries.append(d)
        prev_closing = closing

    if start_date and end_date:
        summaries = [
            d for d in summaries
            if start_date <= (d["entry_date"] or "")[:10] <= end_date
        ]
    return list(reversed(summaries))


def cash_in_hand_balance(conn, user_id):
    entries = _cash_book_running(conn, user_id)
    if entries:
        return float(entries[0]["balance"] or 0)
    return round(_cash_base_opening(conn, user_id), 2)


# --- Dashboard ---

def compute_dashboard(conn, user_id):
    """Build the headline numbers shown on the Overview page (stock worth,
    profit, cash in hand, total owed to/by the shop, etc). Everything here
    is computed fresh from the phones/accounts/cash-book tables each call -
    there is no separate "totals" table to keep in sync, so these numbers
    can never drift out of agreement with the underlying ledger.
    """
    settings = get_user_settings(conn, user_id)
    partners = list_partners(conn, user_id)
    total_investment = sum(p["capital"] for p in partners)

    sold = conn.execute(
        """
        SELECT * FROM phones
        WHERE status = 'Sold' AND user_id = ?
        """,
        (user_id,),
    ).fetchall()
    inventory = conn.execute(
        """
        SELECT id, model, purchase_price, receivable_amount, status, type, condition, imei
        FROM phones WHERE status IN ('Bought', 'In Repair') AND user_id = ?
        """,
        (user_id,),
    ).fetchall()
    payables = conn.execute(
        "SELECT payable_amount, supplier_account_id FROM phones WHERE payable_amount > 0 AND user_id = ?",
        (user_id,),
    ).fetchall()

    total_net_profit = sum(_sold_profit(conn, r) for r in sold)
    acct_summary = accounts_summary(conn, user_id)
    # Phone receivables synced to buyer accounts are already in account balances.
    phone_only_receivables = sum(
        (r["receivable_amount"] or 0) for r in sold
        if (r["receivable_amount"] or 0) > 0 and not r["buyer_account_id"]
    )
    total_udhar = round(acct_summary["total_receivable"] + phone_only_receivables, 2)
    phone_receivables = round(phone_only_receivables, 2)
    accounts_payable = acct_summary["total_payable"]
    # Phone payables synced to a supplier account are already in account balances
    # (posted as a debit entry by _post_purchase_ledger) — only count the ones
    # with no linked account here, mirroring phone_only_receivables above.
    phone_payables = sum(
        r["payable_amount"] or 0 for r in payables if not r["supplier_account_id"]
    )
    total_payables_combined = round(accounts_payable + phone_payables, 2)
    active_stock_worth = sum(r["purchase_price"] or 0 for r in inventory)

    total_in_bank = total_bank_balance(conn, user_id)
    total_in_cash = cash_in_hand_balance(conn, user_id)

    profit_reinvested = float(settings.get("profit_reinvested_total") or 0)
    available_profit = max(0.0, round(total_net_profit - profit_reinvested, 2))

    formula_expected = (
        total_investment + total_net_profit - total_udhar - active_stock_worth
        + total_payables_combined
    )
    expected_bank_balance = round(formula_expected - total_in_cash, 2)

    active_inventory = [dict(r) for r in inventory]
    active_receivables = [
        {
            "phone_id": r["id"],
            "model": r["model"],
            "receivable_amount": r["receivable_amount"] or 0,
        }
        for r in conn.execute(
            """
            SELECT id, model, receivable_amount FROM phones
            WHERE receivable_amount > 0 AND user_id = ?
            """,
            (user_id,),
        ).fetchall()
    ]

    return {
        "partners": partners,
        "partner1_name": partners[0]["name"] if len(partners) > 0 else settings.get("partner1_name", ""),
        "partner1_capital": partners[0]["capital"] if len(partners) > 0 else float(settings.get("partner1_capital", 0)),
        "partner2_name": partners[1]["name"] if len(partners) > 1 else settings.get("partner2_name", ""),
        "partner2_capital": partners[1]["capital"] if len(partners) > 1 else float(settings.get("partner2_capital", 0)),
        "total_investment": round(total_investment, 2),
        "total_net_profit": round(total_net_profit, 2),
        "total_receivables": round(phone_receivables, 2),
        "total_udhar": total_udhar,
        "accounts_payable": accounts_payable,
        "total_payables": total_payables_combined,
        "phone_payables": round(phone_payables, 2),
        "active_stock_worth": round(active_stock_worth, 2),
        "expected_cash_balance": expected_bank_balance,
        "formula_expected_balance": round(formula_expected, 2),
        "profit_reinvested": round(profit_reinvested, 2),
        "available_profit": available_profit,
        "total_in_bank": total_in_bank,
        "total_in_cash": round(total_in_cash, 2),
        "cash_in_hand": round(total_in_cash, 2),
        "active_inventory": active_inventory,
        "active_receivables": active_receivables,
        "theme": settings.get("theme", "default-dark"),
    }


def compute_monthly_metrics(conn, user_id):
    rows = conn.execute(
        """
        SELECT * FROM phones
        WHERE status = 'Sold'
          AND sold_at IS NOT NULL
          AND user_id = ?
          AND strftime('%Y-%m', sold_at) = strftime('%Y-%m', 'now', 'localtime')
        """,
        (user_id,),
    ).fetchall()

    units_sold = len(rows)
    total_profit = sum(_sold_profit(conn, r) for r in rows)
    total_cogs = sum(r["purchase_price"] or 0 for r in rows)
    margin = (total_profit / total_cogs * 100) if total_cogs > 0 else 0

    model_counts = {}
    for r in rows:
        model_counts[r["model"]] = model_counts.get(r["model"], 0) + 1
    top_model = max(model_counts, key=model_counts.get) if model_counts else "—"

    return {
        "units_sold": units_sold,
        "total_profit": round(total_profit, 2),
        "profit_margin": round(margin, 1),
        "top_model": top_model,
        "month_label": conn.execute(
            "SELECT strftime('%B %Y', 'now') AS label"
        ).fetchone()["label"],
    }


# --- Accounts (Digikhata-style ledger) ---

def _account_balance(conn, account_id):
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN entry_type = 'credit' THEN amount ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN entry_type = 'debit' THEN amount ELSE 0 END), 0) AS balance
        FROM account_entries WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return round(row["balance"] or 0, 2)


def is_expense_category_account(conn, account_id):
    row = conn.execute(
        "SELECT name, contact FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if not row:
        return False
    if (row["contact"] or "").strip().lower() == "expense category":
        return True
    return row["name"] in EXPENSE_CATEGORY_NAMES


def account_to_dict(conn, row):
    d = dict(row)
    d["balance"] = _account_balance(conn, d["id"])
    d["is_expense_category"] = is_expense_category_account(conn, d["id"])
    return d


def list_accounts(conn, user_id):
    rows = conn.execute(
        "SELECT * FROM accounts WHERE user_id = ? ORDER BY name COLLATE NOCASE",
        (user_id,),
    ).fetchall()
    return [account_to_dict(conn, r) for r in rows]


def get_account(conn, user_id, account_id):
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, user_id),
    ).fetchone()
    return account_to_dict(conn, row) if row else None


def create_account(conn, user_id, data):
    """Create a new customer/supplier (khata) account. If `opening_balance`
    is given (and > 0), post it as a starting account_entries row dated
    now, so a person who already owed money (or was owed money) before the
    shop started using this CRM has that reflected immediately instead of
    starting every account at zero."""
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Account name is required")
    existing = conn.execute(
        "SELECT id FROM accounts WHERE user_id = ? AND LOWER(TRIM(name)) = LOWER(?)",
        (user_id, name),
    ).fetchone()
    if existing:
        raise ValueError(f'An account named "{name}" already exists — use that one instead of creating a duplicate.')
    cursor = conn.execute(
        "INSERT INTO accounts (name, contact, user_id) VALUES (?, ?, ?)",
        (name, data.get("contact", ""), user_id),
    )
    account_id = cursor.lastrowid

    opening_balance = data.get("opening_balance")
    if opening_balance:
        try:
            amount = round(float(opening_balance), 2)
        except (TypeError, ValueError):
            amount = 0
        if amount > 0:
            entry_type = data.get("opening_balance_type") or "credit"
            if entry_type not in ("credit", "debit"):
                entry_type = "credit"
            _insert_account_entry(conn, account_id, entry_type, amount, "Opening balance")

    return get_account(conn, user_id, account_id)


def update_account(conn, user_id, account_id, data):
    existing = conn.execute(
        "SELECT id FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, user_id),
    ).fetchone()
    if not existing:
        return None
    fields, values = [], []
    for field in ("name", "contact"):
        if field in data:
            fields.append(f"{field} = ?")
            values.append(data[field])
    if fields:
        values.extend([account_id, user_id])
        conn.execute(
            f"UPDATE accounts SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
    return get_account(conn, user_id, account_id)


def _account_still_referenced(conn, account_id):
    """Return a plain-language reason this account can't be deleted yet, or None."""
    checks = [
        ("phones", "supplier_account_id", "one or more phones list it as the supplier"),
        ("phones", "buyer_account_id", "one or more phones list it as the buyer"),
        ("phone_expenses", "account_id", "it's linked to a phone expense"),
        ("return_logs", "account_id", "it's linked to a return record"),
        ("journal_vouchers", "debit_account_id", "it's used in a journal voucher"),
        ("journal_vouchers", "credit_account_id", "it's used in a journal voucher"),
    ]
    for table, column, reason in checks:
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (account_id,)
        ).fetchone()
        if row:
            return reason
    return None


def delete_account(conn, user_id, account_id):
    if not get_account(conn, user_id, account_id):
        return
    still_used = _account_still_referenced(conn, account_id)
    if still_used:
        raise ValueError(f"Can't delete this account — {still_used}. Remove that first.")
    for row in conn.execute(
        "SELECT id FROM account_entries WHERE account_id = ?",
        (account_id,),
    ).fetchall():
        _delete_account_entry_cascade(conn, user_id, row["id"])
    for row in conn.execute(
        """
        SELECT id FROM cash_book_entries
        WHERE user_id = ? AND account_id = ?
        """,
        (user_id, account_id),
    ).fetchall():
        _delete_cash_book_entry_cascade(conn, user_id, row["id"])
    conn.execute(
        "DELETE FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, user_id),
    )


def list_entries(conn, account_id):
    rows = conn.execute(
        """
        SELECT * FROM account_entries
        WHERE account_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (account_id,),
    ).fetchall()
    balance = 0.0
    entries = []
    for row in rows:
        d = dict(row)
        if d["entry_type"] == "credit":
            balance += d["amount"]
        else:
            balance -= d["amount"]
        d["balance"] = round(balance, 2)
        entries.append(d)
    return list(reversed(entries))


def build_statement(conn, user_id, account_id):
    account = get_account(conn, user_id, account_id)
    if not account:
        return None
    rows = conn.execute(
        """
        SELECT * FROM account_entries
        WHERE account_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (account_id,),
    ).fetchall()
    balance = 0.0
    lines = []
    for row in rows:
        d = dict(row)
        if d["entry_type"] == "credit":
            balance += d["amount"]
        else:
            balance -= d["amount"]
        lines.append({**d, "balance": round(balance, 2)})
    lines.reverse()
    return {
        "account": account,
        "entries": lines,
        "closing_balance": account["balance"],
    }


def create_entry(conn, account_id, data, user_id=None):
    entry_type = data["entry_type"]
    if entry_type not in ENTRY_TYPES:
        raise ValueError("Invalid entry type")

    amount = float(data["amount"])
    note = data.get("note", "")
    payment_source = (data.get("payment_source") or "").strip().lower()
    bank_account_id = data.get("bank_account_id")

    is_expense = user_id and is_expense_category_account(conn, account_id)
    # Cash/bank sync is required for debit entries and expense-category credits
    # (real money is guaranteed to move). It's optional but still honored for a
    # plain credit entry (e.g. paying down what you owe a supplier) whenever the
    # user explicitly picks Cash or Bank — that selection means real cash moved.
    needs_payment = entry_type == "debit" or (entry_type == "credit" and is_expense)

    if payment_source and payment_source not in ("cash", "bank"):
        raise ValueError("Payment source must be cash or bank")
    if user_id and needs_payment and not payment_source:
        raise ValueError("Select payment method — Cash or Bank")
    if payment_source == "bank":
        if not bank_account_id:
            raise ValueError("Select a bank account")
        bank_account_id = int(bank_account_id)
        if user_id and not get_bank(conn, user_id, bank_account_id):
            raise ValueError("Bank account not found")

    if user_id and payment_source in ("cash", "bank"):
        cash_direction = "in" if entry_type == "debit" else "out"
        return _create_account_entry_synced(
            conn, user_id, account_id, entry_type, amount, note,
            payment_source=payment_source,
            bank_account_id=bank_account_id,
            mirror_cash_book=True,
            cash_book_entry_type=cash_direction,
            force=bool(data.get("force")),
        )

    account_entry_id = _insert_account_entry(
        conn, account_id, entry_type, amount, note,
        linked_cash_book_entry_id=None,
    )
    row = conn.execute(
        "SELECT * FROM account_entries WHERE id = ?", (account_entry_id,)
    ).fetchone()
    return dict(row)


def _journal_voucher_for_entry(conn, entry_id):
    """Return the journal voucher id if this account entry is one leg of a voucher."""
    row = conn.execute(
        "SELECT id FROM journal_vouchers WHERE debit_entry_id = ? OR credit_entry_id = ?",
        (entry_id, entry_id),
    ).fetchone()
    return row["id"] if row else None


def update_entry(conn, entry_id, data, user_id=None):
    existing = conn.execute(
        "SELECT * FROM account_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not existing:
        return None
    voucher_id = _journal_voucher_for_entry(conn, entry_id)
    if voucher_id is not None:
        raise ValueError(
            f"This entry belongs to Journal Voucher #{voucher_id} — edit or delete it "
            "from the Journal page so both sides stay in sync."
        )

    entry_type = data.get("entry_type", existing["entry_type"])
    amount = float(data["amount"]) if "amount" in data else float(existing["amount"])
    note = data.get("note", existing["note"])

    fields, values = [], []
    for field, val in (("entry_type", entry_type), ("amount", amount), ("note", note)):
        if field in data:
            fields.append(f"{field} = ?")
            values.append(val)
    if fields:
        values.append(entry_id)
        conn.execute(
            f"UPDATE account_entries SET {', '.join(fields)} WHERE id = ?",
            values,
        )

    cb_id = existing["linked_cash_book_entry_id"]
    if user_id and cb_id:
        cash_direction = "in" if entry_type == "debit" else "out"
        update_cash_book_entry(
            conn, user_id, cb_id,
            {"entry_type": cash_direction, "amount": amount, "note": note},
            _sync_linked=False,
        )
        bank_id = existing["bank_account_id"]
        if bank_id and existing["payment_source"] == "bank":
            cb_row = conn.execute(
                "SELECT linked_bank_transaction_id FROM cash_book_entries WHERE id = ?",
                (cb_id,),
            ).fetchone()
            if cb_row and cb_row["linked_bank_transaction_id"]:
                tx_type = "credit" if cash_direction == "in" else "debit"
                conn.execute(
                    """
                    UPDATE bank_transactions
                    SET transaction_type = ?, amount = ?, note = ?
                    WHERE id = ?
                    """,
                    (tx_type, amount, note, cb_row["linked_bank_transaction_id"]),
                )

    row = conn.execute(
        "SELECT * FROM account_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return dict(row)


def delete_entry(conn, entry_id, user_id=None):
    voucher_id = _journal_voucher_for_entry(conn, entry_id)
    if voucher_id is not None:
        raise ValueError(
            f"This entry belongs to Journal Voucher #{voucher_id} — delete it "
            "from the Journal page so both sides stay in sync."
        )
    if user_id is None:
        row = conn.execute(
            """
            SELECT a.user_id FROM account_entries ae
            JOIN accounts a ON a.id = ae.account_id
            WHERE ae.id = ?
            """,
            (entry_id,),
        ).fetchone()
        user_id = row["user_id"] if row else None
    if user_id:
        _delete_account_entry_cascade(conn, user_id, entry_id)
    else:
        _delete_account_entry_raw(conn, entry_id)


def accounts_summary(conn, user_id):
    accounts = [a for a in list_accounts(conn, user_id) if not a["is_expense_category"]]
    total_receivable = sum(a["balance"] for a in accounts if a["balance"] > 0)
    total_payable = sum(abs(a["balance"]) for a in accounts if a["balance"] < 0)
    return {
        "total_accounts": len(accounts),
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
    }


def customer_recovery_analysis(conn, user_id):
    """Per-customer: total billed to them, total collected, total still
    outstanding, and how long the oldest outstanding amount has been owed.

    Billed/collected are computed directly from account_entries (credit =
    billed, debit = collected) rather than joining phones.sale_price — a
    receivable can come from a phone sale, a journal/hawala settlement, or a
    manual entry, and not all of those carry a phones.buyer_account_id link.
    Deriving "collected" as total_sold - outstanding previously produced
    impossible negative-implied values whenever a customer's balance grew
    from something other than a phone linked to their account.
    """
    accounts = [a for a in list_accounts(conn, user_id) if not a["is_expense_category"]]
    results = []
    for acct in accounts:
        agg = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN entry_type = 'credit' THEN amount ELSE 0 END), 0) AS billed,
                COALESCE(SUM(CASE WHEN entry_type = 'debit' THEN amount ELSE 0 END), 0) AS collected,
                MIN(CASE WHEN entry_type = 'credit' THEN created_at END) AS oldest_credit
            FROM account_entries
            WHERE account_id = ?
            """,
            (acct["id"],),
        ).fetchone()
        billed = round(agg["billed"] or 0, 2)
        collected = round(agg["collected"] or 0, 2)
        outstanding = round(acct["balance"], 2) if acct["balance"] > 0 else 0.0
        if billed <= 0 and outstanding <= 0:
            continue
        results.append({
            "account_id": acct["id"],
            "name": acct["name"],
            "contact": acct.get("contact"),
            "total_sold": billed,
            "total_collected": collected,
            "total_outstanding": outstanding,
            "oldest_outstanding_date": (agg["oldest_credit"] if outstanding > 0 else None),
        })
    results.sort(key=lambda r: r["total_outstanding"], reverse=True)
    return results


EXPENSE_CATEGORY_NAMES = ()


def seed_expense_accounts(conn, user_id):
    """Default expense category accounts are no longer auto-created."""
    return


def list_khata_accounts(conn, user_id):
    """Person/supplier accounts only — excludes expense category accounts."""
    return [a for a in list_accounts(conn, user_id) if not a["is_expense_category"]]


def list_journal_vouchers(conn, user_id):
    rows = conn.execute(
        """
        SELECT jv.*,
            da.name AS debit_account_name,
            ca.name AS credit_account_name
        FROM journal_vouchers jv
        JOIN accounts da ON da.id = jv.debit_account_id
        JOIN accounts ca ON ca.id = jv.credit_account_id
        WHERE jv.user_id = ?
        ORDER BY jv.voucher_date DESC, jv.id DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_journal_voucher(conn, user_id, data):
    amount = float(data["amount"])
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    debit_id = int(data["debit_account_id"])
    credit_id = int(data["credit_account_id"])
    if debit_id == credit_id:
        raise ValueError("Debit and credit accounts must be different")

    debit_acct = get_account(conn, user_id, debit_id)
    credit_acct = get_account(conn, user_id, credit_id)
    if not debit_acct or not credit_acct:
        raise ValueError("Invalid account selected")

    voucher_date = data.get("voucher_date") or _local_date(conn)
    reference = data.get("reference", "")
    narration = data.get("narration", "")

    cursor = conn.execute(
        """
        INSERT INTO journal_vouchers (
            voucher_date, reference, narration,
            debit_account_id, credit_account_id, amount, user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (voucher_date, reference, narration, debit_id, credit_id, amount, user_id),
    )
    voucher_id = cursor.lastrowid
    note = narration or reference or f"Journal voucher #{voucher_id}"
    debit_entry_id = _insert_account_entry(conn, debit_id, "debit", amount, note)
    credit_entry_id = _insert_account_entry(conn, credit_id, "credit", amount, note)
    conn.execute(
        """
        UPDATE journal_vouchers
        SET debit_entry_id = ?, credit_entry_id = ?
        WHERE id = ?
        """,
        (debit_entry_id, credit_entry_id, voucher_id),
    )
    _record_ledger_link(
        conn, user_id, "journal_voucher", voucher_id,
        account_entry_id=debit_entry_id,
    )
    _record_ledger_link(
        conn, user_id, "journal_voucher", voucher_id,
        account_entry_id=credit_entry_id,
    )

    row = conn.execute(
        """
        SELECT jv.*,
            da.name AS debit_account_name,
            ca.name AS credit_account_name
        FROM journal_vouchers jv
        JOIN accounts da ON da.id = jv.debit_account_id
        JOIN accounts ca ON ca.id = jv.credit_account_id
        WHERE jv.id = ?
        """,
        (voucher_id,),
    ).fetchone()
    return dict(row)


def delete_journal_voucher(conn, user_id, voucher_id):
    row = conn.execute(
        "SELECT * FROM journal_vouchers WHERE id = ? AND user_id = ?",
        (voucher_id, user_id),
    ).fetchone()
    if not row:
        return False
    if row["debit_entry_id"]:
        _delete_account_entry_cascade(conn, user_id, row["debit_entry_id"])
    if row["credit_entry_id"]:
        _delete_account_entry_cascade(conn, user_id, row["credit_entry_id"])
    conn.execute(
        "DELETE FROM ledger_links WHERE user_id = ? AND source_type = 'journal_voucher' AND source_id = ?",
        (user_id, voucher_id),
    )
    conn.execute(
        "DELETE FROM journal_vouchers WHERE id = ? AND user_id = ?",
        (voucher_id, user_id),
    )
    return True


# --- Backup / Export ---

def export_all_data(conn, user_id):
    settings = get_user_settings(conn, user_id)
    return {
        "settings": settings,
        "partners": list_partners(conn, user_id),
        "phones": [
            phone_to_dict(conn, dict(r), include_details=True)
            for r in conn.execute(
                "SELECT * FROM phones WHERE user_id = ?", (user_id,)
            ).fetchall()
        ],
        "accounts": list_accounts(conn, user_id),
        "account_entries": [
            dict(r) for r in conn.execute(
                """
                SELECT ae.* FROM account_entries ae
                JOIN accounts a ON a.id = ae.account_id
                WHERE a.user_id = ?
                """,
                (user_id,),
            ).fetchall()
        ],
        "fixed_expenses": list_fixed_expenses(conn, user_id),
        "bank_accounts": list_banks(conn, user_id),
        "bank_transactions": [
            dict(r) for r in conn.execute(
                """
                SELECT bt.* FROM bank_transactions bt
                JOIN bank_accounts ba ON ba.id = bt.bank_account_id
                WHERE ba.user_id = ?
                """,
                (user_id,),
            ).fetchall()
        ],
        "cash_book_entries": [
            dict(r) for r in conn.execute(
                "SELECT * FROM cash_book_entries WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        ],
        "phone_expenses": [
            dict(r) for r in conn.execute(
                """
                SELECT pe.* FROM phone_expenses pe
                JOIN phones p ON p.id = pe.phone_id
                WHERE p.user_id = ?
                """,
                (user_id,),
            ).fetchall()
        ],
        "phone_investments": [
            dict(r) for r in conn.execute(
                """
                SELECT pi.* FROM phone_investments pi
                JOIN phones p ON p.id = pi.phone_id
                WHERE p.user_id = ?
                """,
                (user_id,),
            ).fetchall()
        ],
    }


# --- Today dashboard ---

def compute_today_summary(conn, user_id):
    sold = conn.execute(
        """
        SELECT * FROM phones
        WHERE user_id = ? AND status = 'Sold'
          AND date(sold_at) = date('now', 'localtime')
        ORDER BY sold_at DESC
        """,
        (user_id,),
    ).fetchall()
    bought = conn.execute(
        """
        SELECT * FROM phones
        WHERE user_id = ?
          AND status IN ('Bought', 'In Repair', 'Sold')
          AND (
            date(COALESCE(NULLIF(TRIM(purchase_date), ''), date(created_at, 'localtime'))) = date('now', 'localtime')
            OR date(created_at, 'localtime') = date('now', 'localtime')
          )
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    cash = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN entry_type = 'in' AND COALESCE(payment_source, 'cash') = 'cash'
                THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN entry_type = 'out' AND COALESCE(payment_source, 'cash') = 'cash'
                THEN amount ELSE 0 END), 0) AS cash_out
        FROM cash_book_entries
        WHERE user_id = ? AND entry_date = date('now', 'localtime')
        """,
        (user_id,),
    ).fetchone()
    revenue = sum((r["sale_price"] or 0) for r in sold)
    profit = sum(_sold_profit(conn, r) for r in sold)
    sold_phones = [phone_to_dict(conn, r) for r in sold]
    bought_phones = [phone_to_dict(conn, r) for r in bought]
    return {
        "date_label": conn.execute(
            "SELECT strftime('%A, %d %B %Y', 'now', 'localtime') AS label"
        ).fetchone()["label"],
        "phones_sold": len(sold),
        "phones_bought": len(bought),
        "sales_revenue": round(revenue, 2),
        "sales_profit": round(profit, 2),
        "purchase_spend": round(sum((r["purchase_price"] or 0) for r in bought), 2),
        "cash_in": round(cash["cash_in"] or 0, 2),
        "cash_out": round(cash["cash_out"] or 0, 2),
        "sold_phones": sold_phones,
        "bought_phones": bought_phones,
    }


# --- Month report ---

def compute_month_report(conn, user_id, year_month=None, start_date=None, end_date=None):
    if start_date and end_date:
        sold = conn.execute(
            """
            SELECT * FROM phones
            WHERE user_id = ? AND status = 'Sold' AND sold_at IS NOT NULL
              AND date(sold_at) BETWEEN date(?) AND date(?)
            ORDER BY sold_at DESC
            """,
            (user_id, start_date, end_date),
        ).fetchall()
        month_label = (
            f"{datetime.strptime(start_date, '%Y-%m-%d').strftime('%d %b %Y')} – "
            f"{datetime.strptime(end_date, '%Y-%m-%d').strftime('%d %b %Y')}"
        )
        year_month = None
    else:
        if not year_month:
            year_month = conn.execute(
                "SELECT strftime('%Y-%m', 'now', 'localtime') AS ym"
            ).fetchone()["ym"]

        sold = conn.execute(
            """
            SELECT * FROM phones
            WHERE user_id = ? AND status = 'Sold' AND sold_at IS NOT NULL
              AND strftime('%Y-%m', sold_at) = ?
            ORDER BY sold_at DESC
            """,
            (user_id, year_month),
        ).fetchall()
        month_label = datetime.strptime(year_month, "%Y-%m").strftime("%B %Y")

    acct = accounts_summary(conn, user_id)
    dash = compute_dashboard(conn, user_id)
    revenue = sum((r["sale_price"] or 0) for r in sold)
    profit = sum(_sold_profit(conn, r) for r in sold)

    return {
        "year_month": year_month,
        "month_label": month_label,
        "units_sold": len(sold),
        "total_revenue": round(revenue, 2),
        "total_profit": round(profit, 2),
        "total_udhar": dash["total_udhar"],
        "total_receivable": acct["total_receivable"],
        "total_payable": acct["total_payable"],
        "sales": [phone_to_dict(conn, r) for r in sold],
        "shop": get_shop_info(conn, user_id),
    }


# --- Invoices ---

def _next_invoice_number(conn, user_id):
    settings = get_user_settings(conn, user_id)
    counter = int(settings.get("invoice_counter") or 1000)
    max_row = conn.execute(
        "SELECT MAX(invoice_number) AS m FROM invoices WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    current_max = max_row["m"] or 0
    num = max(counter, current_max + 1)
    update_user_settings(conn, user_id, {"invoice_counter": str(num + 1)})
    return num


def create_invoice(conn, user_id, data):
    """Create a printable invoice record (does not post to cash book — sale already synced in inventory)."""
    if not conn.in_transaction:
        # Hold the write lock across the "pick next number" + insert so two
        # near-simultaneous saves (e.g. a double-click) can't both grab the
        # same invoice number.
        conn.execute("BEGIN IMMEDIATE")
    explicit_num = data.get("invoice_number")
    attempts = 1 if explicit_num else 5
    for attempt in range(attempts):
        inv_num = int(explicit_num) if explicit_num else _next_invoice_number(conn, user_id)
        try:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_number, customer_name, customer_phone, phone_id,
                    model, variant, imei, phone_type, condition, amount,
                    warranty, notes, invoice_date, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(inv_num),
                    data.get("customer_name", ""),
                    data.get("customer_phone", ""),
                    data.get("phone_id"),
                    data.get("model", ""),
                    data.get("variant", ""),
                    data.get("imei", ""),
                    data.get("phone_type", ""),
                    data.get("condition", ""),
                    float(data.get("amount") or 0),
                    data.get("warranty", ""),
                    data.get("notes", ""),
                    data.get("invoice_date") or _local_date(conn),
                    user_id,
                ),
            )
            break
        except sqlite3.IntegrityError:
            if explicit_num:
                # A user-typed/pre-filled number that already belongs to this
                # account -- never silently substitute a different number
                # for what they asked for, surface a clear error instead.
                raise ValueError(
                    f"Invoice #{inv_num} already exists for this account — "
                    "choose a different invoice number."
                )
            if attempt == attempts - 1:
                raise RuntimeError(
                    "Could not allocate a unique invoice number after several attempts"
                )
            # Auto-generated number lost a race (should be extremely rare —
            # BEGIN IMMEDIATE above already serializes writers; this is
            # defense in depth) -- retry with a freshly computed number.
            continue
    return get_invoice(conn, user_id, cursor.lastrowid)


def get_invoice(conn, user_id, invoice_id):
    row = conn.execute(
        "SELECT * FROM invoices WHERE id = ? AND user_id = ?",
        (invoice_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_invoices(conn, user_id, limit=50):
    rows = conn.execute(
        """
        SELECT * FROM invoices WHERE user_id = ?
        ORDER BY created_at DESC, id DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Purchase Invoices ---

def _next_purchase_invoice_number(conn, user_id):
    settings = get_user_settings(conn, user_id)
    counter = int(settings.get("purchase_invoice_counter") or 1000)
    max_row = conn.execute(
        "SELECT MAX(invoice_number) AS m FROM purchase_invoices WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    current_max = max_row["m"] or 0
    num = max(counter, current_max + 1)
    update_user_settings(conn, user_id, {"purchase_invoice_counter": str(num + 1)})
    return num


def create_purchase_invoice(conn, user_id, data):
    """Create a printable purchase-invoice record (paperwork only — does not post to cash book)."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    explicit_num = data.get("invoice_number")
    attempts = 1 if explicit_num else 5
    for attempt in range(attempts):
        inv_num = int(explicit_num) if explicit_num else _next_purchase_invoice_number(conn, user_id)
        try:
            cursor = conn.execute(
                """
                INSERT INTO purchase_invoices (
                    invoice_number, supplier_name, supplier_contact, phone_id,
                    model, variant, imei, phone_type, condition, amount,
                    notes, invoice_date, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(inv_num),
                    data.get("supplier_name", ""),
                    data.get("supplier_contact", ""),
                    data.get("phone_id"),
                    data.get("model", ""),
                    data.get("variant", ""),
                    data.get("imei", ""),
                    data.get("phone_type", ""),
                    data.get("condition", ""),
                    float(data.get("amount") or 0),
                    data.get("notes", ""),
                    data.get("invoice_date") or _local_date(conn),
                    user_id,
                ),
            )
            break
        except sqlite3.IntegrityError:
            if explicit_num:
                raise ValueError(
                    f"Purchase invoice #{inv_num} already exists for this account — "
                    "choose a different invoice number."
                )
            if attempt == attempts - 1:
                raise RuntimeError(
                    "Could not allocate a unique invoice number after several attempts"
                )
            continue
    return get_purchase_invoice(conn, user_id, cursor.lastrowid)


def get_purchase_invoice(conn, user_id, invoice_id):
    row = conn.execute(
        "SELECT * FROM purchase_invoices WHERE id = ? AND user_id = ?",
        (invoice_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_purchase_invoices(conn, user_id, limit=50):
    rows = conn.execute(
        """
        SELECT * FROM purchase_invoices WHERE user_id = ?
        ORDER BY created_at DESC, id DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_backup_files(conn, user_id):
    """List backup files for the restore picker. Restricted to files this
    specific user created (matched by their own username-slug prefix) even
    though `local_backup_path` is, by default, one shared folder for every
    account on this installation — otherwise the picker would let a user
    browse to (and restore from) another user's backup."""
    settings = get_storage_settings(conn, user_id)
    backup_dir = (settings.get("local_backup_path") or "").strip()
    if not backup_dir:
        return []
    path = Path(backup_dir)
    if not path.is_dir():
        return []
    slug = backup_username_slug(conn, user_id)
    files = sorted(
        set(path.glob(f"{slug}_crm_backup_*.db")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "path": str(f),
            "name": f.name,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
        for f in files[:20]
    ]


def _validate_backup_file(path: Path) -> None:
    """Open the candidate backup and confirm it's an intact CRM database
    before it's allowed to import into the live one. A corrupted, empty, or
    unrelated .db file gets rejected here instead of destroying today's data."""
    try:
        check_conn = sqlite3.connect(str(path))
    except sqlite3.Error as exc:
        raise ValueError(f"Backup file could not be opened: {exc}") from exc
    try:
        result = check_conn.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("Backup file failed SQLite's integrity check — it may be corrupted")
        table = check_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='phones'"
        ).fetchone()
        if not table:
            raise ValueError("This doesn't look like a Phone Reseller CRM backup file")
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Backup file is not a valid database: {exc}") from exc
    finally:
        check_conn.close()


def _validate_restore_source(conn, user_id: int, backup_path: str) -> Path:
    """Resolve and sandbox the chosen backup file to this user's own backup
    folder and their own filename prefix. Rejects path traversal, symlink
    escapes, absolute paths elsewhere, and other users' backup files."""
    if not backup_path:
        raise ValueError("Select a backup file to restore")
    src = Path(backup_path).expanduser().resolve()
    if not src.is_file():
        raise ValueError("Backup file not found")
    if src.suffix.lower() != ".db":
        raise ValueError("Please select a .db backup file")

    settings = get_storage_settings(conn, user_id)
    backup_dir = (settings.get("local_backup_path") or "").strip()
    if not backup_dir:
        raise ValueError("No backup folder is configured for this account")
    allowed_root = Path(backup_dir).expanduser().resolve()
    if allowed_root not in src.parents:
        raise ValueError("That file is not inside your backup folder")

    slug = backup_username_slug(conn, user_id)
    if not src.name.startswith(f"{slug}_crm_backup_"):
        raise ValueError("That backup file does not belong to this account")

    return src


def _tables_with_user_id_column(conn) -> list[str]:
    """Every table in the current schema that has its own `user_id` column,
    discovered dynamically (never hardcoded) so a per-user restore can never
    silently miss a table a future migration adds. Deliberately excludes
    `users` (has no user_id column — it's the identity table itself, id is
    its own key) and `settings` (global, pre-multi-user legacy table)."""
    tables = [
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return [
        t for t in tables
        if any(c["name"] == "user_id" for c in conn.execute(f"PRAGMA table_info({t})").fetchall())
    ]


def _resolve_table_ownership_paths(conn) -> dict:
    """Map every user-owned table (direct `user_id` column, or a row that
    belongs to a user only via a foreign key into an already-resolved
    user-owned table) to how to scope it to one user_id.

    Returns an (insertion-ordered) dict of:
      table -> ("direct",)                     -- has its own user_id column
      table -> ("via", fk_column, parent_table) -- owned through a parent FK

    Built by walking the live schema (sqlite_master + PRAGMA foreign_key_list)
    rather than a hand-maintained table list, per the rule that silently
    missing a table here is exactly the bug this restore rewrite exists to
    close. If a table can't be resolved either way, this raises loudly
    instead of quietly skipping it — a new unresolvable table must get an
    explicit rule added here before restore can be trusted again."""
    all_tables = [
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    direct = set(_tables_with_user_id_column(conn))
    paths: dict = {t: ("direct",) for t in all_tables if t in direct}

    remaining = [t for t in all_tables if t not in direct and t not in ("users", "settings")]
    resolved_targets = set(direct)
    changed = True
    while changed and remaining:
        changed = False
        still_remaining = []
        for t in remaining:
            fks = conn.execute(f"PRAGMA foreign_key_list({t})").fetchall()
            cols = {c["name"]: c for c in conn.execute(f"PRAGMA table_info({t})").fetchall()}
            found = None
            for fk in fks:
                parent = fk["table"]
                child_col = fk["from"]
                if parent in resolved_targets and cols.get(child_col) is not None \
                        and cols[child_col]["notnull"]:
                    found = (child_col, parent)
                    break
            if found:
                paths[t] = ("via",) + found
                resolved_targets.add(t)
                changed = True
            else:
                still_remaining.append(t)
        remaining = still_remaining

    if remaining:
        raise RuntimeError(
            "Restore cannot determine per-user ownership for table(s) "
            f"{remaining} — add an explicit rule in "
            "_resolve_table_ownership_paths before restore can proceed safely."
        )
    return paths


def _restore_user_rows(conn, user_id: int) -> None:
    """Replace exactly one user's rows across every user-owned table, from
    the database ATTACHed as `backup_db`, leaving every other user's data in
    the live database completely untouched. Must run with
    `PRAGMA foreign_keys = OFF` on `conn` for the duration (set by the
    caller) since deletes/inserts happen table-by-table, not in dependency
    order for FK purposes."""
    ownership = _resolve_table_ownership_paths(conn)

    # Delete children before parents: a "via" table's delete depends on the
    # live parent table's rows still being present (to look up which ids
    # belonged to this user), so parents must not be cleared first.
    for table, path in reversed(list(ownership.items())):
        if path[0] == "direct":
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        else:
            _, fk_col, parent = path
            conn.execute(
                f"DELETE FROM {table} WHERE {fk_col} IN "
                f"(SELECT id FROM {parent} WHERE user_id = ?)",
                (user_id,),
            )

    # Insert order doesn't matter: foreign_keys is OFF for this transaction,
    # and the source (backup_db) is read-only/untouched throughout.
    for table, path in ownership.items():
        cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        col_list = ", ".join(cols)
        if path[0] == "direct":
            conn.execute(
                f"INSERT INTO {table} ({col_list}) "
                f"SELECT {col_list} FROM backup_db.{table} WHERE user_id = ?",
                (user_id,),
            )
        else:
            _, fk_col, parent = path
            conn.execute(
                f"INSERT INTO {table} ({col_list}) "
                f"SELECT {col_list} FROM backup_db.{table} WHERE {fk_col} IN "
                f"(SELECT id FROM backup_db.{parent} WHERE user_id = ?)",
                (user_id,),
            )


def _snapshot_live_db(live: sqlite3.Connection, dest_path: Path) -> None:
    """Write a consistent copy of the live database to dest_path using
    SQLite's own backup API (never a raw file copy — see backup_service.py's
    _snapshot_database for why a plain shutil.copy2 of a live, possibly
    WAL-mode, possibly mid-write database file is not safe, especially on
    Windows)."""
    if dest_path.exists():
        dest_path.unlink()
    snap_conn = sqlite3.connect(str(dest_path))
    try:
        live.backup(snap_conn)
    finally:
        snap_conn.close()


def _restore_live_db_from_snapshot(dest_path: Path) -> None:
    """Overwrite the live database's content from a snapshot file, via the
    backup API (not a file copy). Used only to auto-roll-back a restore that
    failed its post-restore integrity check."""
    snap_conn = sqlite3.connect(str(dest_path))
    try:
        live = get_connection()
        try:
            snap_conn.backup(live)
        finally:
            live.close()
    finally:
        snap_conn.close()


def restore_database_from_backup(backup_path: str, user_id: int) -> str:
    """Restore one user's data from their own backup file, in place, without
    touching any other user's rows in the shared crm.db.

    Full-file replacement (the old behaviour) was wrong for a multi-user
    database: it silently destroyed every other account's data, and did it
    with a raw shutil.copy2 straight onto the live db file, which risks a
    locked or torn copy on Windows if anything else touches the file mid-copy.
    This instead:
      1. Checkpoints the WAL and takes a safety snapshot of the live db via
         the backup API (not a file copy) before touching anything.
      2. Migrates a scratch copy of the backup up to the current schema, if
         it's older, so the cross-database copy below always sees matching
         columns.
      3. Within a single ordinary write transaction on the live db (the same
         connection machinery — WAL + busy_timeout — every other write in
         this app already uses, not a special-cased file swap), deletes this
         user's current rows and re-inserts their rows from the backup,
         across every user-owned table in the schema (discovered
         dynamically, see _resolve_table_ownership_paths).
      4. Verifies PRAGMA foreign_key_check and PRAGMA integrity_check both
         come back clean before declaring success. If either fails, the live
         db is automatically rolled back to the pre-restore snapshot and a
         clear error is raised — the caller's data is left exactly as it was
         before the restore was attempted, not partially changed.
    """
    with db_session() as conn:
        src = _validate_restore_source(conn, user_id, backup_path)
    _validate_backup_file(src)

    dest = DB_PATH.resolve()
    safety = dest.with_name(
        f"{dest.stem}.pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}{dest.suffix}"
    )

    with tempfile.TemporaryDirectory(prefix="crm_restore_") as tmp:
        migrated = Path(tmp) / "migrated_backup.db"
        shutil.copy2(src, migrated)
        mig_conn = sqlite3.connect(str(migrated))
        mig_conn.row_factory = sqlite3.Row
        try:
            _init_schema(mig_conn)
            mig_conn.commit()
        finally:
            mig_conn.close()

        live = get_connection()
        try:
            live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if dest.is_file():
                _snapshot_live_db(live, safety)

            live.execute("PRAGMA foreign_keys = OFF")
            live.execute("ATTACH DATABASE ? AS backup_db", (str(migrated),))
            try:
                live.execute("BEGIN")
                _restore_user_rows(live, user_id)
                live.commit()
            except Exception:
                live.rollback()
                raise
            finally:
                live.execute("DETACH DATABASE backup_db")
            live.execute("PRAGMA foreign_keys = ON")

            fk_errors = live.execute("PRAGMA foreign_key_check").fetchall()
            integrity = live.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            live.close()

    if fk_errors or integrity != "ok":
        if safety.is_file():
            _restore_live_db_from_snapshot(safety)
        raise ValueError(
            "Restore failed its post-restore integrity check and was "
            "automatically rolled back — your data was not changed. "
            f"(integrity_check={integrity}, foreign_key_errors={len(fk_errors)})"
        )

    return str(safety) if safety.is_file() else ""
