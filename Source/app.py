"""Phone Reseller CRM - main web application.

BEGINNER'S MAP OF THIS FILE
----------------------------
This is a Flask app: a Python web server that serves HTML pages (the CRM's
screens, in templates/*.html) and a JSON "API" that those pages call with
JavaScript (static/ui.js) to load and save data - phones, ledger entries,
cash book, etc.

Every browser request that comes in passes through, in order:
  1. ensure_db()       - makes sure the SQLite database file is open and
                          migrated to the latest schema before anything else
                          runs (see database.py for the actual schema).
  2. require_license()  - blocks all pages/API calls until the shop owner has
                          entered a valid activation key (see license_guard.py).
  3. require_auth()     - blocks all pages/API calls until someone is logged
                          in (or, on first run, redirects to account setup).
These are Flask "before_request" hooks below - they run automatically before
every route function, so individual routes don't need to repeat these checks.

After that, routes fall into two kinds:
  - Page routes (no "/api/" prefix) - render an HTML template, e.g. "/inventory"
    renders templates/inventory.html. The page itself is mostly empty; the
    real data is fetched by JavaScript calling the API routes below.
  - API routes (prefixed "/api/...") - read/write data as JSON. These call
    into database.py, which owns all the actual business logic (creating a
    sale, syncing the cash book, etc.) - this file's job is just to validate
    the incoming request and translate between HTTP and database.py's
    plain Python functions.

The file is organized into sections marked with "# --- Section Name ---"
comments (License, Auth, Pages, Phones, Accounts, Cash Book, ...) - search
for "# ---" to jump between them.

Business-term glossary (this is a Pakistani phone reseller CRM, so some
names use Urdu/local shop terms):
  - "khata"  = the customer/supplier running account (a ledger of who owes
    the shop money, and who the shop owes money to).
  - "udhar"  = money owed on credit (not yet paid).
  - "wasool" = a payment collected from a customer (reduces what they owe).
  - "ledger_links" (in database.py) = the glue table that keeps a phone
    sale/purchase, its cash book entry, and its account entry all pointing
    at each other, so deleting/editing one correctly reverses the others.
"""

import base64
import binascii
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import database as db
import license_guard as lic
import update_service as updates

if getattr(sys, "frozen", False):
    _BASE = Path(sys._MEIPASS)
    app = Flask(
        __name__,
        template_folder=str(_BASE / "templates"),
        static_folder=str(_BASE / "static"),
    )
else:
    app = Flask(__name__)

def _load_or_create_secret_key() -> str:
    """A hardcoded Flask secret_key meant every customer build shipped the
    exact same session-signing key -- anyone who decompiled/grepped one
    customer's .exe could forge a valid session cookie for every other
    installation. Generate a random key per installation on first run
    instead, and persist it next to that installation's own database (so
    later launches reuse the same key -- sessions survive a normal restart,
    just not a fresh reinstall/wipe of the Data folder). CRM_SECRET_KEY is
    kept only as a deterministic override for the test suite, never as a
    fallback a real customer build silently ships with."""
    env_key = os.environ.get("CRM_SECRET_KEY")
    if env_key:
        return env_key

    key_path = db.DB_PATH.parent / "secret_key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.is_file():
        existing = key_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    new_key = secrets.token_hex(32)
    # Write to a temp file and rename into place, same pattern as
    # license_guard.save_license() -- a crash mid-write can't leave a
    # half-written key file this way (rename is atomic).
    tmp_path = key_path.with_suffix(".tmp")
    tmp_path.write_text(new_key, encoding="utf-8")
    try:
        os.chmod(tmp_path, 0o600)
    except OSError:
        pass
    tmp_path.replace(key_path)
    return new_key


app.secret_key = _load_or_create_secret_key()

# Bug #22: no CSRF protection anywhere in this app (no token on forms/API
# writes). Accepted as-is because the server only ever binds to
# 127.0.0.1/localhost by default (see CRM_HOST below) -- a page on another
# origin can't reach a service that isn't reachable from the network in
# the first place. This stops being true the moment CRM_HOST is set to a
# non-loopback address (see the warning logged for that case below); if
# LAN/remote access is ever supported as a real feature, CSRF tokens need
# to be added before that ships, not left as a known gap.

