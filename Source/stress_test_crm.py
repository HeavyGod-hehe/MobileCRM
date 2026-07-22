#!/usr/bin/env python3
"""
CRM logic review + stress test harness.
Run: CRM_DB_PATH=/tmp/crm_stress.db python3 stress_test_crm.py
"""
from __future__ import annotations

import os
import random
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Use isolated DB unless already set
if "CRM_DB_PATH" not in os.environ:
    os.environ["CRM_DB_PATH"] = str(Path("/tmp/crm_stress_test.db"))
os.environ.setdefault("CRM_SKIP_LICENSE", "1")

import database as db  # noqa: E402


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0


@dataclass
class StressReport:
    results: list[TestResult] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "", duration_ms: float = 0):
        self.results.append(TestResult(name, passed, detail, duration_ms))
        if not passed:
            self.errors.append(f"{name}: {detail}")

    def warn(self, msg: str):
        self.warnings.append(msg)


report = StressReport()


def run_test(name: str, fn):
    t0 = time.perf_counter()
    try:
        fn()
        ms = (time.perf_counter() - t0) * 1000
        report.add(name, True, f"OK ({ms:.0f}ms)", ms)
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        report.add(name, False, f"{e}\n{traceback.format_exc()}", ms)


def count_table(conn, table, user_id=None):
    if user_id is not None and table in (
        "phones", "cash_book_entries", "ledger_links", "accounts",
        "journal_vouchers", "return_logs", "bank_accounts",
    ):
        if table == "accounts":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        if table == "bank_accounts":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        if table == "cash_book_entries":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        if table == "ledger_links":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        if table == "phones":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        if table == "journal_vouchers":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
        if table == "return_logs":
            return conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()["c"]
    return conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]


def orphan_ledger_links(conn, user_id):
    return conn.execute(
        """
        SELECT COUNT(*) c FROM ledger_links ll
        WHERE ll.user_id = ?
          AND ll.cash_book_entry_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM cash_book_entries cb WHERE cb.id = ll.cash_book_entry_id
          )
        """,
        (user_id,),
    ).fetchone()["c"]


def orphan_account_links(conn, user_id):
    return conn.execute(
        """
        SELECT COUNT(*) c FROM ledger_links ll
        WHERE ll.user_id = ?
          AND ll.account_entry_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM account_entries ae WHERE ae.id = ll.account_entry_id
          )
        """,
        (user_id,),
    ).fetchone()["c"]


def cash_book_cash_total(conn, user_id):
    entries = db._cash_book_running(conn, user_id)
    return entries[0]["balance"] if entries else 0.0


