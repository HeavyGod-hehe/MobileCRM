"""Flask blueprints for Phone Reseller CRM HTTP routes."""
from __future__ import annotations

from routes import auth, pages, inventory, billing, accounts_money, storage, reports, system


def register_blueprints(app):
    """Attach all domain blueprints to the Flask app (URL paths unchanged)."""
    for mod in (system, auth, pages, inventory, billing, accounts_money, storage, reports):
        app.register_blueprint(mod.bp)
