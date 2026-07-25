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

After that, HTTP handlers live in Source/routes/* blueprints (auth, pages,
inventory, billing, accounts_money, storage, reports, system). This file
keeps the Flask app factory, before_request gates (DB / license / auth /
undo), context processor, and error handlers. Shared request helpers are
in app_helpers.py. Business logic stays in database.py (crm_db package).

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

import os
import secrets
import sqlite3
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, redirect, request, session, url_for

import database as db
import license_guard as lic
from app_helpers import APP_VERSION, _display_name

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

# HTTP routes live in Source/routes/* blueprints (registered below).
# Shared request helpers live in app_helpers.py.

_DB_READY = False
_DB_ERROR = None
_DB_INIT_LOCK = threading.Lock()

# Blueprint-prefixed endpoint names (Flask adds the blueprint name).
AUTH_EXEMPT_ENDPOINTS = frozenset({
    "auth.login_page", "auth.auth_status", "auth.auth_login", "auth.auth_signup",
    "auth.auth_forgot_password", "auth.auth_reset_password",
    "auth.auth_reset_password_hwid", "static",
    "auth.activation_page", "system.license_status", "system.license_activate",
})

LICENSE_EXEMPT_ENDPOINTS = frozenset({
    "auth.activation_page", "system.license_status", "system.license_activate", "static",
})


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
    """before_request hook: makes sure the database is migrated and ready
    before any route runs, serialized behind _DB_INIT_LOCK so concurrent
    first-launch requests can't collide mid-migration (see the lock
    comment below), and caches a real schema error as permanent (while
    treating a transient lock as a "retry me" 503, not a crash)."""
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
    return redirect(url_for("auth.activation_page"))


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
        if endpoint == "auth.login_page":
            return
        if request.path.startswith("/api/auth"):
            return
        if request.path.startswith("/api/"):
            return jsonify({"error": "Setup required", "needs_setup": True}), 401
        return redirect(url_for("auth.login_page"))

    if not session.get("logged_in") or not session.get("user_id"):
        if endpoint == "auth.login_page":
            return redirect(url_for("pages.today_page"))
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("auth.login_page"))


# --- Undo / Redo ---
# Snapshots the whole live db right before AND after every qualifying
# mutating request (see database.py's "Undo / Redo" section for why it's
# snapshot-based rather than a hand-written inverse per mutation type, and
# for which routes are excluded). Wrapped in try/except so a bug in this
# bookkeeping can never break the actual request it's piggybacking on.

@app.before_request
def undo_ensure_baseline():
    user_id = session.get("user_id")
    if not user_id or not db.undo_should_track(request.method, request.path):
        return
    try:
        db.ensure_undo_baseline(user_id)
    except Exception:
        pass


@app.after_request
def undo_record_checkpoint(response):
    try:
        user_id = session.get("user_id")
        if user_id and db.undo_should_track(request.method, request.path) \
                and 200 <= response.status_code < 300:
            db.record_undo_checkpoint(user_id, db.describe_undo_action(request.method, request.path))
    except Exception:
        pass
    return response



from routes import register_blueprints
register_blueprints(app)

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
    import socket
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
