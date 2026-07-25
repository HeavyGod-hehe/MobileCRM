"""Shared helpers for Flask routes / blueprints (no app object required)."""
from __future__ import annotations

import base64
import binascii
import os
import re
import subprocess
import sys
from pathlib import Path

from flask import jsonify, session

import database as db


_VERSION_FILE = Path(__file__).parent / "VERSION"
if getattr(sys, "frozen", False):
    try:
        APP_VERSION = (Path(sys._MEIPASS) / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        APP_VERSION = ""
else:
    APP_VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip() if _VERSION_FILE.is_file() else ""

PHONE_STATUSES = db.PHONE_STATUSES
ENTRY_TYPES = db.ENTRY_TYPES

_LOGO_DATA_URI_RE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,(.+)$", re.DOTALL)
_LOGO_MAX_BYTES = 300 * 1024
_LOGO_MAGIC_BYTES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
)


def _current_user_id():
    """Return the logged-in shop owner's user id, or None if nobody is logged in.

    Every table that stores shop data (phones, accounts, cash book, ...) has
    a user_id column, so one CRM installation could technically serve more
    than one shop owner without their data mixing - this is how routes know
    whose data to read/write.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


def _display_name():
    """Human-readable name for titles and headers."""
    username = session.get("username") or "User"
    return username.replace("_", " ").replace("-", " ").title()


def _validate_status(status):
    if status not in PHONE_STATUSES:
        return f"Status must be one of: {', '.join(PHONE_STATUSES)}"
    return None


def _validate_entry_type(entry_type):
    if entry_type not in ENTRY_TYPES:
        return "Entry type must be credit or debit"
    return None


def _negative_balance_response(w):
    """Shared 409 response shape for db.NegativeBalanceWarning (bug #11) --
    lets the frontend show a confirm dialog ("this would take Cash to
    -500, proceed?") and resubmit the same request with force: true,
    instead of a plain error toast."""
    return jsonify({
        "error": str(w), "requires_confirmation": True,
        "target": w.target, "current_balance": w.current_balance,
        "amount": w.amount, "resulting_balance": w.resulting_balance,
    }), 409


def _require_amount(data, field="amount"):
    """Parse amount; rejects missing/blank/negative values. Zero is allowed only for balances, not here."""
    if field not in data or data[field] is None:
        return None, "Amount is required"
    text = str(data[field]).strip()
    if text == "":
        return None, "Amount is required"
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None, "Amount must be a number"
    if value <= 0:
        return None, "Amount must be greater than zero"
    return value, None


def _validate_logo_data_uri(raw: str) -> None:
    match = _LOGO_DATA_URI_RE.match(raw or "")
    if not match:
        raise ValueError("That doesn't look like an image file.")
    try:
        decoded = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("That image file looks corrupted — try a different one.")
    if len(decoded) > _LOGO_MAX_BYTES:
        raise ValueError("Logo is too large — please use an image under 300KB.")
    is_webp = decoded[:4] == b"RIFF" and decoded[8:12] == b"WEBP"
    if not is_webp and not any(decoded.startswith(magic) for magic in _LOGO_MAGIC_BYTES):
        raise ValueError("That doesn't look like a valid image file.")


def _pick_folder_native():
    if sys.platform == "darwin":
        from folder_picker import pick_folder_macos
        return pick_folder_macos()
    if sys.platform == "win32":
        from folder_picker import pick_folder_windows
        try:
            return pick_folder_windows()
        except Exception:
            from folder_picker import pick_folder_tkinter
            return pick_folder_tkinter()
    from folder_picker import pick_folder_tkinter
    return pick_folder_tkinter()


def _pick_backup_file_native():
    if sys.platform == "darwin":
        from folder_picker import pick_file_macos
        return pick_file_macos()
    from folder_picker import pick_backup_file
    return pick_backup_file()


def _get_owned_bank_transaction(conn, user_id, bank_id, tx_id):
    """Verify the bank belongs to this user AND the transaction belongs to
    that bank, before any edit/delete — otherwise a user could act on another
    user's transaction just by guessing an id in the URL."""
    if not db.get_bank(conn, user_id, bank_id):
        return None
    return conn.execute(
        "SELECT id FROM bank_transactions WHERE id = ? AND bank_account_id = ?",
        (tx_id, bank_id),
    ).fetchone()
