"""Dashboard, today/month reports, setup metrics, expense summary."""
from crm_db.core import (  # noqa: F401
    accounts_summary,
    cash_book_daily_summary,
    cash_in_hand_balance,
    close_the_month,
    complete_setup,
    compute_dashboard,
    compute_month_report,
    compute_monthly_closing_summary,
    compute_monthly_metrics,
    compute_today_summary,
    customer_recovery_analysis,
    expense_summary,
    setup_status,
)

__all__ = [
    "accounts_summary",
    "cash_book_daily_summary",
    "cash_in_hand_balance",
    "close_the_month",
    "complete_setup",
    "compute_dashboard",
    "compute_month_report",
    "compute_monthly_closing_summary",
    "compute_monthly_metrics",
    "compute_today_summary",
    "customer_recovery_analysis",
    "expense_summary",
    "setup_status",
]

