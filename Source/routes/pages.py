"""Flask blueprint: HTML page routes (templates)."""
from __future__ import annotations

from flask import Blueprint, render_template


bp = Blueprint('pages', __name__)

@bp.route("/")
def today_page():
    return render_template("today.html")



@bp.route("/inventory")
def inventory():
    return render_template("inventory.html")



@bp.route("/help")
def help_page():
    return render_template("help.html")



@bp.route("/month-report")
def month_report_page():
    return render_template("month_report.html")



@bp.route("/accounts")
def accounts_page():
    return render_template("accounts.html")



@bp.route("/overview")
def overview_page():
    return render_template("overview.html")



@bp.route("/setup")
def setup_page():
    return render_template("setup.html")



@bp.route("/personal-assets")
def personal_assets_page():
    return render_template("personal_assets.html")



@bp.route("/monthly-closing")
def monthly_closing_page():
    return render_template("monthly_closing.html")



@bp.route("/cashbook")
def cashbook_page():
    return render_template("cashbook.html")



@bp.route("/settings")
def settings_page():
    return render_template("settings.html")



@bp.route("/returns")
def returns_page():
    return render_template("returns.html")



@bp.route("/billing")
def billing_page():
    return render_template("billing.html")



@bp.route("/purchase-invoice")
def purchase_invoice_page():
    return render_template("purchase_invoice.html")



@bp.route("/find-imei")
def find_imei_page():
    return render_template("find_imei.html")



@bp.route("/customer-recovery")
def customer_recovery_page():
    return render_template("customer_recovery.html")



@bp.route("/expense-summary")
def expense_summary_page():
    return render_template("expense_summary.html")



@bp.route("/day-book")
def day_book_page():
    return render_template("day_book.html")