APP_VERSION = (Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip() if not getattr(sys, "frozen", False) else ""
if getattr(sys, "frozen", False):
    _ver_path = Path(sys._MEIPASS) / "VERSION"
    APP_VERSION = _ver_path.read_text(encoding="utf-8").strip() if _ver_path.is_file() else "1.0.0"

PHONE_STATUSES = db.PHONE_STATUSES
ENTRY_TYPES = db.ENTRY_TYPES

_DB_READY = False
_DB_ERROR = None
_DB_INIT_LOCK = threading.Lock()

AUTH_EXEMPT_ENDPOINTS = frozenset({
    "login_page", "auth_status", "auth_login", "auth_signup",
    "auth_forgot_password", "auth_reset_password", "auth_vendor_reset_info", "static",
    "activation_page", "license_status", "license_activate",
})

LICENSE_EXEMPT_ENDPOINTS = frozenset({
    "activation_page", "license_status", "license_activate", "static",
})


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


@app.context_processor
def inject_user_context():
    shop_name = "My Phone Shop"
    user_id = session.get("user_id")
    if user_id:
        try:
            with db.db_session() as conn:
                config = db.get_auth_config(conn, user_id)
                shop_name = (config.get("shop_name") or shop_name).strip() or shop_name
        except Exception:
            pass
    return {
        "current_username": _display_name(),
        "session_username": session.get("username"),
        "shop_name": shop_name,
    }


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


_DB_ERROR_HTML = """
<!doctype html><html><head><title>Database problem</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:2rem}}
.box{{max-width:560px;background:#1e293b;border-radius:12px;padding:2rem;
border:1px solid rgba(248,113,113,0.3)}}
h1{{color:#f87171;font-size:1.25rem;margin-top:0}}
code{{background:#0f172a;padding:0.15rem 0.4rem;border-radius:4px;word-break:break-all}}
</style></head><body><div class="box">
<h1>Your database file couldn't be opened</h1>
<p>The CRM's data file appears to be damaged or unreadable:</p>
<p><code>{detail}</code></p>
<p>Your data has <strong>not</strong> been deleted or overwritten — only the file
at <code>{db_path}</code> could not be read.</p>
<p><strong>What to do:</strong> go to your Backups folder and restore the most
recent backup file (Settings &rarr; Storage &amp; Backups, or find the
<code>Backups</code> folder next to the app), then reopen the CRM.</p>
</div></body></html>
"""


@app.before_request
def ensure_db():
    global _DB_READY, _DB_ERROR
    if _DB_ERROR:
        return _DB_ERROR_HTML.format(detail=_DB_ERROR, db_path=db.DB_PATH), 500
    if _DB_READY:
        return
    # Flask runs threaded, so several requests can land here at once on
    # first launch (index page + its static assets). Without this lock,
    # multiple threads called db.init_db() concurrently, and one of the
    # migration steps would collide with another's open transaction,
    # raising "database is locked" — which then got cached as a permanent
    # _DB_ERROR, breaking the app for the rest of the process's life even
    # though the actual lock was transient. Serializing here fixes both:
    # only one thread actually runs init_db(), and a transient lock error
    # (if one still occurs, e.g. another process touching the file) is not
    # treated as permanent corruption.
    with _DB_INIT_LOCK:
        if _DB_READY:
            return
        try:
            db.init_db()
        except sqlite3.OperationalError:
            # Transient (e.g. "database is locked") — don't cache this as
            # permanent, and don't let the request fall through to a view
            # that also needs a ready database. Ask the browser to retry.
            return "Starting up, please retry…", 503
        except sqlite3.DatabaseError as exc:
            _DB_ERROR = str(exc)
            return _DB_ERROR_HTML.format(detail=_DB_ERROR, db_path=db.DB_PATH), 500
        _DB_READY = True


@app.before_request
def require_license():
    """Block every page/API call until this machine has a valid activation key.

    Runs before EVERY request (Flask before_request). See license_guard.py
    for how the key is checked - it's tied to a stable per-machine ID, not
    the network MAC address, so it stays valid across reboots/Wi-Fi changes.
    CRM_SKIP_LICENSE=1 exists only for automated tests, never for real use.
    """
    if os.environ.get("CRM_SKIP_LICENSE") == "1":
        return
    if request.path.startswith("/static/"):
        return
    endpoint = request.endpoint or ""
    if endpoint in LICENSE_EXEMPT_ENDPOINTS:
        return
    if lic.is_licensed():
        return
    if request.path.startswith("/api/"):
        return jsonify({"error": "Activation required", "needs_activation": True}), 403
    return redirect(url_for("activation_page"))


@app.before_request
def require_auth():
    """Block pages/API calls until someone is logged in.

    Two cases:
      - No account exists yet at all (fresh install) -> everyone gets sent
        to the signup/login page so the shop owner can create the first
        account.
      - An account exists but this browser session isn't logged in -> send
        to the login page.
    AUTH_EXEMPT_ENDPOINTS (login, signup, password reset, activation, static
    files) are allowed through without being logged in, since you obviously
    can't log in on a page that itself requires being logged in.
    """
    if request.path.startswith("/static/"):
        return
    endpoint = request.endpoint or ""
    if endpoint in AUTH_EXEMPT_ENDPOINTS:
        return

    with db.db_session() as conn:
        configured = db.auth_is_configured(conn)

    if not configured:
        if endpoint == "login_page":
            return
        if request.path.startswith("/api/auth"):
            return
        if request.path.startswith("/api/"):
            return jsonify({"error": "Setup required", "needs_setup": True}), 401
        return redirect(url_for("login_page"))

    if not session.get("logged_in") or not session.get("user_id"):
        if endpoint == "login_page":
            return redirect(url_for("today_page"))
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("login_page"))


# --- License ---
# Routes for the one-time activation screen (see templates/activation.html
# and license_guard.py). "shutdown_system" also lives here since it needs
# to be reachable from the app's UI without being blocked by license/auth.

@app.route("/activate")
def activation_page():
    return render_template("activation.html", hardware_id=lic.get_hardware_id())


@app.route("/api/license/status")
def license_status():
    return jsonify({
        "licensed": lic.is_licensed(),
        "hardware_id": lic.get_hardware_id(),
    })