def main():
    db_path = os.environ["CRM_DB_PATH"]
    if Path(db_path).exists():
        Path(db_path).unlink()

    db.init_db()
    user_id = None
    supplier_id = buyer_id = food_id = bank_id = None
    phone_ids: list[int] = []
    sold_ids: list[int] = []

    with db.db_session() as conn:
        u = db.register_user(conn, "stresstest", "stress1234", "", "Stress Test Shop")
        user_id = u["user_id"]
        db.create_partner(conn, user_id, {"name": "Partner A", "capital": 500000})
        db.create_partner(conn, user_id, {"name": "Partner B", "capital": 300000})
        supplier = db.create_account(conn, user_id, {"name": "Supplier Khan", "contact": "0300"})
        buyer = db.create_account(conn, user_id, {"name": "Customer Ali", "contact": "0311"})
        food = db.create_account(conn, user_id, {"name": "Food", "contact": "expense category"})
        food_id = food["id"]
        supplier_id, buyer_id = supplier["id"], buyer["id"]
        bank = db.create_bank(conn, user_id, {"name": "HBL Stress", "initial_balance": 1000000})
        bank_id = bank["id"]
        # Generous opening cash: this fixture is reused across dozens of
        # tests below posting real cash-out purchases/expenses, none of
        # which are testing bug #11's negative-balance guard itself.
        db.update_user_settings(conn, user_id, {"cash_in_hand": "500000000"})

    # --- Unit / sync tests ---
    def test_purchase_with_udhar():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "iPhone 14 Sync",
                "type": "PTA",
                "purchase_price": 100000,
                "payable_amount": 40000,
                "status": "Bought",
                "supplier_account_id": supplier_id,
                "purchase_payment_method": "cash",
            })
            phone_ids.append(p["id"])
            links = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_id=?",
                (user_id, p["id"]),
            ).fetchone()["c"]
            assert links >= 1, "purchase should create ledger links"
            cb = conn.execute(
                "SELECT COUNT(*) c FROM cash_book_entries WHERE user_id=? AND entry_type='out'",
                (user_id,),
            ).fetchone()["c"]
            assert cb >= 1

    def test_borrow_phone():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "iPhone 13 Borrow",
                "type": "NON-PTA",
                "purchase_price": 75000,
                "status": "Bought",
                "acquisition_type": "borrow",
                "supplier_account_id": supplier_id,
            })
            phone_ids.append(p["id"])
            borrow = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_type='phone_borrow' AND source_id=?",
                (user_id, p["id"]),
            ).fetchone()["c"]
            assert borrow >= 1

    def test_sell_with_receivable():
        with db.db_session() as conn:
            pid = phone_ids[0]
            db.update_phone(conn, user_id, pid, {
                "status": "Sold",
                "sale_price": 130000,
                "receivable_amount": 30000,
                "buyer_account_id": buyer_id,
                "sale_payment_method": "cash",
            })
            sold_ids.append(pid)
            recv = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_type='phone_receivable' AND source_id=?",
                (user_id, pid),
            ).fetchone()["c"]
            assert recv >= 1

    def test_phone_expense_sync():
        with db.db_session() as conn:
            pid = phone_ids[1]
            exp = db.add_phone_expense(conn, user_id, pid, {
                "amount": 5000,
                "description": "Screen fix",
            })
            cb = conn.execute(
                "SELECT cash_book_entry_id FROM phone_expenses WHERE id=?", (exp["id"],)
            ).fetchone()["cash_book_entry_id"]
            assert cb is not None

    def test_food_expense_cash_out():
        with db.db_session() as conn:
            cash_before = db.cash_in_hand_balance(conn, user_id)
            db.create_entry(conn, food_id, {
                "entry_type": "credit",
                "amount": 1500,
                "note": "Lunch",
                "payment_source": "cash",
            }, user_id=user_id)
            cash_after = db.cash_in_hand_balance(conn, user_id)
            assert cash_after == round(cash_before - 1500, 2)

    def test_wasool_cash_in():
        with db.db_session() as conn:
            cash_before = db.cash_in_hand_balance(conn, user_id)
            entry = db.create_entry(conn, buyer_id, {
                "entry_type": "debit",
                "amount": 10000,
                "note": "Partial payment",
                "payment_source": "cash",
            }, user_id=user_id)
            assert entry.get("linked_cash_book_entry_id")
            cash_after = db.cash_in_hand_balance(conn, user_id)
            assert cash_after == round(cash_before + 10000, 2)

    def test_delete_phone_cascade():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Delete Test",
                "type": "PTA",
                "purchase_price": 50000,
                "status": "Bought",
                "purchase_payment_method": "cash",
            })
            pid = p["id"]
            cb_before = count_table(conn, "cash_book_entries", user_id)
            db.delete_phone(conn, user_id, pid)
            cb_after = count_table(conn, "cash_book_entries", user_id)
            assert cb_after < cb_before

    def test_delete_account_entry_cascade():
        with db.db_session() as conn:
            entry = db.create_entry(conn, buyer_id, {
                "entry_type": "debit",
                "amount": 2000,
                "note": "Test cascade delete",
                "payment_source": "cash",
            }, user_id=user_id)
            cb_id = entry["linked_cash_book_entry_id"]
            db.delete_entry(conn, entry["id"], user_id=user_id)
            row = conn.execute(
                "SELECT id FROM cash_book_entries WHERE id=?", (cb_id,)
            ).fetchone()
            assert row is None

    def test_journal_voucher():
        with db.db_session() as conn:
            jv = db.create_journal_voucher(conn, user_id, {
                "debit_account_id": supplier_id,
                "credit_account_id": buyer_id,
                "amount": 5000,
                "narration": "Transfer test",
            })
            db.delete_journal_voucher(conn, user_id, jv["id"])
            assert conn.execute(
                "SELECT id FROM journal_vouchers WHERE id=?", (jv["id"],)
            ).fetchone() is None

    def test_purchase_return():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Return Purchase",
                "type": "PTA",
                "purchase_price": 60000,
                "status": "Bought",
                "purchase_payment_method": "cash",
            })
            db.process_purchase_return(conn, user_id, {"phone_id": p["id"], "refund_amount": 60000})
            row = conn.execute("SELECT status FROM phones WHERE id=?", (p["id"],)).fetchone()
            assert row["status"] == "Returned to Supplier"

    def test_sale_return():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Return Sale",
                "type": "PTA",
                "purchase_price": 80000,
                "status": "Sold",
                "sale_price": 95000,
                "purchase_payment_method": "cash",
                "sale_payment_method": "cash",
            })
            db.process_sale_return(conn, user_id, {"phone_id": p["id"], "refund_amount": 95000})
            row = conn.execute("SELECT status FROM phones WHERE id=?", (p["id"],)).fetchone()
            assert row["status"] == "Bought"

    def test_today_bought_includes_sold():
        with db.db_session() as conn:
            today = conn.execute("SELECT date('now','localtime')").fetchone()[0]
            p = db.create_phone(conn, user_id, {
                "model": "Same Day Flip",
                "type": "PTA",
                "purchase_price": 90000,
                "status": "Sold",
                "sale_price": 105000,
                "purchase_date": today,
                "purchase_payment_method": "cash",
                "sale_payment_method": "cash",
            })
            summary = db.compute_today_summary(conn, user_id)
            ids = [x["id"] for x in summary["bought_phones"]]
            assert p["id"] in ids

    def test_update_investments():
        with db.db_session() as conn:
            partners = db.list_partners(conn, user_id)
            p = db.create_phone(conn, user_id, {
                "model": "Investment Test",
                "type": "PTA",
                "purchase_price": 70000,
                "status": "Bought",
                "purchase_payment_method": "cash",
            })
            db.update_phone(conn, user_id, p["id"], {
                "investments": [{"partner_id": partners[0]["id"], "amount": 70000}],
            })
            phone = db.get_phone(conn, user_id, p["id"], include_details=True)
            assert len(phone["investments"]) == 1

    def test_udhar_no_double_count():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Udhar Test",
                "type": "PTA",
                "purchase_price": 100000,
                "status": "Sold",
                "sale_price": 130000,
                "receivable_amount": 30000,
                "buyer_account_id": buyer_id,
                "purchase_payment_method": "cash",
                "sale_payment_method": "cash",
            })
            dash = db.compute_dashboard(conn, user_id)
            acct = db.accounts_summary(conn, user_id)
            phone_recv_only = sum(
                (r["receivable_amount"] or 0) for r in conn.execute(
                    "SELECT receivable_amount, buyer_account_id FROM phones WHERE user_id=? AND status='Sold'",
                    (user_id,),
                ).fetchall()
                if (r["receivable_amount"] or 0) > 0 and not r["buyer_account_id"]
            )
            assert dash["total_udhar"] == round(acct["total_receivable"] + phone_recv_only, 2)
            assert p["receivable_amount"] == 30000

    def test_imei_duplicate_rejected():
        with db.db_session() as conn:
            db.create_phone(conn, user_id, {
                "model": "IMEI A",
                "type": "PTA",
                "purchase_price": 50000,
                "status": "Bought",
                "purchase_payment_method": "cash",
                "imei": "356938035641111",
            })
            try:
                db.create_phone(conn, user_id, {
                    "model": "IMEI B",
                    "type": "PTA",
                    "purchase_price": 50000,
                    "status": "Bought",
                    "purchase_payment_method": "cash",
                    "imei": "356938035641111",
                })
                raise AssertionError("Expected duplicate IMEI error")
            except ValueError as e:
                assert "IMEI" in str(e)

    def test_sale_edit_resyncs_ledger():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Edit Sale",
                "type": "PTA",
                "purchase_price": 80000,
                "status": "Sold",
                "sale_price": 100000,
                "purchase_payment_method": "cash",
                "sale_payment_method": "cash",
            })
            cash_before = db.cash_in_hand_balance(conn, user_id)
            db.update_phone(conn, user_id, p["id"], {"sale_price": 110000})
            cash_after = db.cash_in_hand_balance(conn, user_id)
            assert cash_after == round(cash_before + 10000, 2)

    def test_bulk_sold_udhar_requires_buyer():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Bulk Udhar",
                "type": "PTA",
                "purchase_price": 60000,
                "status": "Bought",
                "purchase_payment_method": "cash",
            })
            try:
                db.bulk_mark_sold(conn, user_id, [{
                    "phone_id": p["id"],
                    "sale_price": 80000,
                    "receivable_amount": 10000,
                }])
                raise AssertionError("Expected buyer account required")
            except ValueError as e:
                assert "buyer account" in str(e).lower()

    def test_fixed_expense_cash_out():
        with db.db_session() as conn:
            cash_before = db.cash_in_hand_balance(conn, user_id)
            exp = db.create_fixed_expense(conn, user_id, {
                "purpose": "Shop rent",
                "amount": 25000,
            })
            cash_after = db.cash_in_hand_balance(conn, user_id)
            assert exp.get("cash_book_entry_id")
            assert cash_after == round(cash_before - 25000, 2)

    def test_zero_cash_balance_and_new_account():
        with db.db_session() as conn:
            balance_before = db.cash_in_hand_balance(conn, user_id)
            db.create_cash_book_entry(conn, user_id, {
                "entry_type": "in",
                "amount": 100,
                "note": "Zero-balance probe in",
                "payment_source": "cash",
            })
            db.create_cash_book_entry(conn, user_id, {
                "entry_type": "out",
                "amount": 100,
                "note": "Zero-balance probe out",
                "payment_source": "cash",
            })
            balance_after = db.cash_in_hand_balance(conn, user_id)
            entries = db.list_cash_book(conn, user_id)
            assert balance_after == balance_before
            assert float(entries[0]["balance"]) == balance_before
            acct = db.create_account(conn, user_id, {"name": "Zero Cash Customer", "contact": "0300"})
            assert acct["balance"] == 0
            bank = db.create_bank(conn, user_id, {
                "name": "Zero Opening Bank",
                "initial_balance": 0,
            })
            assert bank["balance"] == 0
            # A manual bank Deposit (credit) is real cash leaving the drawer
            # into the bank, so it must move Cash in Hand down by the same
            # amount — not just log a bank-side row.
            db.create_bank_transaction(
                conn, bank["id"],
                {"transaction_type": "credit", "amount": 5000, "note": "Test deposit", "force": True},
                user_id=user_id,
                mirror_cash_book=True,
                force=True,
            )
            balance_after_deposit = db.cash_in_hand_balance(conn, user_id)
            assert balance_after_deposit == balance_after - 5000
            daily = db.cash_book_daily_summary(conn, user_id)
            assert daily[0]["opening_balance"] is not None
            # Explicit zero balance must display as numeric zero, not null
            db.create_cash_book_entry(conn, user_id, {
                "entry_type": "out",
                "amount": balance_after_deposit,
                "note": "Drain to exact zero",
                "payment_source": "cash",
            })
            assert db.cash_in_hand_balance(conn, user_id) == 0
            assert float(db.list_cash_book(conn, user_id)[0]["balance"]) == 0

    run_test("Purchase + udhar ledger sync", test_purchase_with_udhar)
    run_test("Borrow phone ledger sync", test_borrow_phone)
    run_test("Sale + receivable ledger sync", test_sell_with_receivable)
    run_test("Phone expense -> cash book sync", test_phone_expense_sync)
    run_test("Food expense -> cash out sync", test_food_expense_cash_out)
    run_test("Wasool debit -> cash in sync", test_wasool_cash_in)
    run_test("Delete phone cascades ledger", test_delete_phone_cascade)
    run_test("Delete account entry cascades cash book", test_delete_account_entry_cascade)
    run_test("Journal voucher create/delete", test_journal_voucher)
    run_test("Purchase return flow", test_purchase_return)
    run_test("Sale return flow", test_sale_return)

    # --- Gap coverage: returns can't refund more than was actually paid (bug #12) ---
    def test_purchase_return_refund_capped():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Refund Cap Purchase Phone", "type": "PTA", "purchase_price": 40000,
                "status": "Bought", "purchase_payment_method": "cash",
                "imei": "888800000005555",
            })
            try:
                db.process_purchase_return(conn, user_id, {
                    "phone_id": p["id"], "refund_amount": 41000,
                })
                raise AssertionError("Expected a refund exceeding the amount paid to be rejected")
            except ValueError as e:
                assert "maximum refundable" in str(e).lower()

        with db.db_session() as conn:
            # The default (no refund_amount given) still refunds exactly what
            # was paid, and an explicit refund at or under that cap succeeds.
            result = db.process_purchase_return(conn, user_id, {"phone_id": p["id"]})
            assert result["refund_amount"] == 40000

    run_test("Purchase return refund is capped at what was actually paid", test_purchase_return_refund_capped)

    def test_sale_return_refund_capped():
        with db.db_session() as conn:
            p = db.create_phone(conn, user_id, {
                "model": "Refund Cap Sale Phone", "type": "PTA", "purchase_price": 40000,
                "status": "Sold", "sale_price": 55000,
                "purchase_payment_method": "cash", "sale_payment_method": "cash",
                "imei": "888800000006666",
            })
            try:
                db.process_sale_return(conn, user_id, {
                    "phone_id": p["id"], "refund_amount": 56000,
                })
                raise AssertionError("Expected a refund exceeding what the customer paid to be rejected")
            except ValueError as e:
                assert "maximum refundable" in str(e).lower()

        with db.db_session() as conn:
            result = db.process_sale_return(conn, user_id, {"phone_id": p["id"]})
            assert result["refund_amount"] == 55000

    run_test("Sale return refund is capped at what the customer actually paid", test_sale_return_refund_capped)

    # --- Gap coverage: UTC vs local-midnight date mismatch (bug #13) ---
    def test_utc_vs_local_midnight_report_alignment():
        # created_at is stored in UTC (see _init_schema); a purchase recorded
        # just after LOCAL midnight has a created_at that's still on the
        # PREVIOUS day in UTC (PKT is UTC+5) -- reports that compared
        # date(created_at) directly against date('now','localtime') used to
        # put that purchase in "yesterday" instead of "today". Only runs the
        # TZ-dependent part on platforms with time.tzset (POSIX); skips it
        # gracefully on Windows, where this stress suite isn't run anyway.
        if not hasattr(time, "tzset"):
            return
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Karachi"
        time.tzset()
        try:
            with db.db_session() as conn:
                u = db.register_user(conn, "tz_midnight_user", "pass1234", "", "TZ Midnight Shop")
                tz_uid = u["user_id"]

                today_local = conn.execute("SELECT date('now', 'localtime')").fetchone()[0]
                # "00:05 local" expressed as its UTC equivalent (PKT is
                # UTC+5, so subtract 5 hours) -- computed via SQLite itself,
                # the same mechanism the app's own local-time conversions use.
                created_at_utc = conn.execute(
                    "SELECT datetime(? || ' 00:05:00', '-5 hours')", (today_local,)
                ).fetchone()[0]

                cursor = conn.execute(
                    """
                    INSERT INTO phones (
                        model, condition, type, purchase_price, status,
                        purchase_date, user_id, created_at
                    ) VALUES (?, '', 'PTA', ?, 'Bought', '', ?, ?)
                    """,
                    ("TZ Midnight Phone", 12345, tz_uid, created_at_utc),
                )
                phone_id = cursor.lastrowid

                summary = db.compute_today_summary(conn, tz_uid)
                bought_ids = [p["id"] for p in summary["bought_phones"]]
                assert phone_id in bought_ids, (
                    f"A phone bought at 00:05 local today (created_at={created_at_utc} UTC) "
                    "should appear in today's bought list, keyed by local date not raw UTC date"
                )

                # Same check for the fixed-expense date used in expense_summary.
                exp_cursor = conn.execute(
                    "INSERT INTO fixed_expenses (purpose, amount, user_id, created_at) VALUES (?, ?, ?, ?)",
                    ("TZ Midnight Expense", 500, tz_uid, created_at_utc),
                )
                exp_id = exp_cursor.lastrowid
                summary_exp = db.expense_summary(conn, tz_uid, start_date=today_local, end_date=today_local)
                fixed_dates = [e["expense_date"] for e in summary_exp["entries"] if e["id"] == exp_id]
                assert fixed_dates == [today_local], (
                    f"Fixed expense created at 00:05 local today should be dated {today_local} "
                    f"(local), not its raw UTC created_at -- got {fixed_dates}"
                )
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    run_test("Purchases/expenses just after local midnight land in today's reports, not UTC-yesterday's",
              test_utc_vs_local_midnight_report_alignment)
    run_test("Today summary includes sold-as-bought", test_today_bought_includes_sold)
    run_test("Update phone investments (bug fix)", test_update_investments)
    run_test("Udhar dashboard no double-count", test_udhar_no_double_count)
    run_test("Duplicate IMEI rejected", test_imei_duplicate_rejected)
    run_test("Sale price edit re-syncs cash book", test_sale_edit_resyncs_ledger)
    run_test("Bulk sold udhar requires buyer account", test_bulk_sold_udhar_requires_buyer)
    run_test("Fixed expense posts to cash book", test_fixed_expense_cash_out)
    run_test("Zero cash balance + new account", test_zero_cash_balance_and_new_account)

    # --- Gap coverage: mixed-activity ledger reconciliation ---
    #
    # All prior sync tests check one transaction type in isolation. Historically
    # every serious ledger bug (return-cash corruption, bank deposit/withdrawal
    # not moving Cash in Hand, stale ledger on phone edits) only showed up once
    # multiple transaction types interleaved over time. This test generates 220+
    # randomized mixed transactions (cash/bank sales, purchases, both return
    # types, journal vouchers, fixed expenses, account credits/debits) against a
    # dedicated user, and cross-checks Cash in Hand, total bank balance, and each
    # account's balance against an independent Python-side running total that
    # this test computes itself from the economic meaning of each transaction it
    # issues (not by re-reading the app's own ledger rows) — so a bug that
    # silently drops, duplicates, or mis-signs a ledger entry shows up as a
    # numeric mismatch instead of being invisible to a same-formula recheck.
    def test_mixed_ledger_reconciliation_stress():
        with db.db_session() as conn:
            ru = db.register_user(conn, "reconcile_stress", "recon12345", "", "Reconcile Stress Shop")
            r_uid = ru["user_id"]
            # This test measures DRIFT (actual delta vs expected delta), not
            # absolute balances, so a generous opening cushion is transparent
            # to what it verifies -- without it, bug #11's negative-balance
            # guard would correctly (but unhelpfully) reject some of these
            # 220 random cash-out operations, since this test starts at zero
            # by design to keep the drift math simple.
            r_bank = db.create_bank(conn, r_uid, {"name": "Recon Bank", "initial_balance": 500000000})
            r_bank_id = r_bank["id"]
            r_supplier = db.create_account(conn, r_uid, {"name": "Recon Supplier"})
            r_buyer = db.create_account(conn, r_uid, {"name": "Recon Buyer"})
            r_util = db.create_account(conn, r_uid, {"name": "Recon Utilities", "contact": "expense category"})
            r_supplier_id, r_buyer_id, r_util_id = r_supplier["id"], r_buyer["id"], r_util["id"]
            db.update_user_settings(conn, r_uid, {"cash_in_hand": "500000000"})
            cash_open = db.cash_in_hand_balance(conn, r_uid)
            bank_open = db.total_bank_balance(conn, r_uid)

        expected_cash = 0.0
        expected_bank = 0.0
        expected_acct = {r_supplier_id: 0.0, r_buyer_id: 0.0, r_util_id: 0.0}
        open_cash_phones, open_bank_phones = [], []
        open_cash_sales, open_bank_sales = [], []

        rng = random.Random(20260707)
        N = 220
        counters = {"imei": 0}

        def next_imei():
            counters["imei"] += 1
            return f"77770000{counters['imei']:07d}"

        with db.db_session() as conn:
            for i in range(N):
                choices = [
                    "cash_sale", "bank_sale", "cash_purchase", "bank_purchase",
                    "fixed_expense_cash", "fixed_expense_bank",
                    "expense_credit_cash", "expense_credit_bank", "expense_debit_cash",
                    "person_credit_cash", "person_debit_cash", "journal_voucher",
                ]
                if open_cash_phones:
                    choices.append("purchase_return_cash")
                if open_bank_phones:
                    choices.append("purchase_return_bank")
                if open_cash_sales:
                    choices.append("sale_return_cash")
                if open_bank_sales:
                    choices.append("sale_return_bank")
                op = rng.choice(choices)

                if op == "cash_sale":
                    p_amt = rng.randint(50, 150) * 1000
                    s_amt = p_amt + rng.randint(5, 30) * 1000
                    p = db.create_phone(conn, r_uid, {
                        "model": f"Recon CS {i}", "type": "PTA", "purchase_price": p_amt,
                        "status": "Sold", "sale_price": s_amt,
                        "purchase_payment_method": "cash", "sale_payment_method": "cash",
                        "imei": next_imei(),
                    })
                    expected_cash += (s_amt - p_amt)
                    open_cash_sales.append((p["id"], s_amt, p_amt))
                elif op == "bank_sale":
                    p_amt = rng.randint(50, 150) * 1000
                    s_amt = p_amt + rng.randint(5, 30) * 1000
                    p = db.create_phone(conn, r_uid, {
                        "model": f"Recon BS {i}", "type": "PTA", "purchase_price": p_amt,
                        "status": "Sold", "sale_price": s_amt,
                        "purchase_payment_method": "bank", "purchase_bank_id": r_bank_id,
                        "sale_payment_method": "bank", "sale_bank_id": r_bank_id,
                        "imei": next_imei(),
                    })
                    expected_bank += (s_amt - p_amt)
                    open_bank_sales.append((p["id"], s_amt, p_amt))
                elif op == "cash_purchase":
                    p_amt = rng.randint(40, 120) * 1000
                    p = db.create_phone(conn, r_uid, {
                        "model": f"Recon CP {i}", "type": "PTA", "purchase_price": p_amt,
                        "status": "Bought", "purchase_payment_method": "cash",
                        "imei": next_imei(),
                    })
                    expected_cash -= p_amt
                    open_cash_phones.append((p["id"], p_amt))
                elif op == "bank_purchase":
                    p_amt = rng.randint(40, 120) * 1000
                    p = db.create_phone(conn, r_uid, {
                        "model": f"Recon BP {i}", "type": "PTA", "purchase_price": p_amt,
                        "status": "Bought", "purchase_payment_method": "bank",
                        "purchase_bank_id": r_bank_id, "imei": next_imei(),
                    })
                    expected_bank -= p_amt
                    open_bank_phones.append((p["id"], p_amt))
                elif op == "purchase_return_cash":
                    pid, p_amt = open_cash_phones.pop(rng.randrange(len(open_cash_phones)))
                    db.process_purchase_return(conn, r_uid, {
                        "phone_id": pid, "refund_amount": p_amt, "payment_source": "cash",
                    })
                    expected_cash += p_amt
                elif op == "purchase_return_bank":
                    pid, p_amt = open_bank_phones.pop(rng.randrange(len(open_bank_phones)))
                    db.process_purchase_return(conn, r_uid, {
                        "phone_id": pid, "refund_amount": p_amt, "payment_source": "bank",
                        "bank_account_id": r_bank_id,
                    })
                    expected_bank += p_amt
                elif op == "sale_return_cash":
                    pid, s_amt, p_amt = open_cash_sales.pop(rng.randrange(len(open_cash_sales)))
                    db.process_sale_return(conn, r_uid, {
                        "phone_id": pid, "refund_amount": s_amt, "payment_source": "cash",
                    })
                    expected_cash -= s_amt
                    open_cash_phones.append((pid, p_amt))  # back in stock -> returnable to supplier too
                elif op == "sale_return_bank":
                    pid, s_amt, p_amt = open_bank_sales.pop(rng.randrange(len(open_bank_sales)))
                    db.process_sale_return(conn, r_uid, {
                        "phone_id": pid, "refund_amount": s_amt, "payment_source": "bank",
                        "bank_account_id": r_bank_id,
                    })
                    expected_bank -= s_amt
                    open_bank_phones.append((pid, p_amt))
                elif op == "fixed_expense_cash":
                    amt = rng.randint(1, 20) * 1000
                    db.create_fixed_expense(conn, r_uid, {
                        "purpose": f"Recon fixed {i}", "amount": amt, "payment_source": "cash",
                    })
                    expected_cash -= amt
                elif op == "fixed_expense_bank":
                    amt = rng.randint(1, 20) * 1000
                    db.create_fixed_expense(conn, r_uid, {
                        "purpose": f"Recon fixed {i}", "amount": amt,
                        "payment_source": "bank", "bank_account_id": r_bank_id,
                    })
                    expected_bank -= amt
                elif op == "expense_credit_cash":
                    amt = rng.randint(1, 10) * 500
                    db.create_entry(conn, r_util_id, {
                        "entry_type": "credit", "amount": amt, "note": "Recon util",
                        "payment_source": "cash",
                    }, user_id=r_uid)
                    expected_cash -= amt
                    expected_acct[r_util_id] += amt
                elif op == "expense_credit_bank":
                    amt = rng.randint(1, 10) * 500
                    db.create_entry(conn, r_util_id, {
                        "entry_type": "credit", "amount": amt, "note": "Recon util",
                        "payment_source": "bank", "bank_account_id": r_bank_id,
                    }, user_id=r_uid)
                    expected_bank -= amt
                    expected_acct[r_util_id] += amt
                elif op == "expense_debit_cash":
                    amt = rng.randint(1, 10) * 500
                    db.create_entry(conn, r_util_id, {
                        "entry_type": "debit", "amount": amt, "note": "Recon util refund",
                        "payment_source": "cash",
                    }, user_id=r_uid)
                    expected_cash += amt
                    expected_acct[r_util_id] -= amt
                elif op == "person_credit_cash":
                    acct_id = rng.choice([r_supplier_id, r_buyer_id])
                    amt = rng.randint(1, 20) * 1000
                    db.create_entry(conn, acct_id, {
                        "entry_type": "credit", "amount": amt, "note": "Recon person credit",
                        "payment_source": "cash",
                    }, user_id=r_uid)
                    expected_cash -= amt
                    expected_acct[acct_id] += amt
                elif op == "person_debit_cash":
                    acct_id = rng.choice([r_supplier_id, r_buyer_id])
                    amt = rng.randint(1, 20) * 1000
                    db.create_entry(conn, acct_id, {
                        "entry_type": "debit", "amount": amt, "note": "Recon person debit",
                        "payment_source": "cash",
                    }, user_id=r_uid)
                    expected_cash += amt
                    expected_acct[acct_id] -= amt
                elif op == "journal_voucher":
                    amt = rng.randint(1, 20) * 1000
                    debit_id, credit_id = rng.sample([r_supplier_id, r_buyer_id], 2)
                    db.create_journal_voucher(conn, r_uid, {
                        "debit_account_id": debit_id, "credit_account_id": credit_id,
                        "amount": amt, "narration": f"Recon JV {i}",
                    })
                    expected_acct[debit_id] -= amt
                    expected_acct[credit_id] += amt

            actual_cash = round(db.cash_in_hand_balance(conn, r_uid) - cash_open, 2)
            actual_bank = round(db.total_bank_balance(conn, r_uid) - bank_open, 2)
            assert abs(actual_cash - round(expected_cash, 2)) < 0.01, (
                f"Cash in Hand drift after {N} mixed transactions: "
                f"expected delta {expected_cash:.2f}, actual delta {actual_cash:.2f}"
            )
            assert abs(actual_bank - round(expected_bank, 2)) < 0.01, (
                f"Bank balance drift after {N} mixed transactions: "
                f"expected delta {expected_bank:.2f}, actual delta {actual_bank:.2f}"
            )
            for acct_id, exp in expected_acct.items():
                actual = db.get_account(conn, r_uid, acct_id)["balance"]
                assert abs(actual - round(exp, 2)) < 0.01, (
                    f"Account #{acct_id} balance drift: expected {exp:.2f}, actual {actual:.2f}"
                )
            assert orphan_ledger_links(conn, r_uid) == 0
            assert orphan_account_links(conn, r_uid) == 0

    run_test("Mixed-activity ledger reconciliation (220 randomized transactions)",
              test_mixed_ledger_reconciliation_stress)

    # --- Gap coverage: concurrency / race conditions ---
    with db.db_session() as conn:
        cu = db.register_user(conn, "concur_stress", "concur12345", "", "Concurrency Shop")
        c_uid = cu["user_id"]
        # Generous opening cash balance: this fixture is reused across many
        # concurrency/invoice tests below that post real cash-out purchases
        # and aren't testing bug #11's negative-balance guard themselves.
        db.update_user_settings(conn, c_uid, {"cash_in_hand": "100000000"})

    # update_phone() only takes SQLite's write lock early (BEGIN IMMEDIATE) when
    # an IMEI is being changed (see the duplicate-IMEI race comment in
    # create_phone/update_phone). A plain status change to "Sold" reads the
    # phone's current status, decides in Python whether to post a sale ledger,
    # and only then writes -- so two near-simultaneous sell requests can both
    # read "Bought" before either commits. A deterministic delay is injected
    # into the ledger-posting step (already-uncommitted at that point) so both
    # threads reliably interleave instead of relying on a lucky race window.
    def test_concurrent_double_sell():
        with db.db_session() as conn:
            p = db.create_phone(conn, c_uid, {
                "model": "Race Sell Phone", "type": "PTA", "purchase_price": 50000,
                "status": "Bought", "purchase_payment_method": "cash",
                "imei": "888800000001111",
            })
            phone_id = p["id"]

        barrier = threading.Barrier(2)
        original = db._post_sale_ledger

        def slow_post_sale_ledger(*args, **kwargs):
            result = original(*args, **kwargs)
            time.sleep(0.4)
            return result

        db._post_sale_ledger = slow_post_sale_ledger
        errors = []

        def worker(sale_price):
            try:
                barrier.wait(timeout=5)
                with db.db_session() as conn2:
                    db.update_phone(conn2, c_uid, phone_id, {
                        "status": "Sold", "sale_price": sale_price, "sale_payment_method": "cash",
                    })
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

        t1 = threading.Thread(target=worker, args=(80000,))
        t2 = threading.Thread(target=worker, args=(90000,))
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)
        db._post_sale_ledger = original

        with db.db_session() as conn:
            links = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_type='phone_sale' AND source_id=?",
                (c_uid, phone_id),
            ).fetchone()["c"]
        assert links == 1, (
            f"Expected exactly 1 sale-ledger link after two concurrent sell requests for the "
            f"same phone (one should reject/no-op), found {links} — double-processing created "
            f"duplicate cash-book/account entries. Thread errors seen: {errors or 'none'}"
        )

    run_test("Concurrent double-sell on the same phone is rejected, not double-posted",
              test_concurrent_double_sell)

    # process_sale_return() has the same read-then-write shape as update_phone:
    # it checks phone["status"] == "Sold" before flipping it back to "Bought" and
    # posting a refund, with no write-lock taken before that check.
    def test_concurrent_double_sale_return():
        with db.db_session() as conn:
            p = db.create_phone(conn, c_uid, {
                "model": "Race Return Phone", "type": "PTA", "purchase_price": 40000,
                "status": "Sold", "sale_price": 55000,
                "purchase_payment_method": "cash", "sale_payment_method": "cash",
                "imei": "888800000002222",
            })
            phone_id2 = p["id"]

        barrier = threading.Barrier(2)
        original = db._create_cash_book_synced

        def slow_ccbs(*args, **kwargs):
            result = original(*args, **kwargs)
            time.sleep(0.4)
            return result

        db._create_cash_book_synced = slow_ccbs
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                with db.db_session() as conn2:
                    db.process_sale_return(conn2, c_uid, {
                        "phone_id": phone_id2, "refund_amount": 55000, "payment_source": "cash",
                    })
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)
        db._create_cash_book_synced = original

        with db.db_session() as conn:
            logs = conn.execute(
                "SELECT COUNT(*) c FROM return_logs WHERE user_id=? AND phone_id=? AND return_type='sale'",
                (c_uid, phone_id2),
            ).fetchone()["c"]
        assert logs == 1, (
            f"Expected exactly 1 sale-return log for two concurrent returns of the same sale "
            f"(one should reject), found {logs} — customer would be refunded twice. "
            f"Thread errors seen: {errors or 'none'}"
        )

    run_test("Concurrent double-return on the same sale is rejected, not double-refunded",
              test_concurrent_double_sale_return)

    # process_purchase_return() has the identical read-then-write shape: it
    # checks phone["status"] is Bought/In Repair before flipping it to
    # "Returned to Supplier" and posting a refund. A lock guard was added
    # preemptively in a prior session (same one-line pattern as the two fixes
    # above) but was never actually proven with a failing-before-fix test —
    # this test exists specifically to prove it, not assume it by pattern match.
    def test_concurrent_double_purchase_return():
        with db.db_session() as conn:
            p = db.create_phone(conn, c_uid, {
                "model": "Race Purchase Return Phone", "type": "PTA", "purchase_price": 35000,
                "status": "Bought", "purchase_payment_method": "cash",
                "imei": "888800000004444",
            })
            phone_id4 = p["id"]

        barrier = threading.Barrier(2)
        original = db._create_cash_book_synced

        def slow_ccbs(*args, **kwargs):
            result = original(*args, **kwargs)
            time.sleep(0.4)
            return result

        db._create_cash_book_synced = slow_ccbs
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                with db.db_session() as conn2:
                    db.process_purchase_return(conn2, c_uid, {
                        "phone_id": phone_id4, "refund_amount": 35000, "payment_source": "cash",
                    })
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)
        db._create_cash_book_synced = original

        with db.db_session() as conn:
            logs = conn.execute(
                "SELECT COUNT(*) c FROM return_logs WHERE user_id=? AND phone_id=? AND return_type='purchase'",
                (c_uid, phone_id4),
            ).fetchone()["c"]
        assert logs == 1, (
            f"Expected exactly 1 purchase-return log for two concurrent returns of the same "
            f"purchase (one should reject), found {logs} — supplier refund posted twice. "
            f"Thread errors seen: {errors or 'none'}"
        )

    run_test("Concurrent double-return on the same purchase is rejected, not double-refunded",
              test_concurrent_double_purchase_return)

    # --- Full-audit confirmation tests (functions read as safe, verified empirically) ---
    #
    # update_phone_expense() reads the existing expense row before writing, but
    # only to fill in default field values -- not to decide WHETHER to touch the
    # ledger (it unconditionally reverses-then-reposts every call via a live
    # ledger_links lookup, not a stale snapshot). Two concurrent edits of the
    # same expense are expected to both apply in some serialized order
    # (last-write-wins), not reject one -- this confirms that ends up
    # consistent (exactly one live ledger entry, matching one of the two
    # edits) rather than leaving duplicate or orphaned cash-book rows.
    def test_concurrent_double_edit_phone_expense():
        with db.db_session() as conn:
            p = db.create_phone(conn, c_uid, {
                "model": "Race Expense Phone", "type": "PTA", "purchase_price": 30000,
                "status": "Bought", "purchase_payment_method": "cash",
                "imei": "888800000005555",
            })
            phone_id5 = p["id"]
            exp = db.add_phone_expense(conn, c_uid, phone_id5, {
                "amount": 1000, "description": "Initial", "payment_source": "cash",
            })
            expense_id = exp["id"]

        barrier = threading.Barrier(2)
        errors = []

        def worker(amount):
            try:
                barrier.wait(timeout=5)
                with db.db_session() as conn2:
                    db.update_phone_expense(conn2, c_uid, phone_id5, expense_id, {
                        "amount": amount, "description": f"Edit {amount}", "payment_source": "cash",
                    })
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

        t1 = threading.Thread(target=worker, args=(2000,))
        t2 = threading.Thread(target=worker, args=(3000,))
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"Unexpected errors from concurrent expense edits: {errors}"
        with db.db_session() as conn:
            links = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_type='phone_expense' AND source_id=?",
                (c_uid, expense_id),
            ).fetchone()["c"]
            cb_amount = conn.execute(
                """
                SELECT cb.amount FROM ledger_links ll
                JOIN cash_book_entries cb ON cb.id = ll.cash_book_entry_id
                WHERE ll.user_id=? AND ll.source_type='phone_expense' AND ll.source_id=?
                """,
                (c_uid, expense_id),
            ).fetchone()
        assert links == 1, (
            f"Expected exactly 1 live ledger link after two concurrent expense edits, found {links} "
            f"— duplicate or orphaned cash-book rows from a non-serialized edit."
        )
        assert cb_amount and cb_amount["amount"] in (2000.0, 3000.0), (
            f"Cash-book entry amount {cb_amount} doesn't match either concurrent edit — data corrupted, "
            f"not just last-write-wins."
        )

    run_test("Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)",
              test_concurrent_double_edit_phone_expense)

    # delete_phone() reverses the phone's ledger via a live ledger_links lookup
    # (idempotent by construction: a second reversal finds nothing left to
    # reverse) and then does a plain "DELETE ... WHERE id=?" (idempotent: 0 rows
    # affected the second time, no error). Confirms two concurrent deletes of
    # the same phone don't crash or double-reverse the ledger.
    def test_concurrent_double_delete_phone():
        with db.db_session() as conn:
            cash_before_purchase = db.cash_in_hand_balance(conn, c_uid)
            p = db.create_phone(conn, c_uid, {
                "model": "Race Delete Phone", "type": "PTA", "purchase_price": 42000,
                "status": "Bought", "purchase_payment_method": "cash",
                "imei": "888800000006666",
            })
            phone_id6 = p["id"]

        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                with db.db_session() as conn2:
                    db.delete_phone(conn2, c_uid, phone_id6)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"Unexpected errors from concurrent phone deletes: {errors}"
        with db.db_session() as conn:
            gone = conn.execute("SELECT id FROM phones WHERE id=?", (phone_id6,)).fetchone()
            cash_after = db.cash_in_hand_balance(conn, c_uid)
            links = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_type LIKE 'phone_%' AND source_id=?",
                (c_uid, phone_id6),
            ).fetchone()["c"]
        assert gone is None, "Phone still exists after two concurrent deletes"
        assert cash_after == cash_before_purchase, (
            f"Cash in Hand should net back to its pre-purchase value ({cash_before_purchase}) after "
            f"buying and then deleting the same phone once, but got {cash_after} — the purchase "
            f"reversal ran more than once (double-refund from a double delete)."
        )

    run_test("Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)",
              test_concurrent_double_delete_phone)

    # No "edit invoice" endpoint exists in this codebase (invoices are printable,
    # create-only records) -- the closest real concurrency risk is two
    # near-simultaneous invoice creations racing on the shared auto-numbering
    # counter. create_invoice() already takes BEGIN IMMEDIATE before computing
    # the next number specifically to close this race (see its docstring), so
    # this confirms that protection actually holds under real concurrent
    # threads rather than only in single-threaded logic.
    def test_concurrent_invoice_numbering():
        with db.db_session() as conn:
            p = db.create_phone(conn, c_uid, {
                "model": "Race Invoice Phone", "type": "PTA", "purchase_price": 45000,
                "status": "Sold", "sale_price": 60000,
                "purchase_payment_method": "cash", "sale_payment_method": "cash",
                "imei": "888800000003333",
            })
            phone_id3 = p["id"]

        barrier = threading.Barrier(2)
        errors = []
        invoice_numbers = []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait(timeout=5)
                with db.db_session() as conn2:
                    inv = db.create_invoice(conn2, c_uid, {
                        "customer_name": "Racer", "phone_id": phone_id3,
                        "model": "Race Invoice Phone", "amount": 60000,
                    })
                with lock:
                    invoice_numbers.append(inv["invoice_number"])
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        assert not errors, f"Unexpected errors from concurrent invoice creation: {errors}"
        assert len(invoice_numbers) == 2 and invoice_numbers[0] != invoice_numbers[1], (
            f"Concurrent invoice creation produced colliding/missing invoice numbers: {invoice_numbers}"
        )

    run_test("Concurrent invoice creation gets distinct numbers (confirms existing lock holds)",
              test_concurrent_invoice_numbering)

    # --- Gap coverage: invoice numbers unique per user (bug #7) ---
    def test_duplicate_invoice_number_rejected():
        with db.db_session() as conn:
            p = db.create_phone(conn, c_uid, {
                "model": "Dup Invoice Phone", "type": "PTA", "purchase_price": 30000,
                "status": "Sold", "sale_price": 40000,
                "purchase_payment_method": "cash", "sale_payment_method": "cash",
                "imei": "888800000004444",
            })
            phone_id = p["id"]
            first = db.create_invoice(conn, c_uid, {
                "customer_name": "First Buyer", "phone_id": phone_id,
                "model": "Dup Invoice Phone", "amount": 40000,
            })

        # Simulates the real bug trigger: the billing form pre-fills
        # invoice_number from an existing invoice when you view/reprint it
        # (templates/billing.html), so re-submitting sends that SAME number
        # back as an explicit value on a NEW invoice.
        with db.db_session() as conn:
            try:
                db.create_invoice(conn, c_uid, {
                    "customer_name": "Second Buyer", "phone_id": phone_id,
                    "model": "Dup Invoice Phone", "amount": 40000,
                    "invoice_number": first["invoice_number"],
                })
                raise AssertionError("Expected a duplicate explicit invoice_number to be rejected")
            except ValueError as e:
                assert "already exists" in str(e)

        # Same check for purchase invoices.
        with db.db_session() as conn:
            first_pi = db.create_purchase_invoice(conn, c_uid, {
                "supplier_name": "Dup Supplier", "model": "Dup Invoice Phone", "amount": 30000,
            })
        with db.db_session() as conn:
            try:
                db.create_purchase_invoice(conn, c_uid, {
                    "supplier_name": "Dup Supplier 2", "model": "Dup Invoice Phone", "amount": 30000,
                    "invoice_number": first_pi["invoice_number"],
                })
                raise AssertionError("Expected a duplicate explicit purchase invoice_number to be rejected")
            except ValueError as e:
                assert "already exists" in str(e)

    run_test("Duplicate explicit invoice number is rejected, not silently duplicated",
              test_duplicate_invoice_number_rejected)

    def test_invoice_dedupe_migration_repairs_existing_duplicates():
        # Simulate a customer database that predates this fix: temporarily
        # drop the unique index, insert genuine duplicate rows directly
        # (bypassing create_invoice, the same way old data already on disk
        # would look), then run the same migration init_db() runs on every
        # launch and confirm it repairs the duplicates and the index comes
        # back -- proving existing customer data survives this fix cleanly.
        with db.db_session() as conn:
            conn.execute("DROP INDEX IF EXISTS idx_invoices_user_invoice_unique")
            conn.execute(
                "INSERT INTO invoices (invoice_number, customer_name, invoice_date, user_id) "
                "VALUES (9001, 'Old Row A', date('now'), ?)", (c_uid,)
            )
            conn.execute(
                "INSERT INTO invoices (invoice_number, customer_name, invoice_date, user_id) "
                "VALUES (9001, 'Old Row B (duplicate)', date('now'), ?)", (c_uid,)
            )
            dupe_count = conn.execute(
                "SELECT COUNT(*) c FROM invoices WHERE user_id=? AND invoice_number=9001", (c_uid,)
            ).fetchone()["c"]
            assert dupe_count == 2, "Test setup should have created a real duplicate"

            db._migrate_unique_invoice_numbers(conn)

            rows = conn.execute(
                "SELECT invoice_number, customer_name FROM invoices "
                "WHERE user_id=? AND customer_name IN ('Old Row A', 'Old Row B (duplicate)') "
                "ORDER BY customer_name",
                (c_uid,),
            ).fetchall()
            numbers = {r["customer_name"]: r["invoice_number"] for r in rows}
            assert numbers["Old Row A"] == 9001, "Oldest duplicate should keep its original number"
            assert numbers["Old Row B (duplicate)"] != 9001, (
                "Later duplicate should have been renumbered"
            )

            # Index must exist again and actually enforce uniqueness now.
            index_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_invoices_user_invoice_unique'"
            ).fetchone()
            assert index_exists, "Unique index should be recreated after dedupe"
            try:
                conn.execute(
                    "INSERT INTO invoices (invoice_number, customer_name, invoice_date, user_id) "
                    "VALUES (9001, 'Should Fail', date('now'), ?)", (c_uid,)
                )
                raise AssertionError("Expected the unique index to reject a fresh duplicate insert")
            except sqlite3.IntegrityError:
                pass

    run_test("Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness",
              test_invoice_dedupe_migration_repairs_existing_duplicates)

    # --- Gap coverage: negative cash/bank guard is soft, not a hard block (bug #11) ---
    def test_negative_cash_guard_soft_blocks_then_allows_with_force():
        with db.db_session() as conn:
            u = db.register_user(conn, "neg_cash_user", "pass1234", "", "Neg Cash Shop")
            n_uid = u["user_id"]

        # Starts at 0 cash on purpose -- this test IS about the guard. Let
        # the warning propagate OUT of db_session() (as it would through a
        # real app.py route) so its own rollback actually runs, instead of
        # catching it inside the `with` block and leaving the phone insert
        # that already ran uncommitted-but-visible on the same connection.
        try:
            with db.db_session() as conn:
                db.create_phone(conn, n_uid, {
                    "model": "Guard Test Phone", "type": "PTA", "purchase_price": 10000,
                    "status": "Bought", "purchase_payment_method": "cash",
                })
            raise AssertionError("Expected a cash purchase with insufficient funds to be rejected")
        except db.NegativeBalanceWarning as w:
            assert w.target == "cash"
            assert w.current_balance == 0
            assert w.amount == 10000
            assert w.resulting_balance == -10000

        # Nothing should have been written -- the whole phone insert (and
        # its ledger postings) must roll back together with the warning.
        with db.db_session() as conn:
            count = conn.execute(
                "SELECT COUNT(*) c FROM phones WHERE user_id=?", (n_uid,)
            ).fetchone()["c"]
            assert count == 0, "A rejected purchase must not leave a partial phone row behind"

        # The SAME request with force=True must go through (soft guard, not
        # a hard block -- shopkeepers legitimately record entries out of order).
        with db.db_session() as conn:
            phone = db.create_phone(conn, n_uid, {
                "model": "Guard Test Phone", "type": "PTA", "purchase_price": 10000,
                "status": "Bought", "purchase_payment_method": "cash", "force": True,
            })
            assert phone is not None
            balance = db.cash_in_hand_balance(conn, n_uid)
            assert balance == -10000, f"Expected cash to actually go negative after force=True, got {balance}"

    run_test("Negative cash guard blocks by default, allows through with force=True",
              test_negative_cash_guard_soft_blocks_then_allows_with_force)

    def test_negative_bank_guard_on_withdrawal():
        with db.db_session() as conn:
            u = db.register_user(conn, "neg_bank_user", "pass1234", "", "Neg Bank Shop")
            b_uid = u["user_id"]
            bank = db.create_bank(conn, b_uid, {"name": "Empty Bank", "initial_balance": 0})
            bank_id = bank["id"]

            try:
                db.create_bank_transaction(
                    conn, bank_id, {"transaction_type": "debit", "amount": 5000, "note": "Withdrawal"},
                    user_id=b_uid, mirror_cash_book=True,
                )
                raise AssertionError("Expected a withdrawal exceeding the bank balance to be rejected")
            except db.NegativeBalanceWarning as w:
                assert w.target == "bank"
                assert w.name == "Empty Bank"
                assert w.resulting_balance == -5000

            tx_count = conn.execute(
                "SELECT COUNT(*) c FROM bank_transactions WHERE bank_account_id=?", (bank_id,)
            ).fetchone()["c"]
            assert tx_count == 0, "A rejected withdrawal must not leave a partial bank_transactions row"

        with db.db_session() as conn:
            db.create_bank_transaction(
                conn, bank_id,
                {"transaction_type": "debit", "amount": 5000, "note": "Withdrawal"},
                user_id=b_uid, mirror_cash_book=True, force=True,
            )
            bank_after = db.get_bank(conn, b_uid, bank_id)
            assert bank_after["balance"] == -5000
            # Withdrawal mirrors as cash IN (money into the drawer) -- never
            # guarded, should always succeed regardless of force.
            cash_after = db.cash_in_hand_balance(conn, b_uid)
            assert cash_after == 5000

    run_test("Negative bank guard blocks a withdrawal by default, allows through with force=True",
              test_negative_bank_guard_on_withdrawal)

    def test_negative_cash_guard_on_bank_deposit():
        # A manual bank Deposit pulls cash OUT of the drawer -- if the drawer
        # doesn't have it, this must be guarded exactly like any other cash
        # outflow, even though the primary movement here is bank-side (credit).
        with db.db_session() as conn:
            u = db.register_user(conn, "neg_deposit_user", "pass1234", "", "Neg Deposit Shop")
            d_uid = u["user_id"]
            bank = db.create_bank(conn, d_uid, {"name": "Deposit Target Bank", "initial_balance": 0})
            bank_id = bank["id"]

        # Same reasoning as the cash-purchase test above: let the warning
        # propagate out of db_session() so its rollback actually undoes the
        # bank_transactions row the deposit already inserted before the
        # cash-side mirror check ran, instead of catching it inside the
        # `with` block and observing uncommitted state on the same connection.
        try:
            with db.db_session() as conn:
                db.create_bank_transaction(
                    conn, bank_id, {"transaction_type": "credit", "amount": 2000, "note": "Deposit"},
                    user_id=d_uid, mirror_cash_book=True,
                )
            raise AssertionError("Expected a deposit exceeding cash in hand to be rejected")
        except db.NegativeBalanceWarning as w:
            assert w.target == "cash"
            assert w.resulting_balance == -2000

        with db.db_session() as conn:
            bank_tx_count = conn.execute(
                "SELECT COUNT(*) c FROM bank_transactions WHERE bank_account_id=?", (bank_id,)
            ).fetchone()["c"]
            assert bank_tx_count == 0, (
                "A rejected deposit must not leave a partial bank_transactions row "
                "even though the rejection came from the cash-side check"
            )

    run_test("Negative cash guard also blocks a bank deposit that would overdraw the drawer",
              test_negative_cash_guard_on_bank_deposit)

    # --- Gap coverage: side investment reversal is per-event, not per-partner (bug #8) ---
    def test_side_investment_reversal_is_per_event():
        with db.db_session() as conn:
            u = db.register_user(conn, "side_inv_user", "pass1234", "", "Side Inv Shop")
            si_uid = u["user_id"]
            partner = db.create_partner(conn, si_uid, {"name": "Top-up Partner", "capital": 0})
            partner_id = partner["id"]

            first = db.add_side_investment(conn, si_uid, {
                "partner_id": partner_id, "amount": 50000, "payment_method": "cash",
            })
            second = db.add_side_investment(conn, si_uid, {
                "partner_id": partner_id, "amount": 75000, "payment_method": "cash",
            })
            assert first["investment_id"] != second["investment_id"], (
                "Each side investment must get its own identity, not share the partner's id"
            )

            partner_after_both = db.get_partner(conn, si_uid, partner_id)
            assert partner_after_both["capital"] == 125000

            cb_count_before = conn.execute(
                "SELECT COUNT(*) c FROM cash_book_entries WHERE user_id=? AND note LIKE 'Side investment%'",
                (si_uid,),
            ).fetchone()["c"]
            assert cb_count_before == 2

        # Reversing the FIRST top-up must only undo that one event -- the
        # second top-up's cash book entry and capital contribution must
        # survive untouched. This is exactly the bug: source_id used to be
        # the partner's own id, shared by both top-ups, so reversing one
        # could wipe out both.
        with db.db_session() as conn:
            result = db.reverse_side_investment(conn, si_uid, first["investment_id"])
            assert result["reversed_amount"] == 50000

            partner_after_reverse = db.get_partner(conn, si_uid, partner_id)
            assert partner_after_reverse["capital"] == 75000, (
                f"Expected only the reversed 50000 to come off capital, got {partner_after_reverse['capital']}"
            )

            cb_count_after = conn.execute(
                "SELECT COUNT(*) c FROM cash_book_entries WHERE user_id=? AND note LIKE 'Side investment%'",
                (si_uid,),
            ).fetchone()["c"]
            assert cb_count_after == 1, (
                "Reversing one side investment deleted more than its own cash book entry"
            )

            still_there = conn.execute(
                "SELECT COUNT(*) c FROM side_investments WHERE id = ?", (second["investment_id"],)
            ).fetchone()["c"]
            assert still_there == 1, "The other top-up's own record should be untouched"

    run_test("Reversing one side investment doesn't touch the partner's other top-ups",
              test_side_investment_reversal_is_per_event)

    def test_side_investment_reversal_refuses_ambiguous_legacy_data():
        # Simulate data from BEFORE this fix: two independent top-ups whose
        # ledger_links both used source_id=partner_id (ambiguous -- can't
        # tell which cash book entry belongs to which top-up). reversal must
        # refuse instead of guessing / deleting both.
        with db.db_session() as conn:
            u = db.register_user(conn, "side_inv_legacy_user", "pass1234", "", "Legacy Shop")
            lg_uid = u["user_id"]
            partner = db.create_partner(conn, lg_uid, {"name": "Legacy Partner", "capital": 0})
            partner_id = partner["id"]

            cb1 = db._create_cash_book_synced(conn, lg_uid, {
                "entry_type": "in", "amount": 20000, "note": "Legacy top-up 1",
                "entry_date": "2026-01-01",
            }, source_type="side_investment", source_id=partner_id)
            cb2 = db._create_cash_book_synced(conn, lg_uid, {
                "entry_type": "in", "amount": 30000, "note": "Legacy top-up 2",
                "entry_date": "2026-01-02",
            }, source_type="side_investment", source_id=partner_id)
            assert cb1 and cb2

            link_count = conn.execute(
                "SELECT COUNT(*) c FROM ledger_links WHERE user_id=? AND source_type='side_investment' AND source_id=?",
                (lg_uid, partner_id),
            ).fetchone()["c"]
            assert link_count == 2, "Test setup should reproduce the ambiguous legacy shape"

            try:
                db.reverse_side_investment(conn, lg_uid, partner_id)
                raise AssertionError("Expected reversal of ambiguous legacy data to be refused")
            except ValueError as e:
                assert "ambiguous" in str(e).lower()

            # Neither legacy cash book entry should have been touched.
            remaining = conn.execute(
                "SELECT COUNT(*) c FROM cash_book_entries WHERE user_id=? AND note LIKE 'Legacy top-up%'",
                (lg_uid,),
            ).fetchone()["c"]
            assert remaining == 2, "Refused reversal must not delete anything"

    run_test("Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing",
              test_side_investment_reversal_refuses_ambiguous_legacy_data)

    # --- Gap coverage: licensing lifecycle ---
    #
    # There is no license server and no deactivate/reissue endpoint in this
    # product (see license_guard.py's own docstring: it's a purely client-side,
    # hardware-ID-signed check). "Deactivate" is simulated here the only way a
    # real user could trigger it -- deleting the local license.json -- since
    # that's the entire mechanism that exists to revoke a local activation.
    def test_license_lifecycle():
        scratch_dir = Path(tempfile.mkdtemp(prefix="crm_license_test_"))
        os.environ["CRM_LICENSE_PATH"] = str(scratch_dir / "license.json")
        import license_guard as lic

        hw_a = "AAAA1111BBBB2222"
        hw_b = "CCCC3333DDDD4444"
        key_a = lic._sign_hardware_id(hw_a)

        assert lic.verify_activation_key(hw_a, key_a) is True
        assert lic.verify_activation_key(hw_b, key_a) is False, (
            "A key issued/activated for one hardware ID verified successfully against a "
            "different hardware ID — activation would work on any machine."
        )

        original_get_hw = lic.get_hardware_id
        try:
            lic.get_hardware_id = lambda: hw_a
            lic.save_license(key_a)
            assert lic.is_licensed() is True

            # Same license.json "copied" to a second machine (different hardware ID)
            lic.get_hardware_id = lambda: hw_b
            assert lic.is_licensed() is False, (
                "A license file activated on Machine A reported as licensed on Machine B."
            )

            # Deactivate (remove local license) on Machine A
            lic.get_hardware_id = lambda: hw_a
            lic.LICENSE_FILE.unlink()
            assert lic.is_licensed() is False

            # Reissue a fresh key for the same hardware ID and reactivate
            key_a2 = lic._sign_hardware_id(hw_a)
            lic.save_license(key_a2)
            assert lic.is_licensed() is True
        finally:
            lic.get_hardware_id = original_get_hw

    run_test("License activation is hardware-bound; reuse on another machine fails", test_license_lifecycle)

    # Forgot-password OTP flow, exercised end to end through the real app logic
    # (OTP generation/storage/expiry, email content, login with the new
    # password). The SMTP transport itself is faked (smtplib.SMTP swapped for
    # an in-memory stub) rather than hitting real Gmail — sending live email
    # and holding real Gmail App Password credentials in an automated test
    # suite isn't appropriate. This still exercises send_otp_email's own
    # control flow (including its auth-failure -> clear-ValueError conversion).
    def test_forgot_password_otp_flow():
        import email_service
        import smtplib

        class _FakeSMTP:
            sent = []

            def __init__(self, host, port, timeout=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self):
                pass

            def login(self, user, pwd):
                if pwd != "validapppassword":
                    raise smtplib.SMTPAuthenticationError(535, b"bad creds")

            def send_message(self, msg):
                _FakeSMTP.sent.append(msg)

        original_smtp = email_service.smtplib.SMTP
        email_service.smtplib.SMTP = _FakeSMTP
        try:
            with db.db_session() as conn:
                ou = db.register_user(conn, "otp_stress", "otppass123", "otp_stress@example.com", "OTP Shop")
                o_uid = ou["user_id"]
                # Bug #4: request_password_reset() used to always read Gmail
                # SMTP settings from the first-ever registered user in the DB,
                # regardless of who was actually requesting the reset --
                # silently sending (or trying to send) using a stranger's
                # mailbox. It must now resolve strictly from the REQUESTING
                # user's own settings. Prove isolation first: configure valid
                # SMTP creds on the admin (first) user only, leave the
                # requesting user's own settings empty, and confirm the
                # requester's reset falls back to the vendor message instead
                # of silently borrowing the admin's credentials.
                admin_id = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()["id"]
                db.update_user_settings(conn, admin_id, {
                    "gmail_smtp_user": "admin@example.com",
                    "gmail_smtp_app_password": "validapppassword",
                })

            with db.db_session() as conn:
                result = db.request_password_reset(conn, "otp_stress@example.com")
                assert result["ok"] is True and result["email_sent"] is False, (
                    "Requesting user has no SMTP settings of their own -- must not "
                    "silently send using the admin user's credentials"
                )
                assert result["vendor_fallback"] is True

            # Now configure the REQUESTING user's own SMTP settings -- only
            # then should sending actually work.
            with db.db_session() as conn:
                db.update_user_settings(conn, o_uid, {
                    "gmail_smtp_user": "otp_stress@example.com",
                    "gmail_smtp_app_password": "validapppassword",
                })

            with db.db_session() as conn:
                result = db.request_password_reset(conn, "otp_stress@example.com")
                assert result["ok"] is True and result["email_sent"] is True
                token_row = conn.execute(
                    "SELECT otp, expires_at FROM password_reset_tokens WHERE user_id=? ORDER BY id DESC LIMIT 1",
                    (o_uid,),
                ).fetchone()
                otp = token_row["otp"]

            # Wrong OTP is rejected
            with db.db_session() as conn:
                try:
                    db.verify_otp_and_reset_password(conn, "otp_stress@example.com", "000000", "irrelevant1")
                    raise AssertionError("Expected wrong OTP to be rejected")
                except ValueError as e:
                    assert "Invalid" in str(e)

            # Correct OTP resets the password end to end
            with db.db_session() as conn:
                out = db.verify_otp_and_reset_password(conn, "otp_stress@example.com", otp, "newpassword1")
                assert out["ok"] is True
                assert db.verify_login(conn, "otp_stress", "newpassword1") is not None
                assert db.verify_login(conn, "otp_stress", "otppass123") is None

            # Re-using the same (now-consumed) OTP fails
            with db.db_session() as conn:
                try:
                    db.verify_otp_and_reset_password(conn, "otp_stress@example.com", otp, "anotherpass1")
                    raise AssertionError("Expected already-used OTP to be rejected")
                except ValueError:
                    pass

            # Bad Gmail App Password on the REQUESTING user surfaces as a
            # clear ValueError, not a raw crash -- and admin's still-valid
            # credentials must not be used as a silent fallback here either.
            with db.db_session() as conn:
                db.update_user_settings(conn, o_uid, {"gmail_smtp_app_password": "wrongpassword"})
            with db.db_session() as conn:
                try:
                    db.request_password_reset(conn, "otp_stress@example.com")
                    raise AssertionError("Expected bad Gmail App Password to raise a clear error")
                except ValueError as e:
                    assert "App Password" in str(e)
        finally:
            email_service.smtplib.SMTP = original_smtp

    run_test("Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)",
              test_forgot_password_otp_flow)

    # --- Gap coverage: per-user restore (bug #1 / #2) ---
    #
    # restore_database_from_backup used to be a full-file copy: restoring ANY
    # user's backup replaced the entire shared crm.db, destroying every other
    # account's data. It's now a per-user logical restore -- only the
    # requesting user's rows are touched, across every user-owned table in
    # the schema (discovered dynamically, not a hardcoded list).
    def test_restore_is_per_user_only():
        with db.db_session() as conn:
            user_a = db.register_user(conn, "restore_user_a", "pass1234", "", "Shop A")["user_id"]
            user_b = db.register_user(conn, "restore_user_b", "pass1234", "", "Shop B")["user_id"]
            db.update_storage_settings(conn, user_a, {"local_backup_path": str(Path(tempfile.gettempdir()) / "crm_restore_test_backups")})
            db.update_storage_settings(conn, user_b, {"local_backup_path": str(Path(tempfile.gettempdir()) / "crm_restore_test_backups")})
            acct_a = db.create_account(conn, user_a, {"name": "A Original Account", "contact": "0300"})
            acct_b = db.create_account(conn, user_b, {"name": "B Untouched Account", "contact": "0311"})

        # Snapshot user B's full state before anything else happens, to prove
        # it is byte-for-byte unaffected by user A's restore later.
        with db.db_session() as conn:
            b_accounts_before = [dict(r) for r in conn.execute(
                "SELECT * FROM accounts WHERE user_id=?", (user_b,)
            ).fetchall()]
            b_phones_before = [dict(r) for r in conn.execute(
                "SELECT * FROM phones WHERE user_id=?", (user_b,)
            ).fetchall()]

        # Take user A's backup (into their own configured backup folder).
        import backup_service
        backup_path = backup_service.backup_user_data(user_a, force=True)
        assert backup_path, "Expected a backup file path for user A"

        # Now user A changes data AFTER the backup (renames the account,
        # adds a phone) -- restore should revert exactly this.
        with db.db_session() as conn:
            conn.execute(
                "UPDATE accounts SET name = 'A Changed Post-Backup' WHERE id = ?",
                (acct_a["id"],),
            )
            db.create_phone(conn, user_a, {
                "model": "Post-Backup Phone", "type": "PTA",
                "purchase_price": 50000, "status": "Bought", "force": True,
            })

        db.restore_database_from_backup(backup_path, user_a)

        with db.db_session() as conn:
            a_account = conn.execute(
                "SELECT name FROM accounts WHERE id = ?", (acct_a["id"],)
            ).fetchone()
            assert a_account["name"] == "A Original Account", (
                "Restore should have reverted user A's account name"
            )
            a_phone_count = conn.execute(
                "SELECT COUNT(*) c FROM phones WHERE user_id=?", (user_a,)
            ).fetchone()["c"]
            assert a_phone_count == 0, (
                "Restore should have removed the phone user A added after the backup"
            )

            b_accounts_after = [dict(r) for r in conn.execute(
                "SELECT * FROM accounts WHERE user_id=?", (user_b,)
            ).fetchall()]
            b_phones_after = [dict(r) for r in conn.execute(
                "SELECT * FROM phones WHERE user_id=?", (user_b,)
            ).fetchall()]
            assert b_accounts_after == b_accounts_before, (
                "User B's accounts changed as a side effect of user A's restore"
            )
            assert b_phones_after == b_phones_before, (
                "User B's phones changed as a side effect of user A's restore"
            )

    run_test("Restore only touches the requesting user's rows, others untouched",
              test_restore_is_per_user_only)

    def test_restore_rejects_path_traversal_and_other_users_backup():
        # Look up the two users created in the previous test by username, so
        # this test doesn't depend on run order beyond having already run.
        with db.db_session() as conn:
            row_a = conn.execute("SELECT id FROM users WHERE username='restore_user_a'").fetchone()
            row_b = conn.execute("SELECT id FROM users WHERE username='restore_user_b'").fetchone()
            user_a, user_b = row_a["id"], row_b["id"]
            settings_a = db.get_storage_settings(conn, user_a)

        import backup_service
        backup_b_path = backup_service.backup_user_data(user_b, force=True)
        assert backup_b_path

        # User A must not be able to restore User B's backup file, even
        # though both currently share the same configured backup folder.
        try:
            db.restore_database_from_backup(backup_b_path, user_a)
            raise AssertionError("Expected restoring another user's backup file to be rejected")
        except ValueError:
            pass

        # A real .db file that exists but sits outside the user's configured
        # backup folder (path traversal / arbitrary path) must be rejected,
        # even though it passes every other validation check.
        backup_dir = Path(settings_a["local_backup_path"])
        outside_dir = Path(tempfile.mkdtemp(prefix="crm_restore_outside_"))
        outside_db = outside_dir / "x_crm_backup_x.db"
        # Build it as a genuinely valid CRM db so only the path check can reject it.
        with db.db_session() as conn:
            snap_conn = sqlite3.connect(str(outside_db))
            try:
                conn.backup(snap_conn)
            finally:
                snap_conn.close()
        traversal_path = str(backup_dir / ".." / outside_dir.name / outside_db.name)
        for bad_path in (
            str(outside_db),          # outside the allowed folder entirely
            traversal_path,           # "../<other dir>/..." from inside the allowed folder
            str(backup_dir / "does_not_exist_crm_backup_x.db"),  # inside folder but missing
        ):
            try:
                db.restore_database_from_backup(bad_path, user_a)
                raise AssertionError(f"Expected path to be rejected: {bad_path}")
            except ValueError:
                pass

    run_test("Restore rejects path traversal and another user's backup file",
              test_restore_rejects_path_traversal_and_other_users_backup)

    # --- Gap coverage: backup/restore across a schema migration ---
    #
    # CURRENT_SCHEMA_VERSION is still 1 in this codebase (no real migration has
    # shipped yet through the versioned system added for this purpose), so
    # there's nothing real to restore "across." This test registers a
    # synthetic v2 migration for the duration of the test to validate the
    # *mechanism* the moment a real one ships: a backup taken on an older
    # schema, then restored (per-user) after the live app has already
    # migrated forward, must come in through the current schema -- not
    # silently corrupt data or crash on a column mismatch.
    def test_backup_restore_across_migration():
        with db.db_session() as conn:
            user_id = db.register_user(conn, "restore_migration_user", "pass1234", "", "Migration Shop")["user_id"]
            acct = db.create_account(conn, user_id, {"name": "Pre-Migration Account", "contact": "0322"})
            version_before = conn.execute("PRAGMA user_version").fetchone()[0]
            scratch = Path(tempfile.mkdtemp(prefix="crm_migration_backup_"))
            db.update_storage_settings(conn, user_id, {"local_backup_path": str(scratch)})
            slug = db.backup_username_slug(conn, user_id)
        assert version_before == db.CURRENT_SCHEMA_VERSION

        old_backup_path = scratch / f"{slug}_crm_backup_v1.db"
        with db.db_session() as conn:
            backup_conn = sqlite3.connect(str(old_backup_path))
            try:
                conn.backup(backup_conn)
            finally:
                backup_conn.close()

        def _fake_migration_v2(conn):
            conn.execute(
                "CREATE TABLE IF NOT EXISTS _test_migration_v2_marker (id INTEGER PRIMARY KEY, note TEXT)"
            )
            conn.execute("INSERT INTO _test_migration_v2_marker (note) VALUES ('migrated')")
            if not db._column_exists(conn, "accounts", "migration_v2_column"):
                conn.execute(
                    "ALTER TABLE accounts ADD COLUMN migration_v2_column TEXT NOT NULL DEFAULT 'v2_default'"
                )

        original_version = db.CURRENT_SCHEMA_VERSION
        original_migrations = db.SCHEMA_MIGRATIONS
        db.CURRENT_SCHEMA_VERSION = 2
        db.SCHEMA_MIGRATIONS = ((2, _fake_migration_v2),)
        try:
            pre_migration_dir = db.DB_PATH.parent / "pre_migration_backups"
            before_backups = set(pre_migration_dir.glob("*.db")) if pre_migration_dir.exists() else set()

            db.init_db()  # simulate relaunching the app after an update shipping v2

            with db.db_session() as conn:
                v = conn.execute("PRAGMA user_version").fetchone()[0]
                assert v == 2, f"Expected schema version 2 after migration, got {v}"
                marker = conn.execute(
                    "SELECT COUNT(*) c FROM _test_migration_v2_marker"
                ).fetchone()["c"]
                assert marker == 1

            after_backups = set(pre_migration_dir.glob("*.db")) if pre_migration_dir.exists() else set()
            assert after_backups - before_backups, (
                "Expected a timestamped pre-migration backup file to be created automatically"
            )

            # Delete the account live (simulating data changed after the old
            # backup was taken), then restore that user from the pre-migration
            # (schema v1) backup -- restore must migrate its scratch copy to
            # v2 internally before importing, and the LIVE db's own schema
            # version must never move backwards.
            with db.db_session() as conn:
                conn.execute("DELETE FROM accounts WHERE id = ?", (acct["id"],))
                # This synthetic marker table has no owner and only existed to
                # prove the migration ran (already asserted above) -- it's not
                # part of the real per-user schema, so drop it before restore
                # rather than teaching the ownership resolver to special-case
                # a test-only table. A genuinely un-owned table appearing in
                # a real migration should keep failing restore loudly.
                conn.execute("DROP TABLE IF EXISTS _test_migration_v2_marker")

            db.restore_database_from_backup(str(old_backup_path), user_id)

            with db.db_session() as conn:
                v_after_restore = conn.execute("PRAGMA user_version").fetchone()[0]
                assert v_after_restore == 2, (
                    f"Live schema version must not revert on a per-user restore, got {v_after_restore}"
                )
                restored = conn.execute(
                    "SELECT * FROM accounts WHERE id = ?", (acct["id"],)
                ).fetchone()
                assert restored is not None, "Account from the v1 backup should have been restored"
                assert restored["name"] == "Pre-Migration Account"
                assert restored["migration_v2_column"] == "v2_default", (
                    "Row restored from an older-schema backup should carry the "
                    "new column's default, added by migrating the scratch copy "
                    "before import -- not be missing it or crash"
                )
        finally:
            db.CURRENT_SCHEMA_VERSION = original_version
            db.SCHEMA_MIGRATIONS = original_migrations

    run_test("Backup taken pre-migration restores and cleanly re-migrates after a schema bump",
              test_backup_restore_across_migration)

    # --- Gap coverage: restore while another connection holds the DB open (bug #2) ---
    #
    # The old restore did a raw shutil.copy2 straight onto the live db file --
    # risky if anything else has it open (locked/torn copy, worst on Windows).
    # Restore now goes through the same WAL + busy_timeout connection every
    # other write in this app already uses, plus an explicit WAL checkpoint
    # and post-restore integrity check. This proves a concurrent open
    # connection during a restore doesn't corrupt the database.
    def test_restore_with_concurrent_open_connection():
        with db.db_session() as conn:
            user_id = db.register_user(
                conn, "restore_concurrent_user", "pass1234", "", "Concurrent Shop"
            )["user_id"]
            acct = db.create_account(conn, user_id, {"name": "Concurrent Original", "contact": "0333"})
            scratch = Path(tempfile.mkdtemp(prefix="crm_concurrent_backup_"))
            db.update_storage_settings(conn, user_id, {"local_backup_path": str(scratch)})

        import backup_service
        backup_path = backup_service.backup_user_data(user_id, force=True)
        assert backup_path

        # Change data after the backup so restore has something real to revert.
        with db.db_session() as conn:
            conn.execute(
                "UPDATE accounts SET name='Concurrent Changed' WHERE id=?", (acct["id"],)
            )

        # Hold an open read transaction on another connection/thread
        # throughout the restore, simulating a request mid-read while a
        # restore runs concurrently.
        hold_ready = threading.Event()
        release_hold = threading.Event()
        holder_error = []

        def _hold_open_transaction():
            conn = db.get_connection()
            try:
                conn.execute("BEGIN")
                conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
                hold_ready.set()
                release_hold.wait(timeout=10)
            except Exception as e:
                holder_error.append(e)
            finally:
                try:
                    conn.rollback()
                except Exception:
                    pass
                conn.close()

        t = threading.Thread(target=_hold_open_transaction, daemon=True)
        t.start()
        hold_ready.wait(timeout=5)
        try:
            db.restore_database_from_backup(backup_path, user_id)
        finally:
            release_hold.set()
            t.join(timeout=10)

        assert not holder_error, f"Concurrent reader errored: {holder_error}"

        with db.db_session() as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            assert integrity == "ok", f"DB integrity check failed after concurrent restore: {integrity}"
            restored = conn.execute(
                "SELECT name FROM accounts WHERE id=?", (acct["id"],)
            ).fetchone()
            assert restored["name"] == "Concurrent Original", (
                "Restore did not correctly revert data despite a concurrent open connection"
            )

    run_test("Restore succeeds cleanly with a concurrent open connection (no corruption)",
              test_restore_with_concurrent_open_connection)

    # --- Gap coverage: updater path resolution on Windows vs Mac (bug #3) ---
    #
    # _resolve_target() in update_service.py used to append "Phone Reseller
    # CRM" onto customer_install_dir() a second time on Windows, since that
    # helper already returns the app's own onedir folder there (unlike on
    # Mac, where it walks back out of Contents/MacOS/ to the folder
    # containing the .app bundle). That produced a path one directory too
    # deep, so Windows installs could resolve an update but never apply it.
    # This simulates both real on-disk layouts in a tmp dir (no actual
    # install needed) and asserts the resolved app_dir/launcher/install_dir
    # are the real, existing paths on each platform.
    def test_update_target_resolution_windows_and_mac():
        import update_service

        original_platform = sys.platform
        original_executable = sys.executable
        had_frozen = hasattr(sys, "frozen")
        original_frozen = getattr(sys, "frozen", None)

        def _set_frozen(exe_path, platform):
            sys.platform = platform
            sys.frozen = True
            sys.executable = str(exe_path)

        def _restore():
            sys.platform = original_platform
            sys.executable = original_executable
            if had_frozen:
                sys.frozen = original_frozen
            elif hasattr(sys, "frozen"):
                del sys.frozen

        try:
            # --- Windows onedir layout ---
            with tempfile.TemporaryDirectory(prefix="crm_update_win_") as tmp:
                root = Path(tmp).resolve()
                app_dir = root / "Phone Reseller CRM"
                (app_dir / "_internal").mkdir(parents=True)
                (root / "Data").mkdir()
                exe = app_dir / "Phone Reseller CRM.exe"
                exe.write_text("stub")

                _set_frozen(exe, "win32")
                try:
                    target = update_service._resolve_target()
                finally:
                    _restore()

                assert target["kind"] == "windows_onedir"
                assert target["app_dir"] == app_dir, (
                    f"Expected app_dir={app_dir}, got {target['app_dir']}"
                )
                assert target["launcher"] == exe
                assert target["install_dir"] == root, (
                    "install_dir should be the folder containing both the app "
                    f"dir and Data/, got {target['install_dir']}"
                )
                assert target["app_dir"].is_dir() and target["launcher"].is_file(), (
                    "Resolved Windows paths should point at real, existing paths"
                )

            # --- Mac .app bundle layout ---
            with tempfile.TemporaryDirectory(prefix="crm_update_mac_") as tmp:
                root = Path(tmp).resolve()
                bundle = root / "Phone Reseller CRM.app"
                macos_dir = bundle / "Contents" / "MacOS"
                macos_dir.mkdir(parents=True)
                (bundle / "Contents" / "Info.plist").write_text("<plist/>")
                launcher = macos_dir / "PhoneResellerCRM"
                launcher.write_text("stub")

                _set_frozen(launcher, "darwin")
                try:
                    target = update_service._resolve_target()
                finally:
                    _restore()

                assert target["kind"] == "mac_app"
                assert target["app_bundle"] == bundle
                assert target["launcher"] == launcher
                assert target["install_dir"] == root
                assert target["app_bundle"].is_dir() and target["launcher"].is_file()
        finally:
            _restore()

    run_test("Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)",
              test_update_target_resolution_windows_and_mac)

    # --- Stress load ---
    STRESS_PHONES = 200
    STRESS_BULK = 50
    t_stress = time.perf_counter()

    with db.db_session() as conn:
        # Bulk create phones
        t0 = time.perf_counter()
        # force=True throughout this load-generation section: it's testing
        # sync/throughput at volume, not realistic cash discipline (which
        # bug #11's dedicated tests below cover) -- without it, this
        # section would correctly (but unhelpfully) trip the new negative-
        # balance guard partway through.
        created = db.create_phones_bulk(conn, user_id, {
            "model": "Stress iPhone 15",
            "type": "PTA",
            "quantity": STRESS_BULK,
            "purchase_price": 85000,
            "status": "Bought",
            "purchase_payment_method": "cash",
            "imeis": [{"imei": f"35693803564{i:04d}", "imei2": ""} for i in range(STRESS_BULK)],
            "force": True,
        })
        bulk_ms = (time.perf_counter() - t0) * 1000
        report.stats["bulk_create_50_phones_ms"] = round(bulk_ms, 1)
        stress_phone_ids = [p["id"] for p in created]

        # Mark half sold
        t0 = time.perf_counter()
        items = [{"phone_id": pid, "sale_price": 100000} for pid in stress_phone_ids[:25]]
        db.bulk_mark_sold(conn, user_id, items)
        bulk_sold_ms = (time.perf_counter() - t0) * 1000
        report.stats["bulk_sold_25_phones_ms"] = round(bulk_sold_ms, 1)

        # More individual phones with mixed payments
        for i in range(STRESS_PHONES - STRESS_BULK):
            method = "bank" if i % 3 == 0 else "cash"
            data = {
                "model": f"Stress Unit {i}",
                "type": "PTA" if i % 2 == 0 else "NON-PTA",
                "purchase_price": 70000 + (i * 100),
                "status": "Bought",
                "purchase_payment_method": method,
                "imei": f"9900000000{i:05d}",
                "force": True,
            }
            if method == "bank":
                data["purchase_bank_id"] = bank_id
            if i % 5 == 0:
                data["payable_amount"] = 20000
                data["supplier_account_id"] = supplier_id
            p = db.create_phone(conn, user_id, data)
            if i % 7 == 0:
                db.update_phone(conn, user_id, p["id"], {
                    "status": "Sold",
                    "sale_price": data["purchase_price"] + 15000,
                    "sale_payment_method": "cash",
                })

        # Cash book entries
        for i in range(100):
            db.create_cash_book_entry(conn, user_id, {
                "entry_type": "out" if i % 2 else "in",
                "amount": 1000 + i * 10,
                "note": f"Stress CB {i}",
                "payment_source": "cash",
                "force": True,
            })

        # Account entries
        for i in range(50):
            db.create_entry(conn, food_id, {
                "entry_type": "credit",
                "amount": 500 + i * 5,
                "note": f"Meal {i}",
                "payment_source": "cash",
                "force": True,
            }, user_id=user_id)

        # Journal vouchers
        for i in range(20):
            db.create_journal_voucher(conn, user_id, {
                "debit_account_id": supplier_id,
                "credit_account_id": buyer_id,
                "amount": 1000 + i * 100,
                "narration": f"JV stress {i}",
            })

        # Collect final counts
        report.stats["phones_total"] = count_table(conn, "phones", user_id)
        report.stats["phones_sold"] = conn.execute(
            "SELECT COUNT(*) c FROM phones WHERE user_id=? AND status='Sold'", (user_id,)
        ).fetchone()["c"]
        report.stats["phones_bought"] = conn.execute(
            "SELECT COUNT(*) c FROM phones WHERE user_id=? AND status='Bought'", (user_id,)
        ).fetchone()["c"]
        report.stats["cash_book_entries"] = count_table(conn, "cash_book_entries", user_id)
        report.stats["ledger_links"] = count_table(conn, "ledger_links", user_id)
        report.stats["account_entries"] = conn.execute(
            """
            SELECT COUNT(*) c FROM account_entries ae
            JOIN accounts a ON a.id = ae.account_id WHERE a.user_id=?
            """,
            (user_id,),
        ).fetchone()["c"]
        report.stats["bank_transactions"] = conn.execute(
            """
            SELECT COUNT(*) c FROM bank_transactions bt
            JOIN bank_accounts ba ON ba.id = bt.bank_account_id WHERE ba.user_id=?
            """,
            (user_id,),
        ).fetchone()["c"]
        report.stats["journal_vouchers"] = count_table(conn, "journal_vouchers", user_id)
        report.stats["return_logs"] = count_table(conn, "return_logs", user_id)

        report.stats["orphan_ledger_cash_links"] = orphan_ledger_links(conn, user_id)
        report.stats["orphan_ledger_account_links"] = orphan_account_links(conn, user_id)

        report.stats["cash_in_hand"] = db.cash_in_hand_balance(conn, user_id)
        report.stats["total_in_bank"] = db.total_bank_balance(conn, user_id)

        dash = db.compute_dashboard(conn, user_id)
        report.stats["dashboard_net_profit"] = dash["total_net_profit"]
        report.stats["dashboard_udhar"] = dash["total_udhar"]
        report.stats["dashboard_stock_worth"] = dash["active_stock_worth"]

        today = db.compute_today_summary(conn, user_id)
        report.stats["today_sold"] = today["phones_sold"]
        report.stats["today_bought"] = today["phones_bought"]

        # Sync integrity checks
        if report.stats["orphan_ledger_cash_links"] > 0:
            report.add("No orphan cash ledger links", False,
                       f"Found {report.stats['orphan_ledger_cash_links']} orphans")
        else:
            report.add("No orphan cash ledger links", True)

        if report.stats["orphan_ledger_account_links"] > 0:
            report.add("No orphan account ledger links", False,
                       f"Found {report.stats['orphan_ledger_account_links']} orphans")
        else:
            report.add("No orphan account ledger links", True)

        # Delete 30 phones and verify ledger cleanup
        to_delete = conn.execute(
            "SELECT id FROM phones WHERE user_id=? AND status='Bought' LIMIT 30",
            (user_id,),
        ).fetchall()
        links_before = count_table(conn, "ledger_links", user_id)
        cb_before = count_table(conn, "cash_book_entries", user_id)
        for row in to_delete:
            db.delete_phone(conn, user_id, row["id"])
        links_after = count_table(conn, "ledger_links", user_id)
        cb_after = count_table(conn, "cash_book_entries", user_id)
        if links_after >= links_before:
            report.add("Bulk delete reduces ledger links", False,
                       f"links {links_before} -> {links_after}")
        else:
            report.add("Bulk delete reduces ledger links", True,
                       f"links {links_before} -> {links_after}, cb {cb_before} -> {cb_after}")

    report.stats["stress_total_ms"] = round((time.perf_counter() - t_stress) * 1000, 1)
    report.stats["db_path"] = db_path
    report.stats["db_size_mb"] = round(Path(db_path).stat().st_size / (1024 * 1024), 2)

    # Resolved in v2.3.0 — kept for historical regression notes only.
    if False:
        report.warn("placeholder")

    return report


