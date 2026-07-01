from __future__ import annotations

import json
import random
import re
import shutil
import sqlite3
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


def _app_bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def customer_data_dir() -> Path | None:
    """Customer Copy live data folder (next to the .app bundle)."""
    if not getattr(sys, "frozen", False):
        return None
    return _app_bundle_dir() / "Data"


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

DEFAULT_USER = {"username": "shahir", "password": "test123"}

DEFAULT_SETTINGS = {
    "partner1_name": "Talha",
    "partner1_capital": "241000",
    "partner2_name": "Me",
    "partner2_capital": "241000",
    "cash_in_hand": "0",
    "theme": "default-dark",
    "shop_name": "My Phone Shop",
    "shop_address": "",
    "shop_phones": "[]",
    "local_backup_path": "",
    "google_drive_sync_enabled": "false",
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
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


def init_db():
    with db_session() as conn:
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
        _migrate_cursor_panga(conn)
        _migrate_payment_methods(conn)
        _migrate_account_entry_payments(conn)

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        _migrate_multi_user(conn)
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

    _run_migration_script(
        conn,
        """
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
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        INSERT INTO phones_migrated (
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at
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
            sold_at, created_at
        FROM phones;

        DROP TABLE phones;
        ALTER TABLE phones_migrated RENAME TO phones;
        """,
        staging_table="phones_migrated",
    )


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

    if _table_exists(conn, "phones_status_migrated") and not _table_exists(conn, "phones"):
        conn.execute("ALTER TABLE phones_status_migrated RENAME TO phones")
        return

    has_user_id = _column_exists(conn, "phones", "user_id")
    user_id_col = (
        ",\n            user_id INTEGER REFERENCES users(id)"
        if has_user_id
        else ""
    )
    user_id_copy = ", user_id" if has_user_id else ""

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
            purchase_date TEXT NOT NULL DEFAULT ''{user_id_col}
        );

        INSERT INTO phones_status_migrated (
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at, imei, box_status, battery_health, variant,
            purchase_date{user_id_copy}
        )
        SELECT
            id, model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, created_at, imei, box_status, battery_health, variant,
            purchase_date{user_id_copy}
        FROM phones;

        DROP TABLE phones;
        ALTER TABLE phones_status_migrated RENAME TO phones;
        """,
        staging_table="phones_status_migrated",
    )


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
    if current:
        return current
    backup_dir = default_backup_dir()
    if not backup_dir:
        return ""
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = str(backup_dir)
    update_user_settings(conn, user_id, {"local_backup_path": path})
    return path


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

    legacy_db = _app_bundle_dir() / "crm.db"
    if legacy_db.is_file() and legacy_db.resolve() != DB_PATH.resolve():
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
        "google_drive_sync_enabled": settings.get("google_drive_sync_enabled", "false") == "true",
        "auto_backup_enabled": settings.get("auto_backup_enabled", "true") == "true",
        "last_backup_at": settings.get("last_backup_at", ""),
        "auto_backup_interval_hours": 1,
    }


def update_storage_settings(conn, user_id, data):
    """Persist backup path and Google Drive sync toggle (sync logic is placeholder)."""
    payload = {}
    if "local_backup_path" in data:
        payload["local_backup_path"] = str(data.get("local_backup_path") or "").strip()
    if "google_drive_sync_enabled" in data:
        payload["google_drive_sync_enabled"] = "true" if data.get("google_drive_sync_enabled") else "false"
    if "auto_backup_enabled" in data:
        payload["auto_backup_enabled"] = "true" if data.get("auto_backup_enabled") else "false"
    if payload:
        update_user_settings(conn, user_id, payload)
    return get_storage_settings(conn, user_id)


def update_user_settings(conn, user_id, data):
    allowed = {
        "partner1_name", "partner1_capital", "partner2_name", "partner2_capital",
        "cash_in_hand", "theme", "shop_name", "shop_address", "shop_phones",
        "local_backup_path", "google_drive_sync_enabled",
        "last_backup_at", "auto_backup_enabled",
        "shop_whatsapp", "vendor_whatsapp", "vendor_support_note",
        "gmail_smtp_user", "gmail_smtp_app_password", "invoice_counter",
        "profit_reinvested_total",
    }
    user_fields = {}
    for key, value in data.items():
        if key not in allowed:
            continue
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


def request_password_reset(conn, email):
    email = email.strip().lower()
    if not email:
        raise ValueError("Email is required")
    row = conn.execute(
        "SELECT id, shop_name FROM users WHERE lower(email) = ?", (email,)
    ).fetchone()
    if not row:
        raise ValueError("No account found with that email")

    email_cfg = get_email_settings(conn, None)
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
    expires = (datetime.utcnow() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
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
    admin_id = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()["id"]
    admin_settings = get_user_settings(conn, admin_id)
    email_service.send_otp_email(
        email,
        otp,
        smtp_user=admin_settings["gmail_smtp_user"],
        smtp_password=admin_settings["gmail_smtp_app_password"],
        shop_name=row["shop_name"] or admin_settings.get("shop_name", "Phone Reseller CRM"),
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

    user = conn.execute(
        "SELECT id FROM users WHERE lower(email) = ?", (email,)
    ).fetchone()
    if not user:
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
        raise ValueError("Invalid or expired OTP")

    if token["expires_at"] < datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        raise ValueError("OTP has expired — request a new one")

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password, method=PASSWORD_HASH_METHOD), user["id"]),
    )
    conn.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE id = ?",
        (token["id"],),
    )
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
    conn.execute(
        "DELETE FROM partners WHERE id = ? AND user_id = ?",
        (partner_id, user_id),
    )


def reinvest_profit(conn, user_id, data):
    """Move available profit into a partner's invested capital."""
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
    total_net_profit = sum(
        (r["sale_price"] or 0) - (r["purchase_price"] or 0) for r in sold
    )
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
        conn.execute("SELECT datetime('now')").fetchone()[0] if status == "Sold" else None,
        data.get("imei", ""),
        data.get("box_status", ""),
        data.get("battery_health", ""),
        data.get("variant", ""),
        data.get("purchase_date") or conn.execute("SELECT date('now')").fetchone()[0],
    )