@app.route("/api/license/activate", methods=["POST"])
def license_activate():
    data = request.get_json(force=True)
    key = (data.get("activation_key") or "").strip()
    try:
        lic.save_license(key)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/system/shutdown", methods=["POST"])
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

@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/api/auth/status")
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


@app.route("/api/auth/signup", methods=["POST"])
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


@app.route("/api/auth/forgot-password", methods=["POST"])
def auth_forgot_password():
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            result = db.request_password_reset(conn, data.get("email", "").strip())
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/auth/reset-password", methods=["POST"])
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


@app.route("/api/auth/vendor-reset-info")
def auth_vendor_reset_info():
    with db.db_session() as conn:
        return jsonify(db.get_vendor_reset_info(conn))


@app.route("/api/auth/login", methods=["POST"])
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


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/settings", methods=["PUT"])
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


@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("login_page"))


# --- Pages ---
# These just render an HTML template - no data is loaded here. Each page's
# JavaScript (loaded by templates/base.html) calls the matching "/api/..."
# routes further down to fetch the real data after the page loads.

@app.route("/")
def today_page():
    return render_template("today.html")


@app.route("/inventory")
def inventory():
    return render_template("inventory.html")


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.route("/month-report")
def month_report_page():
    return render_template("month_report.html")


@app.route("/accounts")
def accounts_page():
    return render_template("accounts.html")


@app.route("/overview")
def overview_page():
    return render_template("overview.html")


@app.route("/cashbook")
def cashbook_page():
    return render_template("cashbook.html")


@app.route("/journal")
def journal_page():
    return render_template("journal.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/returns")
def returns_page():
    return render_template("returns.html")


@app.route("/billing")
def billing_page():
    return render_template("billing.html")


@app.route("/purchase-invoice")
def purchase_invoice_page():
    return render_template("purchase_invoice.html")


@app.route("/api/settings/shop", methods=["GET"])
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


@app.route("/api/settings/shop", methods=["PUT"])
def update_shop_settings_api():
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


_LOGO_DATA_URI_RE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,(.+)$", re.DOTALL)
_LOGO_MAX_BYTES = 300 * 1024
_LOGO_MAGIC_BYTES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
)


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


@app.route("/api/settings/logo", methods=["PUT"])
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


@app.route("/api/today")
def today_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.compute_today_summary(conn, user_id))


@app.route("/api/month-report")
def month_report_api():
    user_id = _current_user_id()
    year_month = request.args.get("month")
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    with db.db_session() as conn:
        return jsonify(db.compute_month_report(conn, user_id, year_month, start_date, end_date))


@app.route("/api/settings/email", methods=["GET"])
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


@app.route("/api/settings/email", methods=["PUT"])
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


@app.route("/api/settings/email/test", methods=["POST"])
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


@app.route("/api/update/check")
def update_check_api():
    """Compare local VERSION with remote manifest (version.json) or legacy VERSION file."""
    return jsonify(updates.check_for_updates())


@app.route("/api/update/status")
def update_status_api():
    return jsonify(updates.get_update_state())


@app.route("/api/update/install", methods=["POST"])
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


@app.route("/api/app/version")
def app_version_api():
    return jsonify({"version": APP_VERSION or updates.get_current_version()})


# --- Returns ---
# A "return" reverses part or all of a purchase or sale (customer brings a
# phone back). This posts an opposite ledger/cash-book entry rather than
# deleting the original, so the history stays visible - see database.py's
# process_purchase_return / process_sale_return.

@app.route("/api/returns", methods=["GET"])
def list_returns_api():
    user_id = _current_user_id()
    return_type = request.args.get("type")
    with db.db_session() as conn:
        return jsonify(db.list_return_logs(conn, user_id, return_type))


@app.route("/api/returns/purchase", methods=["POST"])
def process_purchase_return_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            return jsonify(db.process_purchase_return(conn, user_id, data)), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/returns/sale", methods=["POST"])
def process_sale_return_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            return jsonify(db.process_sale_return(conn, user_id, data)), 201
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/returns/inventory/purchase")
def purchase_return_inventory_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_phones_for_purchase_return(conn, user_id))


@app.route("/api/returns/inventory/sale")
def sale_return_inventory_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_phones_for_sale_return(conn, user_id))


# --- Billing ---
# Sale invoices for printing/WhatsApp (static/whatsapp.js). Invoices are
# print-only records here - the actual sale/inventory change already
# happened through the Phones API; billing just formats a receipt for it.

