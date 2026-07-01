# Mobile CRM — Logic Review & Stress Test Report

**Generated:** 2026-07-01 11:56:36
**Database:** `/tmp/crm_stress_test.db` (0.21 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **16** |
| Tests failed | **0** |
| Warnings | 4 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 157 |
| Bank Transactions | 51 |
| Bulk Create 50 Phones Ms | 2.8 |
| Bulk Sold 25 Phones Ms | 2.0 |
| Cash Book Entries | 408 |
| Cash In Hand | -7226425.0 |
| Dashboard Net Profit | 750000.0 |
| Dashboard Stock Worth | 12265800.0 |
| Dashboard Udhar | 1086125.0 |
| Db Size Mb | 0.21 |
| Journal Vouchers | 20 |
| Ledger Links | 381 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 156 |
| Phones Sold | 49 |
| Phones Total | 206 |
| Return Logs | 2 |
| Stress Total Ms | 33.8 |
| Today Bought | 205 |
| Today Sold | 24 |
| Total In Bank | -2667500.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** — OK (2ms)
- [PASS] **Borrow phone ledger sync** — OK (1ms)
- [PASS] **Sale + receivable ledger sync** — OK (2ms)
- [PASS] **Phone expense → cash book sync** — OK (2ms)
- [PASS] **Food expense → cash out sync** — OK (2ms)
- [PASS] **Wasool debit → cash in sync** — OK (2ms)
- [PASS] **Delete phone cascades ledger** — OK (1ms)
- [PASS] **Delete account entry cascades cash book** — OK (2ms)
- [PASS] **Journal voucher create/delete** — OK (2ms)
- [PASS] **Purchase return flow** — OK (2ms)
- [PASS] **Sale return flow** — OK (2ms)
- [PASS] **Today summary includes sold-as-bought** — OK (1ms)
- [PASS] **Update phone investments (bug fix)** — OK (2ms)
- [PASS] **No orphan cash ledger links** — 
- [PASS] **No orphan account ledger links** — 
- [PASS] **Bulk delete reduces ledger links** — links 381 -> 350, cb 408 -> 378

## Sync architecture verified

- Inventory purchase/sale/borrow → cash book + accounts via `ledger_links`
- Phone expenses → cash book out (+ optional account)
- Account Wasool (debit) → cash book in
- Expense category credit (Food) → cash book out
- Delete phone / account entry / cash book / journal → cascade reversal
- Returns post refunds without duplicate account rows

## Known limitations (not blocking)

- Dashboard udhar may double-count phone receivables already on buyer accounts (phone.receivable_amount + accounts receivable).
- update_phone does not re-sync ledgers when purchase/sale amounts change after posting.
- bulk_mark_sold fails if receivable_amount > 0 without buyer_account_id.
- Invoices and fixed expenses are not linked to cash book or inventory ledgers.

## Recommendations

- All automated sync tests passed under stress load — core ledger logic is consistent.
- Add automated pytest suite from `stress_test_crm.py` for CI.
- Fix dashboard udhar double-count when receivable is on both phone and account.
- Re-sync ledgers on phone price/payment edits, or block edits after posting.
- Pass `buyer_account_id` in bulk-sold when receivable is used.
- Filter Today cash in/out to cash-only (fixed in this run).