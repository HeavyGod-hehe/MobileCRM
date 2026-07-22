# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-22 05:29:06
**Database:** `/tmp/crm_stress_bug12b.db` (0.4 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **45** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 52 |
| Bulk Create 50 Phones Ms | 15.0 |
| Bulk Sold 25 Phones Ms | 7.0 |
| Cash Book Entries | 426 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 810000.0 |
| Dashboard Stock Worth | 12415800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.4 |
| Journal Vouchers | 20 |
| Ledger Links | 397 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 159 |
| Phones Sold | 51 |
| Phones Total | 212 |
| Return Logs | 4 |
| Stress Total Ms | 153.1 |
| Today Bought | 210 |
| Today Sold | 26 |
| Total In Bank | -2662500.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (6ms)
- [PASS] **Borrow phone ledger sync** - OK (5ms)
- [PASS] **Sale + receivable ledger sync** - OK (5ms)
- [PASS] **Phone expense -> cash book sync** - OK (5ms)
- [PASS] **Food expense -> cash out sync** - OK (5ms)
- [PASS] **Wasool debit -> cash in sync** - OK (4ms)
- [PASS] **Delete phone cascades ledger** - OK (6ms)
- [PASS] **Delete account entry cascades cash book** - OK (5ms)
- [PASS] **Journal voucher create/delete** - OK (5ms)
- [PASS] **Purchase return flow** - OK (5ms)
- [PASS] **Sale return flow** - OK (6ms)
- [PASS] **Purchase return refund is capped at what was actually paid** - OK (12ms)
- [PASS] **Sale return refund is capped at what the customer actually paid** - OK (11ms)
- [PASS] **Today summary includes sold-as-bought** - OK (6ms)
- [PASS] **Update phone investments (bug fix)** - OK (5ms)
- [PASS] **Udhar dashboard no double-count** - OK (8ms)
- [PASS] **Duplicate IMEI rejected** - OK (6ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (6ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (7ms)
- [PASS] **Fixed expense posts to cash book** - OK (5ms)
- [PASS] **Zero cash balance + new account** - OK (8ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (843ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (885ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (479ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (485ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (14ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (13ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (11ms)
- [PASS] **Duplicate explicit invoice number is rejected, not silently duplicated** - OK (13ms)
- [PASS] **Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness** - OK (4ms)
- [PASS] **Negative cash guard blocks by default, allows through with force=True** - OK (634ms)
- [PASS] **Negative bank guard blocks a withdrawal by default, allows through with force=True** - OK (684ms)
- [PASS] **Negative cash guard also blocks a bank deposit that would overdraw the drawer** - OK (707ms)
- [PASS] **Reversing one side investment doesn't touch the partner's other top-ups** - OK (690ms)
- [PASS] **Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing** - OK (677ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (11ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (2633ms)
- [PASS] **Restore only touches the requesting user's rows, others untouched** - OK (1386ms)
- [PASS] **Restore rejects path traversal and another user's backup file** - OK (20ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (767ms)
- [PASS] **Restore succeeds cleanly with a concurrent open connection (no corruption)** - OK (732ms)
- [PASS] **Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)** - OK (14ms)
- [PASS] **No orphan cash ledger links** - 
- [PASS] **No orphan account ledger links** - 
- [PASS] **Bulk delete reduces ledger links** - links 397 -> 364, cb 426 -> 394

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