def render_markdown(r: StressReport) -> str:
    passed = sum(1 for t in r.results if t.passed)
    failed = sum(1 for t in r.results if not t.passed)
    lines = [
        "# Mobile CRM - Logic Review & Stress Test Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Database:** `{r.stats.get('db_path', '-')}` ({r.stats.get('db_size_mb', 0)} MB)",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tests passed | **{passed}** |",
        f"| Tests failed | **{failed}** |",
        f"| Warnings | {len(r.warnings)} |",
        "",
        "## Stress load results",
        "",
        "| Metric | Count / Value |",
        "|--------|---------------|",
    ]
    for k, v in sorted(r.stats.items()):
        if k not in ("db_path",):
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")

    lines.extend(["", "## Test results", ""])
    for t in r.results:
        icon = "PASS" if t.passed else "**FAIL**"
        lines.append(f"- [{icon}] **{t.name}** - {t.detail.split(chr(10))[0]}")

    if r.errors:
        lines.extend(["", "## Failures (detail)", ""])
        for e in r.errors:
            lines.append(f"```\n{e}\n```")

    lines.extend(["", "## Sync architecture verified", ""])
    lines.extend([
        "- Inventory purchase/sale/borrow -> cash book + accounts via `ledger_links`",
        "- Phone expenses -> cash book out (+ optional account)",
        "- Account Wasool (debit) -> cash book in",
        "- Expense category credit (Food) -> cash book out",
        "- Delete phone / account entry / cash book / journal -> cascade reversal",
        "- Returns post refunds without duplicate account rows",
    ])

    lines.extend(["", "## Known limitations (not blocking)", ""])
    for w in r.warnings:
        lines.append(f"- {w}")

    lines.extend(["", "## Recommendations", ""])
    recs = [
        "Keep pytest CI green on every push to Version007.",
        "Invoices remain print-only records; sales post through inventory.",
    ]
    if failed == 0:
        recs.insert(0, "All automated sync tests passed under stress load - core ledger logic is consistent.")
    for rec in recs:
        lines.append(f"- {rec}")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Mobile CRM stress test starting...")
    print(f"DB: {os.environ['CRM_DB_PATH']}")
    result = main()
    md = render_markdown(result)
    out_dir = Path(__file__).resolve().parent.parent / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "CRM_STRESS_TEST_REPORT.md"
    out_file.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nReport saved: {out_file}")
    passed = sum(1 for t in result.results if t.passed)
    failed = sum(1 for t in result.results if not t.passed)
    sys.exit(1 if failed else 0)
