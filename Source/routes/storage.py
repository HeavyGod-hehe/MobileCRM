"""Flask blueprint: Settings, backup, restore, storage paths."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session
import sqlite3
import subprocess
import sys
from pathlib import Path

import database as db
import backup_service
from app_helpers import (
    _current_user_id,
    _validate_logo_data_uri,
    _pick_folder_native,
    _pick_backup_file_native,
)

bp = Blueprint('storage', __name__)


@bp.route("/api/settings/shop", methods=["GET"])
def get_shop_settings_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        info = db.get_shop_info(conn, user_id)
        # cash_in_hand isn't part of get_shop_info() (that's invoice
        # letterhead data, also used when printing bills) -- read it
        # separately here so this Settings-only field doesn't leak into the
        # billing/purchase-invoice pages that reuse get_shop_info().
        settings = db.get_user_settings(conn, user_id)
        info["cash_in_hand"] = float(settings.get("cash_in_hand") or 0)
        return jsonify(info)



@bp.route("/api/settings/shop", methods=["PUT"])
def update_shop_settings_api():
    """Settings -> Shop Details: name/address/phones/WhatsApp, plus (if
    given) Cash in Hand - validated as a non-negative number before
    saving, since this is the one settings field that seeds a real money
    balance rather than just display text."""
    user_id = _current_user_id()
    data = request.get_json(force=True)
    payload = {
        "shop_name": data.get("shop_name", ""),
        "shop_address": data.get("shop_address", ""),
        "shop_phones": data.get("shop_phones", []),
        "shop_whatsapp": data.get("shop_whatsapp", ""),
    }
    if "cash_in_hand" in data:
        try:
            cash_in_hand = float(data.get("cash_in_hand"))
        except (TypeError, ValueError):
            return jsonify({"error": "Cash in Hand must be a number"}), 400
        if cash_in_hand < 0:
            return jsonify({"error": "Cash in Hand cannot be negative"}), 400
        payload["cash_in_hand"] = cash_in_hand
    with db.db_session() as conn:
        db.update_user_settings(conn, user_id, payload)
        info = db.get_shop_info(conn, user_id)
        settings = db.get_user_settings(conn, user_id)
        info["cash_in_hand"] = float(settings.get("cash_in_hand") or 0)
        return jsonify(info)


@bp.route("/api/settings/logo", methods=["PUT"])
def update_shop_logo_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    logo = data.get("shop_logo", "")
    if logo:
        try:
            _validate_logo_data_uri(logo)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
    with db.db_session() as conn:
        db.update_user_settings(conn, user_id, {"shop_logo": logo})
        return jsonify(db.get_shop_info(conn, user_id))



@bp.route("/api/settings/email", methods=["GET"])
def get_email_settings_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        cfg = db.get_email_settings(conn, user_id)
        settings = db.get_user_settings(conn, user_id)
        return jsonify({
            **cfg,
            "vendor_whatsapp": settings.get("vendor_whatsapp", ""),
            "vendor_support_note": settings.get("vendor_support_note", ""),
        })



@bp.route("/api/settings/email", methods=["PUT"])
def update_email_settings_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    payload = {
        "gmail_smtp_user": data.get("gmail_smtp_user", ""),
        "vendor_whatsapp": data.get("vendor_whatsapp", ""),
        "vendor_support_note": data.get("vendor_support_note", ""),
    }
    if data.get("gmail_smtp_app_password"):
        payload["gmail_smtp_app_password"] = data["gmail_smtp_app_password"]
    with db.db_session() as conn:
        db.update_user_settings(conn, user_id, payload)
        settings = db.get_user_settings(conn, user_id)
        return jsonify({
            **db.get_email_settings(conn, user_id),
            "vendor_whatsapp": settings.get("vendor_whatsapp", ""),
            "vendor_support_note": settings.get("vendor_support_note", ""),
        })



@bp.route("/api/settings/email/test", methods=["POST"])
def test_email_settings_api():
    """Send a real test email to the configured Gmail address, so the
    vendor can confirm the App Password works before relying on it during
    an actual password-reset request."""
    user_id = _current_user_id()
    with db.db_session() as conn:
        settings = db.get_user_settings(conn, user_id)
        gmail_user = settings.get("gmail_smtp_user", "")
        gmail_pass = settings.get("gmail_smtp_app_password", "")
        shop_name = settings.get("shop_name") or "Phone Reseller CRM"
    if not gmail_user or not gmail_pass:
        return jsonify({"error": "Save a Gmail address and App Password first"}), 400
    import email_service
    try:
        email_service.send_otp_email(
            gmail_user, "123456", smtp_user=gmail_user, smtp_password=gmail_pass, shop_name=shop_name,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "message": f"Test email sent to {gmail_user} — check your inbox."})



@bp.route("/api/settings", methods=["PUT"])
def update_settings():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            db.update_user_settings(conn, user_id, data)
            return jsonify(db.compute_dashboard(conn, user_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/storage/settings", methods=["GET"])
def get_storage_settings_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.get_storage_settings(conn, user_id))



@bp.route("/api/storage/settings", methods=["PUT"])
def update_storage_settings_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    with db.db_session() as conn:
        return jsonify(db.update_storage_settings(conn, user_id, data))



@bp.route("/api/storage/backup-now", methods=["POST"])
def backup_now_api():
    user_id = _current_user_id()
    import backup_service
    try:
        path = backup_service.backup_user_data(user_id, force=True)
    except OSError as exc:
        # This route called backup_user_data() with no error handling at
        # all - any OSError (e.g. the destination-filename collision fixed
        # in backup_user_data's own docstring, or a transient file-lock
        # from antivirus/another process) fell through as an unhandled 500
        # with no JSON body, which the frontend couldn't show a clean
        # message for. This was the closest thing in the app to the
        # reported "database is busy" symptom on the manual "Save Data
        # Now" button specifically.
        return jsonify({"error": f"Backup could not be saved right now — {exc}. Try again in a moment."}), 500
    if not path:
        return jsonify({"error": "Set a local backup folder in Settings first"}), 400
    with db.db_session() as conn:
        settings = db.get_storage_settings(conn, user_id)
    return jsonify({"ok": True, "path": path, **settings})



@bp.route("/api/storage/restore", methods=["POST"])
def restore_backup_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    backup_path = (data.get("backup_path") or "").strip()
    if not backup_path:
        return jsonify({"error": "Select a backup file to restore"}), 400
    import backup_service
    try:
        safety = backup_service.restore_from_backup(user_id, backup_path)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (OSError, sqlite3.Error) as e:
        return jsonify({"error": f"Restore could not complete right now — {e}. Try again in a moment."}), 500
    # The just-restored data doesn't follow on from whatever this user's
    # undo history was tracking before the restore - clear it so a stray
    # Undo click afterward can't quietly step back into a pre-restore state.
    db.clear_undo_history(user_id)
    session.clear()
    return jsonify({
        "ok": True,
        "message": "Database restored. Please sign in again.",
        "safety_copy": safety,
    })



@bp.route("/api/settings/reset-crm", methods=["POST"])
def reset_crm_api():
    """Danger Zone -> Reset CRM: wipes this user's business data entirely
    and sends them back through the Setup Wizard. Requires the literal
    string "RESET" in the request body as a server-side confirmation gate,
    not just the frontend's type-to-confirm modal - a defense-in-depth
    check against anything that might call this endpoint directly."""
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True)
    if (data.get("confirm") or "") != "RESET":
        return jsonify({"error": "Type RESET to confirm"}), 400
    try:
        with db.db_session() as conn:
            safety = db.reset_user_data(conn, user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (OSError, sqlite3.Error) as e:
        return jsonify({"error": f"Reset could not complete right now — {e}. Try again in a moment."}), 500
    session.clear()
    return jsonify({
        "ok": True,
        "message": "CRM reset. Please sign in again to go through setup.",
        "safety_copy": safety,
    })



@bp.route("/api/storage/browse-backup-file", methods=["POST"])
def browse_backup_file_api():
    """Open native file picker to choose a .db backup for restore."""
    if sys.platform in ("darwin", "win32") or not getattr(sys, "frozen", False):
        try:
            path = _pick_backup_file_native()
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"error": "File picker timed out"}), 408
        if not path:
            return jsonify({"cancelled": True})
        return jsonify({"path": path})

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        picker_name = "FolderPicker.exe" if sys.platform == "win32" else "FolderPicker"
        picker = exe_dir / picker_name
        if not picker.is_file():
            picker = Path(sys._MEIPASS) / "folder_picker.py"
    else:
        picker = Path(__file__).parent / "folder_picker.py"

    cmd = ([sys.executable, str(picker), "--file"]
           if picker.suffix.lower() == ".py" else [str(picker), "--file"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "File picker timed out"}), 408
    except OSError as e:
        return jsonify({"error": f"Could not launch file picker: {e}"}), 500

    path = (result.stdout or "").strip()
    if not path:
        if result.returncode not in (0, 1):
            err = (result.stderr or "").strip()
            return jsonify({"error": err or "File picker failed"}), 500
        return jsonify({"cancelled": True})
    return jsonify({"path": path})



@bp.route("/api/storage/browse-folder", methods=["POST"])
def browse_folder_api():
    """Open native OS folder picker in-process (no separate helper exe required)."""
    if sys.platform in ("darwin", "win32") or not getattr(sys, "frozen", False):
        try:
            path = _pick_folder_native()
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Folder picker timed out"}), 408
        if not path:
            return jsonify({"cancelled": True})
        return jsonify({"path": path})

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        picker_name = "FolderPicker.exe" if sys.platform == "win32" else "FolderPicker"
        picker = exe_dir / picker_name
        if not picker.is_file():
            picker = Path(sys._MEIPASS) / "folder_picker.py"
    else:
        picker = Path(__file__).parent / "folder_picker.py"

    cmd = [sys.executable, str(picker)] if picker.suffix.lower() == ".py" else [str(picker)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Folder picker timed out"}), 408
    except OSError as e:
        return jsonify({"error": f"Could not launch folder picker: {e}"}), 500

    if result.returncode == 2:
        return jsonify({"error": "Folder picker is not available on this system"}), 501

    path = (result.stdout or "").strip()
    if not path:
        if result.returncode not in (0, 1):
            err = (result.stderr or "").strip()
            return jsonify({"error": err or "Folder picker failed"}), 500
        return jsonify({"cancelled": True})
    return jsonify({"path": path})


# --- Partners ---
# Business partners who share ownership/investment in the shop - tracks
# each partner's invested amount and profit reinvestment/withdrawals
# separately from regular customer/supplier accounts.


@bp.route("/api/backup/export")
def backup_export():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.export_all_data(conn, user_id))
