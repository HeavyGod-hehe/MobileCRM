"""Regression tests for architecture/money fixes (partial udhar + supplier bills)."""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

_fd, _DB = tempfile.mkstemp(suffix="_finalize_coverage.db")
os.close(_fd)
os.environ["CRM_DB_PATH"] = _DB
os.environ["CRM_SKIP_LICENSE"] = "1"

import database as db  # noqa: E402
import app as crm_app  # noqa: E402


def _fresh_user(conn, username: str, cash: float = 100_000, capital: float = 100_000):
    u = db.register_user(conn, username, "pass1234", "", f"{username} Shop")
    uid = u["user_id"]
    db.update_user_settings(conn, uid, {"cash_in_hand": str(cash), "setup_completed": "1"})
    db.create_partner(conn, uid, {"name": "Owner", "capital": capital})
    return uid


class FinalizeCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(_DB + suffix).unlink(missing_ok=True)
            except OSError:
                pass

    def test_unsold_phone_expense_does_not_open_liquidity_gap(self):
        with db.db_session() as conn:
            uid = _fresh_user(conn, "unsold_expense_gap")
            self.assertAlmostEqual(db.compute_dashboard(conn, uid)["liquidity_gap"], 0.0, places=2)
            phone = db.create_phone(conn, uid, {
                "model": "Gap Phone", "condition": "10/10", "type": "PTA",
                "purchase_price": 50000, "status": "Bought",
                "purchase_payment_method": "cash", "payable_amount": 0,
            })
            dash_before = db.compute_dashboard(conn, uid)
            db.add_phone_expense(conn, uid, phone["id"], {
                "amount": 3500, "description": "Screen repair", "payment_source": "cash",
            })
            dash_after = db.compute_dashboard(conn, uid)
            self.assertAlmostEqual(dash_after["liquidity_gap"], dash_before["liquidity_gap"], places=2)
            self.assertAlmostEqual(
                dash_after["active_stock_worth"], dash_before["active_stock_worth"] + 3500, places=2,
            )

    def test_partial_purchase_supplier_balance_equals_unpaid_payable(self):
        with db.db_session() as conn:
            uid = _fresh_user(conn, "partial_purch", cash=200_000, capital=200_000)
            supplier = db.create_account(conn, uid, {"name": "Partial Sup"})
            self.assertAlmostEqual(db.compute_dashboard(conn, uid)["liquidity_gap"], 0.0, places=2)
            db.create_phone(conn, uid, {
                "model": "PartialBuy", "type": "PTA", "purchase_price": 80000,
                "status": "Bought", "purchase_payment_method": "cash",
                "payable_amount": 30000, "supplier_account_id": supplier["id"],
            })
            bal = db.get_account(conn, uid, supplier["id"])["balance"]
            gap = db.compute_dashboard(conn, uid)["liquidity_gap"]
            self.assertAlmostEqual(bal, -30000, places=2)
            self.assertAlmostEqual(gap, 0.0, places=2)

    def test_partial_sale_buyer_balance_equals_receivable(self):
        with db.db_session() as conn:
            uid = _fresh_user(conn, "partial_sale", cash=200_000, capital=200_000)
            buyer = db.create_account(conn, uid, {"name": "Partial Buy"})
            phone = db.create_phone(conn, uid, {
                "model": "PartialSell", "type": "PTA", "purchase_price": 50000,
                "status": "Bought", "purchase_payment_method": "cash",
                "payable_amount": 0,
            })
            db.update_phone(conn, uid, phone["id"], {
                "status": "Sold", "sale_price": 100000, "receivable_amount": 40000,
                "buyer_account_id": buyer["id"], "sale_payment_method": "cash",
            })
            bal = db.get_account(conn, uid, buyer["id"])["balance"]
            self.assertAlmostEqual(bal, 40000, places=2)

    def test_full_cash_sale_with_buyer_account_settles_to_zero(self):
        with db.db_session() as conn:
            uid = _fresh_user(conn, "full_cash_buyer", cash=200_000, capital=200_000)
            buyer = db.create_account(conn, uid, {"name": "Cash Buy"})
            phone = db.create_phone(conn, uid, {
                "model": "CashSell", "type": "PTA", "purchase_price": 10000,
                "status": "Bought", "purchase_payment_method": "cash", "payable_amount": 0,
            })
            db.update_phone(conn, uid, phone["id"], {
                "status": "Sold", "sale_price": 15000, "receivable_amount": 0,
                "buyer_account_id": buyer["id"], "sale_payment_method": "cash",
            })
            bal = db.get_account(conn, uid, buyer["id"])["balance"]
            self.assertAlmostEqual(bal, 0.0, places=2)

    def test_supplier_unpaid_bill_allowed_without_payment(self):
        with db.db_session() as conn:
            uid = _fresh_user(conn, "supp_bill_ok")
            supplier = db.create_account(conn, uid, {"name": "Ali Supplier"})
            db.create_entry(conn, supplier["id"], {
                "entry_type": "credit", "amount": 25000, "note": "Unpaid bill",
            }, user_id=uid)
            self.assertAlmostEqual(db.get_account(conn, uid, supplier["id"])["balance"], -25000, places=2)

    def test_partner_settings_keys_no_longer_writable(self):
        with db.db_session() as conn:
            uid = _fresh_user(conn, "partner_dual")
            with self.assertRaises(ValueError):
                db.update_user_settings(conn, uid, {
                    "partner1_name": "Ghost", "partner1_capital": "999999",
                })
            dash = db.compute_dashboard(conn, uid)
            self.assertEqual(dash["partners"][0]["name"], "Owner")

    def test_modal_registry_includes_device_and_reset_not_jv(self):
        ui = (Path(crm_app.__file__).resolve().parent / "static" / "ui.js").read_text(encoding="utf-8")
        m = re.search(r"const MODAL_REGISTRY = \[(.*?)\];", ui, re.S)
        self.assertIsNotNone(m)
        registry = m.group(1)
        self.assertIn("device-overlay", registry)
        self.assertIn("reset-crm-overlay", registry)
        self.assertNotIn("jv-acct-overlay", registry)

    def test_invoice_routes_have_no_edit_or_delete(self):
        mutating = []
        for r in crm_app.app.url_map.iter_rules():
            methods = set(r.methods or ()) - {"HEAD", "OPTIONS"}
            if "invoice" in r.rule and methods & {"PUT", "PATCH", "DELETE"}:
                mutating.append((r.rule, sorted(methods)))
        self.assertEqual(mutating, [])


if __name__ == "__main__":
    unittest.main()
