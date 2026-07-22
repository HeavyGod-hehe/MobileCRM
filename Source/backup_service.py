"""Automatic and manual CRM database backups."""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

import database as db
from app_paths import customer_data_dir


def _log_path() -> Path | None:
    data_dir = customer_data_dir()
    if not data_dir:
        return None
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "crm.log"


def _log(message: str) -> None:
    """Same append-only Data/crm.log pattern launch_crm.py uses -- writes
    are a no-op when running from source (customer_data_dir() is None
    there), which is fine since dev runs already print to a real console."""
    path = _log_path()
    if not path:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def _snapshot_database(source_conn: sqlite3.Connection, dest_path: Path) -> None:
    """Write a consistent copy of the live database using SQLite's own backup
    API instead of copying the file — a raw file copy taken while the app is
    mid-write can capture a torn, unusable snapshot. sqlite3's backup() takes
    a proper read lock and is safe to run alongside concurrent writers."""
    if dest_path.exists():
        dest_path.unlink()
    backup_conn = sqlite3.connect(str(dest_path))
    try:
        source_conn.backup(backup_conn)
    finally:
        backup_conn.close()

BACKUP_INTERVAL_SECONDS = int(
    __import__("os").environ.get("CRM_BACKUP_INTERVAL_SECONDS", "3600")
)


def backup_user_data(user_id: int, *, force: bool = False) -> str | None:
    """Copy the SQLite database to the user's configured backup folder."""
    with db.db_session() as conn:
        db.ensure_user_backup_path(conn, user_id)
        settings = db.get_storage_settings(conn, user_id)
        if not force and not settings.get("auto_backup_enabled", True):
            return None
        backup_dir = (settings.get("local_backup_path") or "").strip()
        if not backup_dir:
            return None

        dest_dir = Path(backup_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        username = db.backup_username_slug(conn, user_id)
        dest = dest_dir / f"{username}_crm_backup_{stamp}.db"
        _snapshot_database(conn, dest)

        db.update_user_settings(conn, user_id, {
            "last_backup_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return str(dest)


def backup_all_users(*, force: bool = False) -> list[str]:
    """Run backup_user_data() for every account in this installation and
    return the paths that were actually written (skips users with no
    backup folder configured or with auto-backup turned off, unless
    force=True)."""
    created: list[str] = []
    with db.db_session() as conn:
        users = conn.execute("SELECT id FROM users").fetchall()
    for row in users:
        path = backup_user_data(row["id"], force=force)
        if path:
            created.append(path)
    return created


def list_backup_files(user_id: int) -> list[dict]:
    """List this user's saved backup files (for the Settings page's restore picker)."""
    with db.db_session() as conn:
        return db.list_backup_files(conn, user_id)


def restore_from_backup(user_id: int, backup_path: str) -> str:
    """Restore this user's own data from their backup copy. Returns path to
    the safety copy taken automatically before the restore."""
    return db.restore_database_from_backup(backup_path, user_id)


def run_startup_backups() -> list[str]:
    """Create Data/Backups on first run and save an immediate backup when possible."""
    try:
        with db.db_session() as conn:
            db.ensure_customer_data_layout(conn)
        return backup_all_users(force=True)
    except Exception:
        return []


def start_auto_backup_thread() -> None:
    """Background thread — backs up every hour when a backup path is configured."""

    def _loop() -> None:
        # Wait 30s before the first run so it doesn't slow down app startup.
        time.sleep(30)
        while True:
            try:
                backup_all_users()
            except Exception:
                pass
            time.sleep(BACKUP_INTERVAL_SECONDS)

    threading.Thread(target=_loop, daemon=True, name="crm-auto-backup").start()


def start_signup_backup_thread(user_id: int) -> threading.Thread:
    """Bug #20: the signup route used to call backup_user_data() directly
    on the request thread, so a slow disk (or, before it was fixed, any
    error the sync backup raised, which was never caught here) held up the
    signup response -- or made it fail outright even though the account
    was already created. Runs in the background instead so signup responds
    immediately; success/failure is written to Data/crm.log either way.
    Returns the Thread (callers don't need it -- app.py doesn't -- but
    tests can join() it to deterministically wait for completion)."""

    def _run() -> None:
        try:
            path = backup_user_data(user_id, force=True)
            if path:
                _log(f"Signup backup completed for user {user_id}: {path}")
            else:
                _log(f"Signup backup skipped for user {user_id} (no backup folder configured)")
        except Exception as exc:
            _log(f"Signup backup FAILED for user {user_id}: {exc}")

    thread = threading.Thread(target=_run, daemon=True, name="crm-signup-backup")
    thread.start()
    return thread
