"""Flask blueprint: Phones and returns APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
import sqlite3

import database as db
from app_helpers import (
    _current_user_id,
    _require_amount,
    _negative_balance_response,
    _validate_status,
)

bp = Blueprint('inventory', __name__)

@bp.route("/api/returns", methods=["GET"])
def list_returns_api():
    user_id = _current_user_id()
    return_type = request.args.get("type")
    with db.db_session() as conn:
        return jsonify(db.list_return_logs(conn, user_id, return_type))



@bp.route("/api/returns/purchase", methods=["POST"])
def process_purchase_return_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            return jsonify(db.process_purchase_return(conn, user_id, data)), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400



@bp.route("/api/returns/sale", methods=["POST"])
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



@bp.route("/api/returns/inventory/purchase")
def purchase_return_inventory_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_phones_for_purchase_return(conn, user_id))



@bp.route("/api/returns/inventory/sale")
def sale_return_inventory_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_phones_for_sale_return(conn, user_id))


# --- Billing ---
# Sale invoices for printing/WhatsApp (static/whatsapp.js). Invoices are
# print-only records here - the actual sale/inventory change already
# happened through the Phones API; billing just formats a receipt for it.


@bp.route("/api/phones", methods=["GET"])
def list_phones_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_phones(conn, user_id))



@bp.route("/api/phones/<int:phone_id>", methods=["GET"])
def get_phone_api(phone_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        phone = db.get_phone(conn, user_id, phone_id, include_details=True)
        if not phone:
            return jsonify({"error": "Phone not found"}), 404
        return jsonify(phone)



@bp.route("/api/phones", methods=["POST"])
def create_phone():
    """POST /api/phones: validates the request (required fields, type,
    status, quantity), then delegates to db.create_phones_bulk() for
    quantity > 1 or db.create_phone() for a single unit - all the actual
    ledger-posting logic lives in database.py, this is just HTTP
    plumbing and input validation."""
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



@bp.route("/api/phones/<int:phone_id>", methods=["PUT"])
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



@bp.route("/api/phones/bulk-delete", methods=["POST"])
def bulk_delete_phones_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    phone_ids = data.get("phone_ids") or []
    if not phone_ids:
        return jsonify({"error": "No phones selected"}), 400
    with db.db_session() as conn:
        result = db.bulk_delete_phones(conn, user_id, phone_ids)
        return jsonify(result)



@bp.route("/api/phones/bulk-sold", methods=["POST"])
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



@bp.route("/api/phones/<int:phone_id>", methods=["DELETE"])
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



@bp.route("/api/phones/<int:phone_id>/expenses", methods=["POST"])
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



@bp.route("/api/phones/<int:phone_id>/expenses/<int:expense_id>", methods=["PUT"])
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



@bp.route("/api/phones/<int:phone_id>/expenses/<int:expense_id>", methods=["DELETE"])
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