def _save_phone_extras(conn, phone_id, data):
    expenses = data.get("expenses") or []
    for exp in expenses:
        if float(exp.get("amount") or 0) > 0:
            conn.execute(
                "INSERT INTO phone_expenses (phone_id, amount, description) VALUES (?, ?, ?)",
                (phone_id, float(exp["amount"]), exp.get("description", "")),
            )

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
):
    """Record cash book or bank movement for phone purchase/sale payments."""
    if amount <= 0:
        return
    if payment_method == "bank":
        if not bank_id:
            raise ValueError("Select a bank account for bank payment")
        if not get_bank(conn, user_id, int(bank_id)):
            raise ValueError("Bank account not found")
        create_cash_book_entry(conn, user_id, {
            "entry_type": entry_type,
            "amount": amount,
            "note": note,
            "entry_date": entry_date,
            "payment_source": "bank",
            "bank_account_id": int(bank_id),
        })
    else:
        create_cash_book_entry(conn, user_id, {
            "entry_type": entry_type,
            "amount": amount,
            "note": note,
            "entry_date": entry_date,
            "payment_source": "cash",
        })


def _post_purchase_payment(conn, user_id, phone_id, data):
    purchase_price = float(data.get("purchase_price") or 0)
    payable = float(data.get("payable_amount") or 0)
    paid_now = max(0.0, purchase_price - payable)
    if paid_now <= 0:
        return
    method = data.get("purchase_payment_method") or "cash"
    bank_id = data.get("purchase_bank_id")
    model = data.get("model", "Phone")
    entry_date = data.get("purchase_date") or conn.execute("SELECT date('now')").fetchone()[0]
    _post_payment_transaction(
        conn, user_id, method, bank_id, "out", paid_now,
        f"Purchase: {model} (#{phone_id})", entry_date,
    )


