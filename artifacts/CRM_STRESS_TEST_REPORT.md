# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-20 19:11:52
**Database:** `C:\Users\Raza Printer\Downloads\REHMAN CRM Work\stress_test.db` (0.39 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **32** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 52 |
| Bulk Create 50 Phones Ms | 25.1 |
| Bulk Sold 25 Phones Ms | 5.5 |
| Cash Book Entries | 421 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 810000.0 |
| Dashboard Stock Worth | 12375800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.39 |
| Journal Vouchers | 20 |
| Ledger Links | 392 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 158 |
| Phones Sold | 51 |
| Phones Total | 210 |
| Return Logs | 2 |
| Stress Total Ms | 180.9 |
| Today Bought | 209 |
| Today Sold | 26 |
| Total In Bank | -2662500.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (27ms)
- [PASS] **Borrow phone ledger sync** - OK (25ms)
- [PASS] **Sale + receivable ledger sync** - OK (28ms)
- [PASS] **Phone expense -> cash book sync** - OK (25ms)
- [PASS] **Food expense -> cash out sync** - OK (24ms)
- [PASS] **Wasool debit -> cash in sync** - OK (20ms)
- [PASS] **Delete phone cascades ledger** - OK (22ms)
- [PASS] **Delete account entry cascades cash book** - OK (23ms)
- [PASS] **Journal voucher create/delete** - OK (24ms)
- [PASS] **Purchase return flow** - OK (21ms)
- [PASS] **Sale return flow** - OK (24ms)
- [PASS] **Today summary includes sold-as-bought** - OK (30ms)
- [PASS] **Update phone investments (bug fix)** - OK (30ms)
- [PASS] **Udhar dashboard no double-count** - OK (34ms)
- [PASS] **Duplicate IMEI rejected** - OK (30ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (35ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (29ms)
- [PASS] **Fixed expense posts to cash book** - OK (28ms)
- [PASS] **Zero cash balance + new account** - OK (33ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (1087ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (910ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (487ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (499ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (110ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (61ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (82ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (40ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (3962ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (199ms)
- [PASS] **No orphan cash ledger links** - 
- [PASS] **No orphan account ledger links** - 
- [PASS] **Bulk delete reduces ledger links** - links 392 -> 360, cb 421 -> 390

## Sync architecture verified

- Inventory purchase/sale/borrow -> cash book + accounts via `ledger_links`
- Phone expenses -> cash book out (+ optional account)
- Account Wasool (debit) -> cash book in
- Expense category credit (Food) -> cash book out
- Delete phone / account entry / cash book / journal -> cascade reversal
- Returns post refunds without duplicate account rows

## Known limitations (not blocking)


## Recommendations

- All automated sync tests passed under stress load - core ledger logic is consistent.
- Keep pytest CI green on every push to Version007.
- Invoices remain print-only records; sales post through inventory.