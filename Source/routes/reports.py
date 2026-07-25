"""Flask blueprint: Overview, setup wizard, today/month reports, find-IMEI."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import database as db
import backup_service
from app_helpers import (
    _current_user_id,
)

bp = Blueprint('reports', __name__)

import backup_service

@bp.route("/api/today")
def today_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.compute_today_summary(conn, user_id))



@bp.route("/api/month-report")
def month_report_api():
    user_id = _current_user_id()
    year_month = request.args.get("month")
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    with db.db_session() as conn:
        return jsonify(db.compute_month_report(conn, user_id, year_month, start_date, end_date))



@bp.route("/api/monthly-closing")
def monthly_closing_api():
    user_id = _current_user_id()
    year_month = request.args.get("month")
    with db.db_session() as conn:
        return jsonify(db.compute_monthly_closing_summary(conn, user_id, year_month))



@bp.route("/api/monthly-closing/close-month", methods=["POST"])
def close_the_month_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.close_the_month(conn, user_id))



@bp.route("/api/overview")
def overview_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify({
            "summary": db.compute_dashboard(conn, user_id),
            "monthly": db.compute_monthly_metrics(conn, user_id),
        })


# --- Opening Setup Wizard ---
# Lets a new customer with an existing business seed their old books
# (already-owned phones, real cash/bank balances, existing receivables and
# payables) before Actual Liquid vs Expected Liquid means anything. Steps
# B (cash), C (banks) and D (khata openings) reuse the existing /api/settings,
# /api/banks and /api/accounts endpoints directly from the wizard's own
# frontend - see database.py's setup_status/add_opening_stock docstrings for
# why only Step A (opening stock) and completion need dedicated routes here.


@bp.route("/api/setup/status")
def setup_status_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.setup_status(conn, user_id))



@bp.route("/api/setup/opening-stock", methods=["POST"])
def setup_opening_stock_api():
    user_id = _current_user_id()
    data = request.get_json(force=True)
    rows = data.get("phones") or []
    if not rows:
        return jsonify({"error": "Add at least one phone"}), 400
    try:
        with db.db_session() as conn:
            created = db.add_opening_stock(conn, user_id, rows)
        return jsonify({"ok": True, "created": created}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400



@bp.route("/api/setup/complete", methods=["POST"])
def setup_complete_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        db.complete_setup(conn, user_id)
        return jsonify(db.setup_status(conn, user_id))



@bp.route("/api/find-imei")
def find_imei_api():
    user_id = _current_user_id()
    imei = request.args.get("imei", "")
    with db.db_session() as conn:
        phone = db.find_phone_by_imei(conn, user_id, imei)
    if not phone:
        return jsonify({"error": "No phone found with that IMEI"}), 404
    return jsonify(phone)



@bp.route("/api/reports/customer-recovery")
def customer_recovery_api():
    user_id = _current_user_id()
    with db.db_session() as conn:
        return jsonify(db.customer_recovery_analysis(conn, user_id))



@bp.route("/api/reports/expense-summary")
def expense_summary_api():
    user_id = _current_user_id()
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    with db.db_session() as conn:
        return jsonify(db.expense_summary(conn, user_id, start_date, end_date))



@bp.route("/api/reports/day-book")
def day_book_api():
    user_id = _current_user_id()
    start_date = request.args.get("from")
    end_date = request.args.get("to")
    with db.db_session() as conn:
        return jsonify(db.cash_book_daily_summary(conn, user_id, start_date, end_date))


# --- Backup ---
# Manual "download my data" export - automatic scheduled backups are
# handled separately by backup_service.py.
