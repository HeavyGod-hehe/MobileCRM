"""Flask blueprint: Accounts, cash book, banks, partners, assets, devices, fixed expenses."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
from app_helpers import (
    _current_user_id,
    _require_amount,
    _negative_balance_response,
    _validate_entry_type,
    _get_owned_bank_transaction,
)

bp = Blueprint('accounts_money', __name__)

@bp.route("/api/partners", methods=["GET"])
def list_partners_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_partners(conn, user_id))



@bp.route("/api/partners", methods=["POST"])
def create_partner_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    with db.db_session() as conn:
        return jsonify(db.create_partner(conn, user_id, data)), 201



@bp.route("/api/partners/<int:partner_id>", methods=["PUT"])
def update_partner_api(partner_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    with db.db_session() as conn:
        partner = db.update_partner(conn, user_id, partner_id, data)
        if not partner:
            return jsonify({"error": "Partner not found"}), 404
        return jsonify(partner)



@bp.route("/api/partners/<int:partner_id>", methods=["DELETE"])
def delete_partner_api(partner_id):
    user_id = _current_user_id()
    try:
        with db.db_session() as conn:
            db.delete_partner(conn, user_id, partner_id)
            return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/partners/reinvest-profit", methods=["POST"])
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



@bp.route("/api/partners/side-investment", methods=["POST"])
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



@bp.route("/api/partners/side-investments", methods=["GET"])
def list_side_investments_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_side_investments(conn, user_id))



@bp.route("/api/partners/side-investments/<int:investment_id>", methods=["DELETE"])
def delete_side_investment_api(investment_id):
    user_id = _current_user_id()
    try:
        with db.db_session() as conn:
            result = db.reverse_side_investment(conn, user_id, investment_id)
            return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# --- Personal Assets ---
# Plots, commodities, gold, or anything else the shop owner wants to note
# the value of for their own reference. Deliberately NOT part of the money
# model - see database.py's _migrate_personal_assets docstring for why.


@bp.route("/api/personal-assets", methods=["GET"])
def list_personal_assets_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_personal_assets(conn, user_id))



@bp.route("/api/personal-assets", methods=["POST"])
def create_personal_asset_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            return jsonify(db.create_personal_asset(conn, user_id, data)), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/personal-assets/<int:asset_id>", methods=["PUT"])
def update_personal_asset_api(asset_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            result = db.update_personal_asset(conn, user_id, asset_id, data)
            if not result:
                return jsonify({"error": "Asset not found"}), 404
            return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/personal-assets/<int:asset_id>", methods=["DELETE"])
def delete_personal_asset_api(asset_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.delete_personal_asset(conn, user_id, asset_id):
            return jsonify({"error": "Asset not found"}), 404
        return jsonify({"ok": True})


# --- Devices ---
# Shop-owned equipment (POS terminal, delivery bike, laptop, etc.), shown on
# Overview. Isolated the same way as Personal Assets - see database.py's
# _migrate_devices docstring for why this is NOT a partner-capital replacement.


@bp.route("/api/devices", methods=["GET"])
def list_devices_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_devices(conn, user_id))



@bp.route("/api/devices", methods=["POST"])
def create_device_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            return jsonify(db.create_device(conn, user_id, data)), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/devices/<int:device_id>", methods=["PUT"])
def update_device_api(device_id):
    user_id = _current_user_id()
    data = request.get_json(force=True)
    try:
        with db.db_session() as conn:
            result = db.update_device(conn, user_id, device_id, data)
            if not result:
                return jsonify({"error": "Device not found"}), 404
            return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/devices/<int:device_id>", methods=["DELETE"])
def delete_device_api(device_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.delete_device(conn, user_id, device_id):
            return jsonify({"error": "Device not found"}), 404
        return jsonify({"ok": True})


# --- Fixed Expenses ---
# Recurring costs (shop rent, staff salary, etc.) that post straight to the
# cash book as an outgoing entry, separate from per-phone expenses.


@bp.route("/api/fixed-expenses", methods=["GET"])
def list_fixed_expenses_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.list_fixed_expenses(conn, user_id))



@bp.route("/api/fixed-expenses", methods=["POST"])
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



@bp.route("/api/fixed-expenses/<int:expense_id>", methods=["DELETE"])
def delete_fixed_expense_api(expense_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        db.delete_fixed_expense(conn, user_id, expense_id)
        return jsonify({"ok": True})


# --- Bank Accounts ---
# Separate from the cash book (physical cash) - tracks money sitting in the
# shop's actual bank account(s) and each deposit/withdrawal against them.


@bp.route("/api/banks", methods=["GET"])
def list_banks_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "banks": db.list_banks(conn, user_id),
            "total_balance": db.total_bank_balance(conn, user_id),
        })



@bp.route("/api/banks", methods=["POST"])
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



@bp.route("/api/banks/<int:bank_id>", methods=["PUT"])
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



@bp.route("/api/banks/<int:bank_id>", methods=["DELETE"])
def delete_bank_api(bank_id):
    user_id = _current_user_id()
    try:
        with db.db_session() as conn:
            db.delete_bank(conn, user_id, bank_id)
            return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/banks/<int:bank_id>/transactions", methods=["GET"])
def list_bank_transactions_api(bank_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        if not db.get_bank(conn, user_id, bank_id):
            return jsonify({"error": "Bank not found"}), 404
        return jsonify(db.list_bank_transactions(conn, bank_id))



@bp.route("/api/banks/<int:bank_id>/transactions", methods=["POST"])
def create_bank_transaction_api(bank_id):
    """POST a manual credit/debit on a bank account: validates the amount
    and transaction_type, confirms the bank belongs to this user, then
    creates it via db.create_bank_transaction() with mirror_cash_book=True
    so it also shows up in the cash book. `force` re-submits past a
    negative-balance warning the user already confirmed."""
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



@bp.route("/api/banks/<int:bank_id>/transactions/<int:tx_id>", methods=["DELETE"])
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


@bp.route("/api/cash-book", methods=["GET"])
def list_cash_book_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "entries": db.list_cash_book(conn, user_id),
            "daily": db.cash_book_daily_summary(conn, user_id),
            "balance": db.cash_in_hand_balance(conn, user_id),
        })



@bp.route("/api/cash-book", methods=["POST"])
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



@bp.route("/api/cash-book/<int:entry_id>", methods=["DELETE"])
def delete_cash_book_entry_api(entry_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        db.delete_cash_book_entry(conn, user_id, entry_id)
        return jsonify({"ok": True})


# --- Accounts ---
# The khata: customer and supplier running accounts. Each account has a
# statement of entries (debit/credit) that nets out to how much is owed
# to/by that person - this is what "udhar" tracking is built on.


@bp.route("/api/accounts", methods=["GET"])
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



@bp.route("/api/accounts", methods=["POST"])
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



@bp.route("/api/accounts/<int:account_id>", methods=["PUT"])
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



@bp.route("/api/accounts/<int:account_id>", methods=["DELETE"])
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



@bp.route("/api/accounts/<int:account_id>/statement")
def account_statement(account_id):
    user_id = _current_user_id()
    with db.db_session() as conn:
        statement = db.build_statement(conn, user_id, account_id)
        if not statement:
            return jsonify({"error": "Account not found"}), 404
        return jsonify(statement)



@bp.route("/api/accounts/<int:account_id>/entries", methods=["POST"])
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



@bp.route("/api/accounts/<int:account_id>/entries/<int:entry_id>", methods=["PUT"])
def update_entry_api(account_id, entry_id):
    """PUT an edit to one account_entries row: validates entry_type/amount
    if present, confirms the account and entry both belong to this user
    (and that the entry belongs to that account) before delegating to
    db.update_entry(), which recomputes the running balance."""
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



@bp.route("/api/accounts/<int:account_id>/entries/<int:entry_id>", methods=["DELETE"])
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