@app.route("/api/billing/inventory")
def billing_inventory_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        settings = db.get_user_settings(conn, user_id)
        counter = int(settings.get("invoice_counter") or 1000)
        max_row = conn.execute(
            "SELECT MAX(invoice_number) AS m FROM invoices WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        next_num = max(counter, (max_row["m"] or 0) + 1)
        return jsonify({
            "inventory": db.list_phones_for_billing(conn, user_id),
            "shop": db.get_shop_info(conn, user_id),
            "next_invoice_number": next_num,
        })


@app.route("/api/billing/invoices", methods=["GET"])
def list_invoices_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        settings = db.get_user_settings(conn, user_id)
        counter = int(settings.get("invoice_counter") or 1000)
        max_row = conn.execute(
            "SELECT MAX(invoice_number) AS m FROM invoices WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        next_num = max(counter, (max_row["m"] or 0) + 1)
        return jsonify({
            "invoices": db.list_invoices(conn, user_id),
            "next_invoice_number": next_num,
        })


@app.route("/api/billing/invoices", methods=["POST"])
def create_invoice_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            invoice = db.create_invoice(conn, user_id, data)
            return jsonify(invoice), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/billing/phone/<int:phone_id>")
def billing_phone_api(phone_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        phone = db.get_phone(conn, user_id, phone_id)
        if not phone:
            return jsonify({"error": "Phone not found"}), 404
        return jsonify(phone)


# --- Purchase Invoices ---
# Same idea as Billing, but for what the shop bought (from suppliers)
# instead of what it sold.

@app.route("/api/purchase-invoice/inventory")
def purchase_invoice_inventory_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        settings = db.get_user_settings(conn, user_id)
        counter = int(settings.get("purchase_invoice_counter") or 1000)
        max_row = conn.execute(
            "SELECT MAX(invoice_number) AS m FROM purchase_invoices WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        next_num = max(counter, (max_row["m"] or 0) + 1)
        return jsonify({
            "inventory": db.list_phones_for_purchase_return(conn, user_id),
            "shop": db.get_shop_info(conn, user_id),
            "next_invoice_number": next_num,
        })


@app.route("/api/purchase-invoice/invoices", methods=["GET"])
def list_purchase_invoices_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        settings = db.get_user_settings(conn, user_id)
        counter = int(settings.get("purchase_invoice_counter") or 1000)
        max_row = conn.execute(
            "SELECT MAX(invoice_number) AS m FROM purchase_invoices WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        next_num = max(counter, (max_row["m"] or 0) + 1)
        return jsonify({
            "invoices": db.list_purchase_invoices(conn, user_id),
            "next_invoice_number": next_num,
        })


@app.route("/api/purchase-invoice/invoices", methods=["POST"])
def create_purchase_invoice_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not (data.get("model") or "").strip() and not (data.get("supplier_name") or "").strip():
        return jsonify({"error": "Enter a phone model or supplier name"}), 400
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    try:
        with db.db_session() as conn:
            invoice = db.create_purchase_invoice(conn, user_id, data)
            return jsonify(invoice), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# --- Phones ---
# The core inventory: every phone the shop has bought, sold, or is holding.
# Creating/updating/deleting a phone automatically keeps the cash book and
# accounts (khata) ledger in sync - see database.py's create_phone /
# update_phone / delete_phone for the actual sync logic (this is the part
# of the app that has the most business rules).

@app.route("/api/phones", methods=["GET"])
def list_phones_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_phones(conn, user_id))


@app.route("/api/phones/<int:phone_id>", methods=["GET"])
def get_phone_api(phone_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        phone = db.get_phone(conn, user_id, phone_id, include_details=True)
        if not phone:
            return jsonify({"error": "Phone not found"}), 404
        return jsonify(phone)


@app.route("/api/phones", methods=["POST"])
def create_phone():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    required = ["model", "type", "purchase_price"]
    for field in required:
        if field not in data or data[field] == "":
            return jsonify({"error": f"Missing required field: {field}"}), 400
    if data["type"] not in ("PTA", "NON-PTA", "JV"):
        return jsonify({"error": "Type must be PTA, NON-PTA, or JV"}), 400
    if "status" in data:
        err = _validate_status(data["status"])
        if err:
            return jsonify({"error": err}), 400

    try:
        quantity = int(data.get("quantity") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "Quantity must be a whole number"}), 400
    if quantity < 1:
        return jsonify({"error": "Quantity must be at least 1"}), 400

    try:
        with db.db_session() as conn:
            if quantity > 1:
                phones = db.create_phones_bulk(conn, user_id, data)
                return jsonify(phones), 201
            phone = db.create_phone(conn, user_id, data)
            return jsonify(phone), 201
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/phones/<int:phone_id>", methods=["PUT"])
def update_phone(phone_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "type" in data and data["type"] not in ("PTA", "NON-PTA", "JV"):
        return jsonify({"error": "Type must be PTA, NON-PTA, or JV"}), 400
    if "status" in data:
        err = _validate_status(data["status"])
        if err:
            return jsonify({"error": err}), 400

    try:
        with db.db_session() as conn:
            phone = db.update_phone(conn, user_id, phone_id, data)
            if not phone:
                return jsonify({"error": "Phone not found"}), 404
            return jsonify(phone)
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/phones/bulk-delete", methods=["POST"])
def bulk_delete_phones_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    phone_ids = data.get("phone_ids") or []
    if not phone_ids:
        return jsonify({"error": "No phones selected"}), 400
    with db.db_session() as conn:
        result = db.bulk_delete_phones(conn, user_id, phone_ids)
        return jsonify(result)


@app.route("/api/phones/bulk-sold", methods=["POST"])
def bulk_mark_sold_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    items = data.get("items") or []
    if not items:
        return jsonify({"error": "No phones to mark sold"}), 400
    try:
        with db.db_session() as conn:
            result = db.bulk_mark_sold(
                conn, user_id, items,
                default_sale_price=data.get("sale_price_per_unit"),
            )
            return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/phones/<int:phone_id>", methods=["DELETE"])
def delete_phone(phone_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        existing = db.get_phone(conn, user_id, phone_id)
        if not existing:
            return jsonify({"error": "Phone not found"}), 404
        try:
            db.delete_phone(conn, user_id, phone_id)
        except sqlite3.IntegrityError:
            return jsonify({
                "error": "Can't delete this phone — it still has linked cash "
                         "or account entries. Remove those first, then try again.",
            }), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify({"ok": True})


@app.route("/api/phones/<int:phone_id>/expenses", methods=["POST"])
def add_phone_expense(phone_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    with db.db_session() as conn:
        try:
            expense = db.add_phone_expense(conn, user_id, phone_id, data)
        except db.NegativeBalanceWarning as w:
            return _negative_balance_response(w)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not expense:
            return jsonify({"error": "Phone not found"}), 404
        return jsonify(db.get_phone(conn, user_id, phone_id, include_details=True))


@app.route("/api/phones/<int:phone_id>/expenses/<int:expense_id>", methods=["PUT"])
def update_phone_expense(phone_id, expense_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "amount" in data:
        amount, err = _require_amount(data)
        if err:
            return jsonify({"error": err}), 400
        data["amount"] = amount
    with db.db_session() as conn:
        try:
            expense = db.update_phone_expense(conn, user_id, phone_id, expense_id, data)
        except db.NegativeBalanceWarning as w:
            return _negative_balance_response(w)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not expense:
            return jsonify({"error": "Expense not found"}), 404
        return jsonify(db.get_phone(conn, user_id, phone_id, include_details=True))


@app.route("/api/phones/<int:phone_id>/expenses/<int:expense_id>", methods=["DELETE"])
def delete_phone_expense(phone_id, expense_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.get_phone(conn, user_id, phone_id):
            return jsonify({"error": "Phone not found"}), 404
        if not db.delete_phone_expense(conn, user_id, phone_id, expense_id):
            return jsonify({"error": "Expense not found"}), 404
        return jsonify(db.get_phone(conn, user_id, phone_id, include_details=True))


# --- Overview / Dashboard ---
# Summary numbers shown on the Today / Overview pages: stock worth, profit,
# how much is owed (udhar), cash in hand. These are all *calculated* from
# the phones/accounts/cash-book tables, not stored separately - so they're
# always consistent with the underlying ledger.

@app.route("/api/overview")
def overview_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "summary": db.compute_dashboard(conn, user_id),
            "monthly": db.compute_monthly_metrics(conn, user_id),
        })


@app.route("/api/dashboard")
def dashboard():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "summary": db.compute_dashboard(conn, user_id),
            "monthly": db.compute_monthly_metrics(conn, user_id),
            "phones": db.list_phones(conn, user_id),
        })


@app.route("/api/settings", methods=["PUT"])
def update_settings():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            db.update_user_settings(conn, user_id, data)
            return jsonify(db.compute_dashboard(conn, user_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/storage/settings", methods=["GET"])
def get_storage_settings_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.get_storage_settings(conn, user_id))


@app.route("/api/storage/settings", methods=["PUT"])
def update_storage_settings_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    with db.db_session() as conn:
        return jsonify(db.update_storage_settings(conn, user_id, data))


@app.route("/api/storage/backup-now", methods=["POST"])
def backup_now_api():
    user_id = _current_user_id()
    import backup_service
    path = backup_service.backup_user_data(user_id, force=True)
    if not path:
        return jsonify({"error": "Set a local backup folder in Settings first"}), 400
    with db.db_session() as conn:
        settings = db.get_storage_settings(conn, user_id)
    return jsonify({"ok": True, "path": path, **settings})


@app.route("/api/storage/backup-status", methods=["GET"])
def backup_status_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.get_storage_settings(conn, user_id))


@app.route("/api/storage/backups", methods=["GET"])
def list_backups_api():
    user_id = _current_user_id()
    import backup_service
    return jsonify({"backups": backup_service.list_backup_files(user_id)})


@app.route("/api/storage/restore", methods=["POST"])
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
    session.clear()
    return jsonify({
        "ok": True,
        "message": "Database restored. Please sign in again.",
        "safety_copy": safety,
    })


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


@app.route("/api/storage/browse-backup-file", methods=["POST"])
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


@app.route("/api/storage/browse-folder", methods=["POST"])
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

@app.route("/api/partners", methods=["GET"])
def list_partners_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_partners(conn, user_id))


@app.route("/api/partners", methods=["POST"])
def create_partner_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    with db.db_session() as conn:
        return jsonify(db.create_partner(conn, user_id, data)), 201


@app.route("/api/partners/<int:partner_id>", methods=["PUT"])
def update_partner_api(partner_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    with db.db_session() as conn:
        partner = db.update_partner(conn, user_id, partner_id, data)
        if not partner:
            return jsonify({"error": "Partner not found"}), 404
        return jsonify(partner)


@app.route("/api/partners/<int:partner_id>", methods=["DELETE"])
def delete_partner_api(partner_id):
    user_id = _current_user_id()
    try:
        with db.db_session() as conn:
            db.delete_partner(conn, user_id, partner_id)
            return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/partners/reinvest-profit", methods=["POST"])
def reinvest_profit_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("partner_id"):
        return jsonify({"error": "Partner is required"}), 400
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    try:
        with db.db_session() as conn:
            result = db.reinvest_profit(conn, user_id, data)
            return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/partners/side-investment", methods=["POST"])
def side_investment_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("partner_id"):
        return jsonify({"error": "Partner is required"}), 400
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    try:
        with db.db_session() as conn:
            result = db.add_side_investment(conn, user_id, data)
            return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# --- Fixed Expenses ---
# Recurring costs (shop rent, staff salary, etc.) that post straight to the
# cash book as an outgoing entry, separate from per-phone expenses.

@app.route("/api/fixed-expenses", methods=["GET"])
def list_fixed_expenses_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_fixed_expenses(conn, user_id))


@app.route("/api/fixed-expenses", methods=["POST"])
def create_fixed_expense_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("purpose"):
        return jsonify({"error": "Purpose is required"}), 400
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    try:
        with db.db_session() as conn:
            return jsonify(db.create_fixed_expense(conn, user_id, data)), 201
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/fixed-expenses/<int:expense_id>", methods=["DELETE"])
def delete_fixed_expense_api(expense_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        db.delete_fixed_expense(conn, user_id, expense_id)
        return jsonify({"ok": True})


# --- Bank Accounts ---
# Separate from the cash book (physical cash) - tracks money sitting in the
# shop's actual bank account(s) and each deposit/withdrawal against them.

@app.route("/api/banks", methods=["GET"])
def list_banks_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "banks": db.list_banks(conn, user_id),
            "total_balance": db.total_bank_balance(conn, user_id),
        })


@app.route("/api/banks", methods=["POST"])
def create_bank_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "Bank name is required"}), 400
    try:
        with db.db_session() as conn:
            return jsonify(db.create_bank(conn, user_id, data)), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/banks/<int:bank_id>", methods=["PUT"])
def update_bank_api(bank_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "name" in data and not (data.get("name") or "").strip():
        return jsonify({"error": "Bank name is required"}), 400
    with db.db_session() as conn:
        bank = db.update_bank(conn, user_id, bank_id, data)
        if not bank:
            return jsonify({"error": "Bank not found"}), 404
        return jsonify(bank)


@app.route("/api/banks/<int:bank_id>", methods=["DELETE"])
def delete_bank_api(bank_id):
    user_id = _current_user_id()
    try:
        with db.db_session() as conn:
            db.delete_bank(conn, user_id, bank_id)
            return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/banks/<int:bank_id>/transactions", methods=["GET"])
def list_bank_transactions_api(bank_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.get_bank(conn, user_id, bank_id):
            return jsonify({"error": "Bank not found"}), 404
        return jsonify(db.list_bank_transactions(conn, bank_id))


@app.route("/api/banks/<int:bank_id>/transactions", methods=["POST"])
def create_bank_transaction_api(bank_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    if data.get("transaction_type") not in db.BANK_TX_TYPES:
        return jsonify({"error": "Transaction type must be credit or debit"}), 400
    force = bool(data.get("force"))
    try:
        with db.db_session() as conn:
            if not db.get_bank(conn, user_id, bank_id):
                return jsonify({"error": "Bank not found"}), 404
            entry = db.create_bank_transaction(
                conn, bank_id, data, user_id=user_id, mirror_cash_book=True, force=force,
            )
            return jsonify(entry), 201
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


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


@app.route("/api/banks/<int:bank_id>/transactions/<int:tx_id>", methods=["PUT"])
def update_bank_transaction_api(bank_id, tx_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "amount" in data:
        amount, err = _require_amount(data)
        if err:
            return jsonify({"error": err}), 400
        data["amount"] = amount
    with db.db_session() as conn:
        if not _get_owned_bank_transaction(conn, user_id, bank_id, tx_id):
            return jsonify({"error": "Transaction not found"}), 404
        entry = db.update_bank_transaction(conn, tx_id, data, user_id=user_id)
        if not entry:
            return jsonify({"error": "Transaction not found"}), 404
        return jsonify(entry)


@app.route("/api/banks/<int:bank_id>/transactions/<int:tx_id>", methods=["DELETE"])
def delete_bank_transaction_api(bank_id, tx_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not _get_owned_bank_transaction(conn, user_id, bank_id, tx_id):
            return jsonify({"error": "Transaction not found"}), 404
        db.delete_bank_transaction(conn, tx_id, user_id=user_id)
        return jsonify({"ok": True})


# --- Cash Book ---
# The shop's day-to-day physical cash ledger (money in vs money out). Most
# entries here are created automatically by other actions (a sale, an
# expense, a wasool/collection) rather than typed in directly - see the
# "ledger_links" glossary note at the top of this file.

@app.route("/api/cash-book", methods=["GET"])
def list_cash_book_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "entries": db.list_cash_book(conn, user_id),
            "daily": db.cash_book_daily_summary(conn, user_id),
            "balance": db.cash_in_hand_balance(conn, user_id),
        })


@app.route("/api/cash-book", methods=["POST"])
def create_cash_book_entry_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    if data.get("entry_type") not in db.CASH_BOOK_TYPES:
        return jsonify({"error": "Entry type must be in or out"}), 400
    try:
        with db.db_session() as conn:
            return jsonify(db.create_cash_book_entry(conn, user_id, data)), 201
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/cash-book/<int:entry_id>", methods=["PUT"])
def update_cash_book_entry_api(entry_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "amount" in data:
        amount, err = _require_amount(data)
        if err:
            return jsonify({"error": err}), 400
        data["amount"] = amount
    if "entry_type" in data and data.get("entry_type") not in db.CASH_BOOK_TYPES:
        return jsonify({"error": "Entry type must be in or out"}), 400
    try:
        with db.db_session() as conn:
            entry = db.update_cash_book_entry(conn, user_id, entry_id, data)
            if not entry:
                return jsonify({"error": "Entry not found"}), 404
            return jsonify(entry)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/cash-book/<int:entry_id>", methods=["DELETE"])
def delete_cash_book_entry_api(entry_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        db.delete_cash_book_entry(conn, user_id, entry_id)
        return jsonify({"ok": True})


# --- Journal Vouchers ---
# Manual, free-form ledger entries for anything that doesn't fit the normal
# sale/purchase/expense flows (accounting adjustments, corrections, etc.).

@app.route("/api/journal-vouchers", methods=["GET"])
def list_journal_vouchers_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_journal_vouchers(conn, user_id))


@app.route("/api/journal-vouchers", methods=["POST"])
def create_journal_voucher_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    if not data.get("debit_account_id") or not data.get("credit_account_id"):
        return jsonify({"error": "Debit and credit accounts are required"}), 400
    try:
        with db.db_session() as conn:
            return jsonify(db.create_journal_voucher(conn, user_id, data)), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/journal-vouchers/<int:voucher_id>", methods=["DELETE"])
def delete_journal_voucher_api(voucher_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.delete_journal_voucher(conn, user_id, voucher_id):
            return jsonify({"error": "Voucher not found"}), 404
        return jsonify({"ok": True})


@app.route("/api/accounts/expense-categories", methods=["GET"])
def expense_categories_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_khata_accounts(conn, user_id))


# --- Accounts ---
# The khata: customer and supplier running accounts. Each account has a
# statement of entries (debit/credit) that nets out to how much is owed
# to/by that person - this is what "udhar" tracking is built on.

@app.route("/api/accounts", methods=["GET"])
def list_accounts_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        summary = db.accounts_summary(conn, user_id)
        dash = db.compute_dashboard(conn, user_id)
        return jsonify({
            "accounts": db.list_khata_accounts(conn, user_id),
            "summary": summary,
            "cash_in_hand": dash["cash_in_hand"],
            "total_in_bank": dash["total_in_bank"],
            "expected_bank_balance": dash["expected_cash_balance"],
        })


@app.route("/api/accounts", methods=["POST"])
def create_account_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    try:
        with db.db_session() as conn:
            return jsonify(db.create_account(conn, user_id, data)), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/accounts/<int:account_id>", methods=["PUT"])
def update_account_api(account_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "name" in data and not (data.get("name") or "").strip():
        return jsonify({"error": "Name is required"}), 400
    with db.db_session() as conn:
        account = db.update_account(conn, user_id, account_id, data)
        if not account:
            return jsonify({"error": "Account not found"}), 404
        return jsonify(account)


@app.route("/api/accounts/<int:account_id>", methods=["DELETE"])
def delete_account_api(account_id):
    user_id = _current_user_id()
    try:
        with db.db_session() as conn:
            if not db.get_account(conn, user_id, account_id):
                return jsonify({"error": "Account not found"}), 404
            db.delete_account(conn, user_id, account_id)
            return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/accounts/<int:account_id>/statement")
def account_statement(account_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        statement = db.build_statement(conn, user_id, account_id)
        if not statement:
            return jsonify({"error": "Account not found"}), 404
        return jsonify(statement)


@app.route("/api/accounts/<int:account_id>/entries", methods=["POST"])
def create_entry_api(account_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    amount, err = _require_amount(data)
    if err:
        return jsonify({"error": err}), 400
    data["amount"] = amount
    err = _validate_entry_type(data.get("entry_type"))
    if err:
        return jsonify({"error": err}), 400
    try:
        with db.db_session() as conn:
            if not db.get_account(conn, user_id, account_id):
                return jsonify({"error": "Account not found"}), 404
            entry = db.create_entry(conn, account_id, data, user_id=user_id)
            return jsonify(entry), 201
    except db.NegativeBalanceWarning as w:
        return _negative_balance_response(w)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/accounts/<int:account_id>/entries/<int:entry_id>", methods=["PUT"])
def update_entry_api(account_id, entry_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if "entry_type" in data:
        err = _validate_entry_type(data["entry_type"])
        if err:
            return jsonify({"error": err}), 400
    if "amount" in data:
        amount, err = _require_amount(data)
        if err:
            return jsonify({"error": err}), 400
        data["amount"] = amount
    with db.db_session() as conn:
        if not db.get_account(conn, user_id, account_id):
            return jsonify({"error": "Account not found"}), 404
        row = conn.execute(
            "SELECT id FROM account_entries WHERE id = ? AND account_id = ?",
            (entry_id, account_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Entry not found"}), 404
        try:
            entry = db.update_entry(conn, entry_id, data, user_id=user_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(entry)


@app.route("/api/accounts/<int:account_id>/entries/<int:entry_id>", methods=["DELETE"])
def delete_entry_api(account_id, entry_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.get_account(conn, user_id, account_id):
            return jsonify({"error": "Account not found"}), 404
        row = conn.execute(
            "SELECT id FROM account_entries WHERE id = ? AND account_id = ?",
            (entry_id, account_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "Entry not found"}), 404
        try:
            db.delete_entry(conn, entry_id, user_id=user_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True})


# --- Reports ---
# Read-only lookups/summaries: find a phone by IMEI, list customers who owe
# money (recovery), expense breakdowns, and the day book (a chronological
# log of everything that happened on a given day).

@app.route("/find-imei")
def find_imei_page():
    return render_template("find_imei.html")


@app.route("/api/find-imei")
def find_imei_api():
    user_id = _current_user_id()
    imei = request.args.get("imei", "")
    with db.db_session() as conn:
        phone = db.find_phone_by_imei(conn, user_id, imei)
    if not phone:
        return jsonify({"error": "No phone found with that IMEI"}), 404
    return jsonify(phone)


@app.route("/customer-recovery")
def customer_recovery_page():
    return render_template("customer_recovery.html")


@app.route("/api/reports/customer-recovery")
def customer_recovery_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.customer_recovery_analysis(conn, user_id))


@app.route("/expense-summary")
def expense_summary_page():
    return render_template("expense_summary.html")


@app.route("/api/reports/expense-summary")
def expense_summary_api():
    user_id = _current_user_id()
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    with db.db_session() as conn:
        return jsonify(db.expense_summary(conn, user_id, start_date, end_date))


@app.route("/day-book")
def day_book_page():
    return render_template("day_book.html")


@app.route("/api/reports/day-book")
def day_book_api():
    user_id = _current_user_id()
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    with db.db_session() as conn:
        return jsonify(db.cash_book_daily_summary(conn, user_id, start_date, end_date))


# --- Backup ---
# Manual "download my data" export - automatic scheduled backups are
# handled separately by backup_service.py.

@app.route("/api/backup/export")
def backup_export():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.export_all_data(conn, user_id))


@app.errorhandler(sqlite3.DatabaseError)
def handle_database_error(exc):
    """Corruption discovered mid-session (not just at startup) — show a clear
    message instead of a blank 500, and stop retrying against the broken file.
    A transient sqlite3.OperationalError (e.g. "database is locked" from a
    momentary collision with another writer) is NOT corruption — don't cache
    it as permanent, just ask the browser to retry. Likewise a
    sqlite3.IntegrityError (e.g. "FOREIGN KEY constraint failed" from a
    blocked delete) means one write was rejected and rolled back — the file
    itself is untouched, so it must not poison every later request the way
    real corruption does."""
    if isinstance(exc, sqlite3.OperationalError):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Database busy, please retry"}), 503
        return "Database busy, please retry…", 503
    if isinstance(exc, sqlite3.IntegrityError):
        message = f"Couldn't complete that action: {exc}"
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), 409
        return message, 409
    global _DB_ERROR
    _DB_ERROR = str(exc)
    if request.path.startswith("/api/"):
        return jsonify({"error": f"Database problem: {_DB_ERROR}"}), 500
    return _DB_ERROR_HTML.format(detail=_DB_ERROR, db_path=db.DB_PATH), 500


if __name__ == "__main__":
    import os
    import socket
    import threading
    import time
    import webbrowser

    import backup_service

    _HOST = os.environ.get("CRM_HOST", "127.0.0.1")
    _DEFAULT_PORT = int(os.environ.get("CRM_PORT", "5050"))

    def _find_free_port(start: int) -> int:
        for port in range(start, start + 20):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind((_HOST, port))
                    return port
                except OSError:
                    continue
        return start

    def _open_browser(host: str, port: int) -> None:
        url = f"http://{host}:{port}"
        for _ in range(30):
            time.sleep(0.5)
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    break
            except OSError:
                continue
        webbrowser.open(url)

    port = _find_free_port(_DEFAULT_PORT)
    os.environ["CRM_PORT"] = str(port)
    url = f"http://{_HOST}:{port}"

    print("Phone Reseller CRM")
    print(f"  Server: {url}")
    print("  Press Ctrl+C to stop.\n")

    if _HOST not in ("127.0.0.1", "localhost", "::1"):
        print(
            "  WARNING: CRM_HOST is set to a non-loopback address "
            f"({_HOST}) -- this app has no CSRF protection and was built "
            "for localhost-only use. Anyone who can reach this address on "
            "your network can use the CRM as if they were logged in. Only "
            "do this on a network you trust.\n"
        )

    backup_service.run_startup_backups()
    backup_service.start_auto_backup_thread()
    threading.Thread(target=_open_browser, args=(_HOST, port), daemon=True).start()
    # Bug #27: missing threaded=True here (launch_crm.py's equivalent
    # app.run() call already had it) meant `python app.py` served one
    # request at a time — every other tab/page blocked until whatever was
    # in flight finished. A slow request (e.g. signup's backup) made
    # concurrent pages fail with a generic browser fetch error, not a
    # clean message, and made transient DB-busy retries pile up. See the
    # threading comment on ensure_db() above, which already assumed this.
    app.run(host=_HOST, port=port, debug=False, use_reloader=False, threaded=True)