def _post_sale_payment(conn, user_id, phone_id, data):
    sale_price = float(data.get("sale_price") or 0)
    receivable = float(data.get("receivable_amount") or 0)
    received_now = max(0.0, sale_price - receivable)
    if received_now <= 0:
        return
    method = data.get("sale_payment_method") or "cash"
    bank_id = data.get("sale_bank_id")
    model = data.get("model", "Phone")
    entry_date = conn.execute("SELECT date('now')").fetchone()[0]
    _post_payment_transaction(
        conn, user_id, method, bank_id, "in", received_now,
        f"Sale: {model} (#{phone_id})", entry_date,
    )


def _validate_phone_payments(conn, user_id, data, status):
    if status in ("Bought", "In Repair"):
        method = data.get("purchase_payment_method") or "cash"
        if method not in ("cash", "bank"):
            raise ValueError("Purchase payment method must be Cash or Bank")
        if method == "bank" and not data.get("purchase_bank_id"):
            raise ValueError("Select a bank account for purchase payment")
        if method == "bank" and not get_bank(conn, user_id, int(data["purchase_bank_id"])):
            raise ValueError("Selected bank account not found")
    if status == "Sold":
        method = data.get("sale_payment_method") or "cash"
        if method not in ("cash", "bank"):
            raise ValueError("Sale payment method must be Cash or Bank")
        if method == "bank" and not data.get("sale_bank_id"):
            raise ValueError("Select a bank account for sale payment")
        if method == "bank" and not get_bank(conn, user_id, int(data["sale_bank_id"])):
            raise ValueError("Selected bank account not found")


