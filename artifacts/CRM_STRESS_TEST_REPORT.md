# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-22 05:55:44
**Database:** `/tmp/crm_stress_phase3_final.db` (0.4 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **53** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 53 |
| Bulk Create 50 Phones Ms | 11.4 |
| Bulk Sold 25 Phones Ms | 5.4 |
| Cash Book Entries | 430 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 820000.0 |
| Dashboard Stock Worth | 12455800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.4 |
| Journal Vouchers | 20 |
| Ledger Links | 401 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 161 |
| Phones Sold | 52 |
| Phones Total | 215 |
| Return Logs | 4 |
| Stress Total Ms | 124.4 |
| Today Bought | 213 |
| Today Sold | 27 |
| Total In Bank | -2650155.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (5ms)
- [PASS] **Borrow phone ledger sync** - OK (4ms)
- [PASS] **Sale + receivable ledger sync** - OK (10ms)
- [PASS] **Phone expense -> cash book sync** - OK (9ms)
- [PASS] **Food expense -> cash out sync** - OK (9ms)
- [PASS] **Wasool debit -> cash in sync** - OK (4ms)
- [PASS] **Delete phone cascades ledger** - OK (6ms)
- [PASS] **Deleting a phone with invoices on record is blocked, not silently orphaning them** - OK (19ms)
- [PASS] **Bulk delete skips phones blocked by invoices instead of aborting the whole batch** - OK (9ms)
- [PASS] **Bank opening balance rejects negative values** - OK (3ms)
- [PASS] **Signup backup runs in the background and still actually completes** - OK (673ms)
- [PASS] **Delete account entry cascades cash book** - OK (5ms)
- [PASS] **Journal voucher create/delete** - OK (5ms)
- [PASS] **Purchase return flow** - OK (5ms)
- [PASS] **Sale return flow** - OK (6ms)
- [PASS] **Purchase return refund is capped at what was actually paid** - OK (9ms)
- [PASS] **Sale return refund is capped at what the customer actually paid** - OK (9ms)
- [PASS] **Purchases/expenses just after local midnight land in today's reports, not UTC-yesterday's** - OK (638ms)
- [PASS] **purchase_invoice_counter persists; unknown setting keys raise instead of vanishing** - OK (693ms)
- [PASS] **Today summary includes sold-as-bought** - OK (5ms)
- [PASS] **Update phone investments (bug fix)** - OK (5ms)
- [PASS] **Udhar dashboard no double-count** - OK (6ms)
- [PASS] **Duplicate IMEI rejected** - OK (5ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (6ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (5ms)
- [PASS] **Fixed expense posts to cash book** - OK (4ms)
- [PASS] **Zero cash balance + new account** - OK (7ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (878ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (875ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (477ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (471ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (15ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (12ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (11ms)
- [PASS] **Duplicate explicit invoice number is rejected, not silently duplicated** - OK (12ms)
- [PASS] **Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness** - OK (4ms)
- [PASS] **Negative cash guard blocks by default, allows through with force=True** - OK (680ms)
- [PASS] **Negative bank guard blocks a withdrawal by default, allows through with force=True** - OK (656ms)
- [PASS] **Negative cash guard also blocks a bank deposit that would overdraw the drawer** - OK (658ms)
- [PASS] **Reversing one side investment doesn't touch the partner's other top-ups** - OK (698ms)
- [PASS] **Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing** - OK (655ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (8ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (2732ms)
- [PASS] **OTP verification locks out after too many wrong attempts** - OK (622ms)
- [PASS] **OTP expires after 10 minutes** - OK (610ms)
- [PASS] **Restore only touches the requesting user's rows, others untouched** - OK (1392ms)
- [PASS] **Restore rejects path traversal and another user's backup file** - OK (18ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (664ms)
- [PASS] **Restore succeeds cleanly with a concurrent open connection (no corruption)** - OK (688ms)
- [PASS] **Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)** - OK (11ms)
- [PASS] **No orphan cash ledger links** - 
- [PASS] **No orphan account ledger links** - 
- [PASS] **Bulk delete reduces ledger links** - links 401 -> 370, cb 430 -> 400

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