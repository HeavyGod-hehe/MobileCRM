"""Automatic and manual CRM database backups."""

from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

import database as db

BACKUP_INTERVAL_SECONDS = int(
    __import__("os").environ.get("CRM_BACKUP_INTERVAL_SECONDS", "3600")
)


def backup_user_data(user_id: int, *, force: bool = False) -> str | None:
    """Copy the SQLite database to the user's configured backup folder."""
    with db.db_session() as conn:
        settings = db.get_storage_settings(conn, user_id)
        if not force and not settings.get("auto_backup_enabled", True):
            return None
        backup_dir = (settings.get("local_backup_path") or "").strip()
        if not backup_dir:
            return None

        dest_dir = Path(backup_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = dest_dir / f"crm_backup_{stamp}.db"
        shutil.copy2(db.DB_PATH, dest)

        db.update_user_settings(conn, user_id, {
            "last_backup_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        return str(dest)


def backup_all_users() -> list[str]:
    created: list[str] = []
    with db.db_session() as conn:
        users = conn.execute("SELECT id FROM users").fetchall()
    for row in users:
        path = backup_user_data(row["id"])
        if path:
            created.append(path)
    return created


def list_backup_files(user_id: int) -> list[dict]:
    with db.db_session() as conn:
        return db.list_backup_files(conn, user_id)


def restore_from_backup(backup_path: str) -> str:
    """Replace live database with a backup copy. Returns path to safety copy."""
    return db.restore_database_from_backup(backup_path)


def start_auto_backup_thread() -> None:
    """Background thread — backs up every hour when a backup path is configured."""

    def _loop() -> None:
        time.sleep(30)
        while True:
            try:
                backup_all_users()
            except Exception:
                pass
            time.sleep(BACKUP_INTERVAL_SECONDS)

    threading.Thread(target=_loop, daemon=True, name="crm-auto-backup").start()