def create_phone(conn, user_id, data):
    status = data.get("status", "Bought")
    _validate_phone_payments(conn, user_id, data, status)
    values = _build_phone_insert_values(conn, data)
    purchase_pm = data.get("purchase_payment_method") or "cash"
    purchase_bank = data.get("purchase_bank_id")
    sale_pm = data.get("sale_payment_method") or "cash"
    sale_bank = data.get("sale_bank_id")
    cursor = conn.execute(
        """
        INSERT INTO phones (
            model, condition, type, purchase_price,
            supplier_name, supplier_contact, status,
            payable_amount, advance_received,
            buyer_name, buyer_contact, sale_price, receivable_amount,
            sold_at, imei, box_status, battery_health, variant, purchase_date,
            purchase_payment_method, purchase_bank_id, sale_payment_method, sale_bank_id,
            user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            *values,
            purchase_pm,
            int(purchase_bank) if purchase_bank else None,
            sale_pm,
            int(sale_bank) if sale_bank else None,
            user_id,
        ),
    )
    phone_id = cursor.lastrowid
    _save_phone_extras(conn, phone_id, data)
    if status in ("Bought", "In Repair"):
        _post_purchase_payment(conn, user_id, phone_id, data)
    if status == "Sold":
        _post_purchase_payment(conn, user_id, phone_id, data)
        _post_sale_payment(conn, user_id, phone_id, data)
    return get_phone(conn, user_id, phone_id, include_details=True)


def create_phones_bulk(conn, user_id, data):
    quantity = int(data.get("quantity") or 1)
    imeis = data.get("imeis") or []
    created = []
    for i in range(quantity):
        phone_data = dict(data)
        phone_data["imei"] = imeis[i] if i < len(imeis) else ""
        phone_data.pop("quantity", None)
        phone_data.pop("imeis", None)
        if quantity > 1 and i > 0:
            phone_data["expenses"] = []
            phone_data["investments"] = []
        created.append(create_phone(conn, user_id, phone_data))
    return created


def update_phone(conn, user_id, phone_id, data):
    existing = conn.execute(
        "SELECT * FROM phones WHERE id = ? AND user_id = ?",
        (phone_id, user_id),
    ).fetchone()
    if not existing:
        return None

    new_status = data.get("status", existing["status"])
    _validate_phone_payments(conn, user_id, {**dict(existing), **data}, new_status)
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
        "imei", "box_status", "battery_health", "variant", "purchase_date",
        "purchase_payment_method", "purchase_bank_id", "sale_payment_method", "sale_bank_id",
    ]
    numeric_fields = {
        "purchase_price", "payable_amount", "advance_received",
        "sale_price", "receivable_amount",
    }
    for field in simple_fields:
        if field in data:
            fields.append(f"{field} = ?")
            val = data[field]
            if field in ("purchase_bank_id", "sale_bank_id"):
                val = int(val) if val not in (None, "", 0) else None
            elif field in numeric_fields:
                val = float(val) if val not in (None, "") else 0
            values.append(val)

    if new_status == "Sold" and existing["status"] != "Sold":
        fields.append("sold_at = datetime('now')")
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
        _save_phone_extras(conn, phone_id, {"investments": data["investments"]})

    if new_status == "Sold" and existing["status"] != "Sold":
        merged = {**dict(existing), **data}
        _post_sale_payment(conn, user_id, phone_id, merged)

    return get_phone(conn, user_id, phone_id, include_details=True)


def delete_phone(conn, user_id, phone_id):
    conn.execute(
        "DELETE FROM phones WHERE id = ? AND user_id = ?",
        (phone_id, user_id),
    )


def bulk_delete_phones(conn, user_id, phone_ids):
    deleted = 0
    for phone_id in phone_ids:
        existing = conn.execute(
            "SELECT id FROM phones WHERE id = ? AND user_id = ?",
            (int(phone_id), user_id),
        ).fetchone()
        if existing:
            delete_phone(conn, user_id, int(phone_id))
            deleted += 1
    return {"deleted": deleted}


def bulk_mark_sold(conn, user_id, items):
    """Mark multiple phones sold with sale price only (defaults: cash, no udhar)."""
    updated = []
    errors = []
    for item in items:
        phone_id = int(item["phone_id"])
        sale_price = float(item.get("sale_price") or 0)
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
            "receivable_amount": 0,
            "buyer_name": "",
            "buyer_contact": "",
            "sale_payment_method": "cash",
            "sale_bank_id": None,
        }
        phone = update_phone(conn, user_id, phone_id, data)
        if phone:
            updated.append(phone)
    if errors and not updated:
        raise ValueError("; ".join(errors))
    return {"updated": updated, "errors": errors}


def add_phone_expense(conn, user_id, phone_id, data):
    if not get_phone(conn, user_id, phone_id):
        return None
    cursor = conn.execute(
        "INSERT INTO phone_expenses (phone_id, amount, description) VALUES (?, ?, ?)",
        (phone_id, float(data["amount"]), data.get("description", "")),
    )
    row = conn.execute(
        "SELECT * FROM phone_expenses WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def delete_phone_expense(conn, expense_id):
    conn.execute("DELETE FROM phone_expenses WHERE id = ?", (expense_id,))


def find_phone_by_imei(conn, user_id, imei):
    imei = (imei or "").strip()
    if not imei:
        return None
    row = conn.execute(
        "SELECT * FROM phones WHERE user_id = ? AND imei = ? COLLATE NOCASE",
        (user_id, imei),
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
    phone_id = data.get("phone_id")
    imei = (data.get("imei") or "").strip()
    note = (data.get("note") or "").strip()

    phone = None
    if phone_id:
        phone = get_phone(conn, user_id, phone_id)
    elif imei:
        phone = find_phone_by_imei(conn, user_id, imei)

    if not phone:
        raise ValueError("Phone not found — enter a valid IMEI from current inventory")
    if phone["status"] not in INVENTORY_STATUSES:
        raise ValueError("Only Bought or In Repair items can be returned to supplier")

    conn.execute(
        """
        UPDATE phones SET status = 'Returned to Supplier'
        WHERE id = ? AND user_id = ?
        """,
        (phone["id"], user_id),
    )
    cursor = conn.execute(
        """
        INSERT INTO return_logs (user_id, return_type, phone_id, imei, model, party_name, note)
        VALUES (?, 'purchase', ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            phone["id"],
            phone.get("imei") or imei,
            phone["model"],
            phone.get("supplier_name") or "",
            note,
        ),
    )
    log = conn.execute(
        "SELECT * FROM return_logs WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(log)


def process_sale_return(conn, user_id, data):
    phone_id = data.get("phone_id")
    imei = (data.get("imei") or "").strip()
    note = (data.get("note") or "").strip()
    party_name = (data.get("party_name") or "").strip()

    phone = None
    if phone_id:
        phone = get_phone(conn, user_id, phone_id)
    elif imei:
        phone = find_phone_by_imei(conn, user_id, imei)

    if not phone:
        raise ValueError("Phone not found — enter a valid IMEI from sold inventory")
    if phone["status"] != "Sold":
        raise ValueError("Only sold items can be processed as sale returns")

    conn.execute(
        """
        UPDATE phones SET
            status = 'Bought',
            buyer_name = '',
            buyer_contact = '',
            sale_price = NULL,
            receivable_amount = 0,
            sold_at = NULL
        WHERE id = ? AND user_id = ?
        """,
        (phone["id"], user_id),
    )
    cursor = conn.execute(
        """
        INSERT INTO return_logs (user_id, return_type, phone_id, imei, model, party_name, note)
        VALUES (?, 'sale', ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            phone["id"],
            phone.get("imei") or imei,
            phone["model"],
            party_name or phone.get("buyer_name") or "",
            note,
        ),
    )
    log = conn.execute(
        "SELECT * FROM return_logs WHERE id = ?", (cursor.lastrowid,)
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


def create_fixed_expense(conn, user_id, data):
    cursor = conn.execute(
        "INSERT INTO fixed_expenses (purpose, amount, user_id) VALUES (?, ?, ?)",
        (data["purpose"], float(data["amount"]), user_id),
    )
    row = conn.execute(
        "SELECT * FROM fixed_expenses WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def delete_fixed_expense(conn, user_id, expense_id):
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
    cursor = conn.execute(
        "INSERT INTO bank_accounts (name, user_id) VALUES (?, ?)",
        (data["name"], user_id),
    )
    bank_id = cursor.lastrowid
    if data.get("initial_balance"):
        conn.execute(
            """
            INSERT INTO bank_transactions (bank_account_id, transaction_type, amount, note)
            VALUES (?, 'credit', ?, 'Opening balance')
            """,
            (bank_id, float(data["initial_balance"])),
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


def delete_bank(conn, user_id, bank_id):
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


def create_bank_transaction(conn, bank_id, data):
    tx_type = data["transaction_type"]
    if tx_type not in BANK_TX_TYPES:
        raise ValueError("Invalid transaction type")
    cursor = conn.execute(
        """
        INSERT INTO bank_transactions (bank_account_id, transaction_type, amount, note)
        VALUES (?, ?, ?, ?)
        """,
        (bank_id, tx_type, float(data["amount"]), data.get("note", "")),
    )
    row = conn.execute(
        "SELECT * FROM bank_transactions WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def update_bank_transaction(conn, tx_id, data):
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
    return dict(row)


def delete_bank_transaction(conn, tx_id):
    conn.execute("DELETE FROM bank_transactions WHERE id = ?", (tx_id,))


def total_bank_balance(conn, user_id):
    banks = list_banks(conn, user_id)
    return round(sum(b["balance"] for b in banks), 2)


# --- Cash Book ---

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
    balance = 0.0
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
        else:
            d["balance"] = None
        d["payment_label"] = (
            f"Bank: {d['bank_name']}" if source == "bank" and d.get("bank_name")
            else "Cash"
        )
        entries.append(d)
    return list(reversed(entries))


def list_cash_book(conn, user_id):
    return _cash_book_running(conn, user_id)


def create_cash_book_entry(conn, user_id, data):
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
        acct = get_account(conn, user_id, account_id)
        if not acct:
            raise ValueError("Selected account not found")

    note = data.get("note", "")
    amount = float(data["amount"])
    entry_date = data.get("entry_date") or conn.execute("SELECT date('now')").fetchone()[0]

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

    if payment_source == "bank":
        create_bank_transaction(conn, bank_account_id, {
            "transaction_type": "credit" if entry_type == "in" else "debit",
            "amount": amount,
            "note": note or f"Cash book {entry_type} — entry #{entry_id}",
        })

    if account_id:
        acct_entry_type = "debit" if entry_type == "out" else "credit"
        acct_note = note or f"Cash book {entry_type} — entry #{entry_id}"
        create_entry(conn, account_id, {
            "entry_type": acct_entry_type,
            "amount": amount,
            "note": acct_note,
        })

    row = conn.execute(
        "SELECT * FROM cash_book_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    result = dict(row)
    if account_id:
        result["account_name"] = get_account(conn, user_id, account_id)["name"]
    if bank_account_id:
        result["bank_name"] = get_bank(conn, user_id, bank_account_id)["name"]
    result["payment_label"] = (
        f"Bank: {result['bank_name']}" if payment_source == "bank"
        else "Cash"
    )
    return result


def update_cash_book_entry(conn, user_id, entry_id, data):
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
    row = conn.execute(
        "SELECT * FROM cash_book_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return dict(row)


def delete_cash_book_entry(conn, user_id, entry_id):
    conn.execute(
        "DELETE FROM cash_book_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )


def cash_book_daily_summary(conn, user_id):
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
        ORDER BY entry_date DESC
        """,
        (user_id,),
    ).fetchall()
    summaries = []
    all_entries = conn.execute(
        """
        SELECT entry_date, entry_type, amount, payment_source
        FROM cash_book_entries
        WHERE user_id = ? AND COALESCE(payment_source, 'cash') = 'cash'
        ORDER BY entry_date ASC, created_at ASC, id ASC
        """,
        (user_id,),
    ).fetchall()
    daily_closing = {}
    bal = 0.0
    for e in all_entries:
        if e["entry_type"] == "in":
            bal += e["amount"]
        else:
            bal -= e["amount"]
        daily_closing[e["entry_date"]] = round(bal, 2)

    for r in rows:
        d = dict(r)
        d["closing_balance"] = daily_closing.get(d["entry_date"], 0)
        d["cash_in"] = round(d["cash_in"] or 0, 2)
        d["cash_out"] = round(d["cash_out"] or 0, 2)
        d["bank_in"] = round(d.get("bank_in") or 0, 2)
        d["bank_out"] = round(d.get("bank_out") or 0, 2)
        summaries.append(d)
    return summaries


def cash_in_hand_balance(conn, user_id):
    settings = get_user_settings(conn, user_id)
    manual = float(settings.get("cash_in_hand", 0))
    entries = _cash_book_running(conn, user_id)
    if entries:
        return entries[0]["balance"]
    return manual


# --- Dashboard ---

def compute_dashboard(conn, user_id):
    settings = get_user_settings(conn, user_id)
    partners = list_partners(conn, user_id)
    total_investment = sum(p["capital"] for p in partners)

    sold = conn.execute(
        """
        SELECT purchase_price, sale_price, receivable_amount FROM phones
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
        "SELECT payable_amount FROM phones WHERE payable_amount > 0 AND user_id = ?",
        (user_id,),
    ).fetchall()

    total_net_profit = sum(
        (r["sale_price"] or 0) - (r["purchase_price"] or 0) for r in sold
    )
    phone_receivables = sum(r["receivable_amount"] or 0 for r in sold)
    acct_summary = accounts_summary(conn, user_id)
    total_udhar = round(phone_receivables + acct_summary["total_receivable"], 2)
    accounts_payable = acct_summary["total_payable"]
    phone_payables = sum(r["payable_amount"] or 0 for r in payables)
    total_payables_combined = round(accounts_payable + phone_payables, 2)
    active_stock_worth = sum(r["purchase_price"] or 0 for r in inventory)

    total_in_bank = total_bank_balance(conn, user_id)
    total_in_cash = cash_in_hand_balance(conn, user_id)

    profit_reinvested = float(settings.get("profit_reinvested_total") or 0)
    available_profit = max(0.0, round(total_net_profit - profit_reinvested, 2))

    formula_expected = (
        total_investment + total_net_profit - total_udhar - active_stock_worth
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
        SELECT model, purchase_price, sale_price
        FROM phones
        WHERE status = 'Sold'
          AND sold_at IS NOT NULL
          AND user_id = ?
          AND strftime('%Y-%m', sold_at) = strftime('%Y-%m', 'now')
        """,
        (user_id,),
    ).fetchall()

    units_sold = len(rows)
    total_profit = sum((r["sale_price"] or 0) - (r["purchase_price"] or 0) for r in rows)
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


def account_to_dict(conn, row):
    d = dict(row)
    d["balance"] = _account_balance(conn, d["id"])
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
    cursor = conn.execute(
        "INSERT INTO accounts (name, contact, user_id) VALUES (?, ?, ?)",
        (data["name"], data.get("contact", ""), user_id),
    )
    return get_account(conn, user_id, cursor.lastrowid)


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


def delete_account(conn, user_id, account_id):
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

    if payment_source and payment_source not in ("cash", "bank"):
        raise ValueError("Payment source must be cash or bank")
    if entry_type == "credit" and payment_source:
        raise ValueError("Payment method applies only to Wasool (Payment) entries")
    if user_id and entry_type == "debit" and not payment_source:
        raise ValueError("Payment method is required for Wasool entries")
    if payment_source == "bank":
        if not bank_account_id:
            raise ValueError("Select a bank account")
        bank_account_id = int(bank_account_id)
        if user_id and not get_bank(conn, user_id, bank_account_id):
            raise ValueError("Bank account not found")

    cursor = conn.execute(
        """
        INSERT INTO account_entries (
            account_id, entry_type, amount, note, payment_source, bank_account_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            entry_type,
            amount,
            note,
            payment_source,
            bank_account_id if payment_source == "bank" else None,
        ),
    )
    entry_id = cursor.lastrowid

    if user_id and entry_type == "debit" and payment_source == "cash":
        acct = get_account(conn, user_id, account_id)
        acct_name = acct["name"] if acct else "Account"
        create_cash_book_entry(conn, user_id, {
            "entry_type": "in",
            "amount": amount,
            "note": note or f"Wasool — {acct_name}",
            "payment_source": "cash",
        })

    row = conn.execute(
        "SELECT * FROM account_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return dict(row)


def update_entry(conn, entry_id, data):
    existing = conn.execute(
        "SELECT * FROM account_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    if not existing:
        return None
    fields, values = [], []
    for field in ("entry_type", "amount", "note"):
        if field in data:
            fields.append(f"{field} = ?")
            val = data[field]
            if field == "amount":
                val = float(val)
            values.append(val)
    if fields:
        values.append(entry_id)
        conn.execute(
            f"UPDATE account_entries SET {', '.join(fields)} WHERE id = ?",
            values,
        )
    row = conn.execute(
        "SELECT * FROM account_entries WHERE id = ?", (entry_id,)
    ).fetchone()
    return dict(row)


def delete_entry(conn, entry_id):
    conn.execute("DELETE FROM account_entries WHERE id = ?", (entry_id,))


def accounts_summary(conn, user_id):
    accounts = list_accounts(conn, user_id)
    total_receivable = sum(a["balance"] for a in accounts if a["balance"] > 0)
    total_payable = sum(abs(a["balance"]) for a in accounts if a["balance"] < 0)
    return {
        "total_accounts": len(accounts),
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
    }


EXPENSE_CATEGORY_NAMES = (
    "Food", "Entertainment", "Transport", "Utilities", "Shop Expenses", "Other",
)


def seed_expense_accounts(conn, user_id):
    """Create default expense category accounts for cash book / journal use."""
    existing = {
        r["name"].lower()
        for r in conn.execute(
            "SELECT name FROM accounts WHERE user_id = ?", (user_id,)
        ).fetchall()
    }
    for name in EXPENSE_CATEGORY_NAMES:
        if name.lower() not in existing:
            create_account(conn, user_id, {"name": name, "contact": "Expense category"})


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

    voucher_date = data.get("voucher_date") or conn.execute("SELECT date('now')").fetchone()[0]
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
    create_entry(conn, debit_id, {"entry_type": "debit", "amount": amount, "note": note})
    create_entry(conn, credit_id, {"entry_type": "credit", "amount": amount, "note": note})

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
        SELECT id, model, sale_price, purchase_price, buyer_name, imei, sold_at
        FROM phones
        WHERE user_id = ? AND status = 'Sold' AND date(sold_at) = date('now')
        ORDER BY sold_at DESC
        """,
        (user_id,),
    ).fetchall()
    bought = conn.execute(
        """
        SELECT id, model, purchase_price, supplier_name, imei, purchase_date, created_at
        FROM phones
        WHERE user_id = ? AND status IN ('Bought', 'In Repair')
          AND (date(purchase_date) = date('now') OR date(created_at) = date('now'))
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    cash = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN entry_type = 'in' THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN entry_type = 'out' THEN amount ELSE 0 END), 0) AS cash_out
        FROM cash_book_entries
        WHERE user_id = ? AND entry_date = date('now')
        """,
        (user_id,),
    ).fetchone()
    revenue = sum((r["sale_price"] or 0) for r in sold)
    profit = sum((r["sale_price"] or 0) - (r["purchase_price"] or 0) for r in sold)
    return {
        "date_label": conn.execute(
            "SELECT strftime('%A, %d %B %Y', 'now') AS label"
        ).fetchone()["label"],
        "phones_sold": len(sold),
        "phones_bought": len(bought),
        "sales_revenue": round(revenue, 2),
        "sales_profit": round(profit, 2),
        "purchase_spend": round(sum((r["purchase_price"] or 0) for r in bought), 2),
        "cash_in": round(cash["cash_in"] or 0, 2),
        "cash_out": round(cash["cash_out"] or 0, 2),
        "sold_phones": [dict(r) for r in sold],
        "bought_phones": [dict(r) for r in bought],
    }


# --- Month report ---

def compute_month_report(conn, user_id, year_month=None):
    if not year_month:
        year_month = conn.execute(
            "SELECT strftime('%Y-%m', 'now') AS ym"
        ).fetchone()["ym"]

    sold = conn.execute(
        """
        SELECT model, purchase_price, sale_price, buyer_name, imei, sold_at
        FROM phones
        WHERE user_id = ? AND status = 'Sold' AND sold_at IS NOT NULL
          AND strftime('%Y-%m', sold_at) = ?
        ORDER BY sold_at DESC
        """,
        (user_id, year_month),
    ).fetchall()

    acct = accounts_summary(conn, user_id)
    dash = compute_dashboard(conn, user_id)
    revenue = sum((r["sale_price"] or 0) for r in sold)
    profit = sum((r["sale_price"] or 0) - (r["purchase_price"] or 0) for r in sold)
    month_label = conn.execute(
        "SELECT strftime('%B %Y', ? || '-01') AS label",
        (year_month,),
    ).fetchone()["label"]

    return {
        "year_month": year_month,
        "month_label": month_label,
        "units_sold": len(sold),
        "total_revenue": round(revenue, 2),
        "total_profit": round(profit, 2),
        "total_udhar": dash["total_udhar"],
        "total_receivable": acct["total_receivable"],
        "total_payable": acct["total_payable"],
        "sales": [dict(r) for r in sold],
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
    inv_num = data.get("invoice_number") or _next_invoice_number(conn, user_id)
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
            data.get("invoice_date") or conn.execute(
                "SELECT date('now')"
            ).fetchone()[0],
            user_id,
        ),
    )
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


def list_backup_files(conn, user_id):
    settings = get_storage_settings(conn, user_id)
    backup_dir = (settings.get("local_backup_path") or "").strip()
    if not backup_dir:
        return []
    path = Path(backup_dir)
    if not path.is_dir():
        return []
    files = sorted(
        {*path.glob("*_crm_backup_*.db"), *path.glob("crm_backup_*.db")},
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


def restore_database_from_backup(backup_path: str) -> str:
    src = Path(backup_path).expanduser().resolve()
    if not src.is_file():
        raise ValueError("Backup file not found")
    if src.suffix.lower() != ".db":
        raise ValueError("Please select a .db backup file")

    dest = DB_PATH.resolve()
    safety = dest.with_suffix(".db.pre_restore")
    if dest.is_file():
        shutil.copy2(dest, safety)
    shutil.copy2(src, dest)
    return str(safety) if safety.is_file() else ""
