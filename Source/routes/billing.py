"""Flask blueprint: Sale and purchase invoice APIs."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from app_helpers import (
    _current_user_id,
    _require_amount,
)

bp = Blueprint('billing', __name__)

@bp.route("/api/billing/inventory")
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



@bp.route("/api/billing/invoices", methods=["GET"])
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



@bp.route("/api/billing/invoices", methods=["POST"])
def create_invoice_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            invoice = db.create_invoice(conn, user_id, data)
            return jsonify(invoice), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# --- Purchase Invoices ---
# Same idea as Billing, but for what the shop bought (from suppliers)
# instead of what it sold.


@bp.route("/api/purchase-invoice/inventory")
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



@bp.route("/api/purchase-invoice/invoices", methods=["GET"])
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



@bp.route("/api/purchase-invoice/invoices", methods=["POST"])
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
