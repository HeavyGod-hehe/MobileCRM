"""Flask blueprint: Signup, login, password reset, activation page helpers."""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
import sqlite3

import database as db
import license_guard as lic
import backup_service
from app_helpers import (
    _current_user_id,
)

bp = Blueprint('auth', __name__)

import backup_service

@bp.route("/activate")
def activation_page():
    return render_template("activation.html", hardware_id=lic.get_hardware_id())



@bp.route("/login")
def login_page():
    return render_template("login.html")



@bp.route("/api/auth/status")
def auth_status():
    show_welcome = session.pop("show_welcome", False)
    user_id = _current_user_id()
    with db.db_session() as conn:
        config = db.get_auth_config(conn, user_id) if user_id else db.get_auth_config(conn)
    return jsonify({
        **config,
        "logged_in": bool(session.get("logged_in")),
        "session_username": session.get("username"),
        "show_welcome": show_welcome,
    })



@bp.route("/api/auth/signup", methods=["POST"])
def auth_signup():
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            user = db.register_user(
                conn,
                data.get("username", "").strip(),
                data.get("password", ""),
                data.get("email", "").strip(),
                data.get("shop_name", "").strip(),
            )
        session["logged_in"] = True
        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["show_welcome"] = True
        import backup_service
        backup_service.start_signup_backup_thread(user["user_id"])
        return jsonify({"ok": True, **user})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except sqlite3.Error as e:
        # register_user() only ever had ValueError caught here - a real
        # "database is locked"/OperationalError (SQLite lock contention,
        # most likely from a background backup or migration holding a
        # write lock) fell through as an unhandled 500 with no JSON body,
        # which the customer would have experienced as signup just hanging
        # or failing with no explanation. get_connection() already uses a
        # generous 30s busy_timeout + WAL mode so genuine lock contention
        # should be rare and self-resolving, but if it ever does happen
        # this at least surfaces a clean, retryable message instead of a
        # raw crash.
        return jsonify({"error": f"Couldn't create your account right now — {e}. Please try again."}), 500



@bp.route("/api/auth/forgot-password", methods=["POST"])
def auth_forgot_password():
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            result = db.request_password_reset(conn, data.get("email", "").strip())
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400



@bp.route("/api/auth/reset-password", methods=["POST"])
def auth_reset_password():
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            result = db.verify_otp_and_reset_password(
                conn,
                data.get("email", "").strip(),
                data.get("otp", "").strip(),
                data.get("new_password", ""),
            )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400



@bp.route("/api/auth/reset-password-hwid", methods=["POST"])
def auth_reset_password_hwid():
    """Vendor-assisted recovery for accounts with no email/OTP configured -
    see db.reset_password_with_hwid_code for how the code is verified."""
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            result = db.reset_password_with_hwid_code(
                conn,
                data.get("username", ""),
                data.get("code", ""),
                data.get("new_password", ""),
            )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400



@bp.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True)
    with db.db_session() as conn:
        if not db.auth_is_configured(conn):
            return jsonify({"error": "No accounts available"}), 400
        user = db.verify_login(conn, data.get("username", "").strip(), data.get("password", ""))
        if not user:
            return jsonify({"error": "Invalid username or password"}), 401
    session["logged_in"] = True
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["show_welcome"] = True
    return jsonify({"ok": True, **user})



@bp.route("/api/auth/settings", methods=["PUT"])
def auth_settings():
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            config = db.update_auth_credentials(conn, user_id, data)
        if data.get("username"):
            session["username"] = data["username"]
        return jsonify(config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400



@bp.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("auth.login_page"))


# --- Pages ---
# These just render an HTML template - no data is loaded here. Each page's
# JavaScript (loaded by templates/base.html) calls the matching "/api/..."
# routes further down to fetch the real data after the page loads.
