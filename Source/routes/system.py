"""Flask blueprint: Undo/redo, license, updates, shutdown."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session
import sqlite3
import os
import threading

import database as db
import license_guard as lic
import update_service as updates
from app_helpers import (
    APP_VERSION,
    _current_user_id,
)

bp = Blueprint('system', __name__)

@bp.route("/api/undo/status")
def undo_status_api():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(db.get_undo_status(user_id))



@bp.route("/api/undo", methods=["POST"])
def undo_api():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify(db.perform_undo(user_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (OSError, sqlite3.Error) as e:
        # perform_undo/perform_redo do real file + database I/O
        # (_restore_user_rows_from_file) - only ValueError was ever caught
        # here, so a transient file/db issue (locked by antivirus, a
        # momentary sharing violation) fell through as an unhandled 500
        # with no JSON body. Same class of bug as backup_now_api.
        return jsonify({"error": f"Undo could not complete right now — {e}. Try again in a moment."}), 500



@bp.route("/api/redo", methods=["POST"])
def redo_api():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify(db.perform_redo(user_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except (OSError, sqlite3.Error) as e:
        return jsonify({"error": f"Redo could not complete right now — {e}. Try again in a moment."}), 500


# --- License ---
# Routes for the one-time activation screen (see templates/activation.html
# and license_guard.py). "shutdown_system" also lives here since it needs
# to be reachable from the app's UI without being blocked by license/auth.


@bp.route("/api/license/status")
def license_status():
    return jsonify({
        "licensed": lic.is_licensed(),
        "hardware_id": lic.get_hardware_id(),
    })



@bp.route("/api/license/activate", methods=["POST"])
def license_activate():
    data = request.get_json(force=True)
    key = (data.get("activation_key") or "").strip()
    try:
        lic.save_license(key)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400



@bp.route("/api/system/shutdown", methods=["POST"])
def shutdown_system():
    if not session.get("logged_in") or not session.get("user_id"):
        return jsonify({"error": "Unauthorized"}), 401

    def _shutdown() -> None:
        os._exit(0)

    import threading

    threading.Timer(0.3, _shutdown).start()
    return jsonify({"ok": True, "message": "CRM is closing..."})


# --- Auth ---
# Login/signup/password-reset routes. Passwords are never stored in plain
# text - see database.py's register_user/verify_login for the hashing.
# Password reset uses a one-time code (OTP) emailed to the shop owner via
# email_service.py.


@bp.route("/api/update/check")
def update_check_api():
    """Compare local VERSION with remote manifest (version.json) or legacy VERSION file."""
    return jsonify(updates.check_for_updates())



@bp.route("/api/update/status")
def update_status_api():
    return jsonify(updates.get_update_state())



@bp.route("/api/update/install", methods=["POST"])
def update_install_api():
    if not session.get("logged_in") or not session.get("user_id"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(updates.start_install(data.get("download_url")))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500



@bp.route("/api/app/version")
def app_version_api():
    return jsonify({"version": APP_VERSION or updates.get_current_version()})


# --- Returns ---
# A "return" reverses part or all of a purchase or sale (customer brings a
# phone back). This posts an opposite ledger/cash-book entry rather than
# deleting the original, so the history stays visible - see database.py's
# process_purchase_return / process_sale_return.
