# Phone Reseller CRM

A desktop CRM for phone resellers: inventory (PTA/NON-PTA/JV phones), bank
accounts, cash book, customer/supplier ledgers with running balances,
monthly closing, and a licensing/activation system for paid customer
installs. Built with Flask + SQLite (WAL mode) on the backend and
server-rendered Jinja templates + vanilla JS on the frontend.
It runs as a local web server that opens in the customer's default
browser — there's no separate desktop UI framework.

Packaged for customers as a PyInstaller onedir build wrapped in a Windows
installer (Inno Setup) or a macOS `.app`.

## Running from source

```
cd Source
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python launch_crm.py
```

This starts the Flask server on `http://127.0.0.1:5050` (override with the
`CRM_PORT` / `CRM_HOST` env vars) and opens it in your browser.

For running the test suite, install `requirements-dev.txt` as well:

```
pip install -r requirements-dev.txt
pytest -q
```

## Building the Windows installer

One command, run from `Source/` on Windows (requires Inno Setup 6 —
`winget install JRSoftware.InnoSetup` if it's not already installed):

```
python build_installer.py
```

This runs the full pipeline — PyInstaller onedir build, Inno Setup
compile, checksum — and drops `PhoneResellerCRM-Setup-{version}.exe` plus
a matching `.sha256` file in `Source/releases/`.

macOS customer copies are built separately via `build_customer_mac.py` /
`build_customer_copy.py`.

## Where data lives

- **Running from source**: `Source/crm.db` (next to the code), unless the
  `CRM_DB_PATH` environment variable overrides it.
- **Installed (frozen) build**: `Data/crm.db` next to the installed app
  (e.g. next to the `.exe` on Windows, next to the `.app` on macOS),
  alongside `Data/Backups/`.

The database is SQLite in WAL mode, so a live install also has
`crm.db-wal` / `crm.db-shm` files alongside `crm.db` while the server is
running.

## Branches

- **`main`** — current development branch; this is where new work lands.
- **`bugfix/2026-07-22-pass`** — the old stable CRM, kept as a known-good
  reference point. Protected — do not delete or force-push.
- **`Version007`** — the oldest version in this repo's history. Protected.
- **`Practising-Code`** — the repo owner's practice branch, unrelated to
  the CRM's release history. Protected.
