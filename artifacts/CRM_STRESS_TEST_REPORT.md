# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-22 06:41:51
**Database:** `/tmp/crm_stress_all_newbugs_final.db` (0.41 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **57** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 53 |
| Bulk Create 50 Phones Ms | 12.1 |
| Bulk Sold 25 Phones Ms | 5.1 |
| Cash Book Entries | 430 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 820000.0 |
| Dashboard Stock Worth | 12455800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.41 |
| Journal Vouchers | 20 |
| Ledger Links | 401 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 161 |
| Phones Sold | 52 |
| Phones Total | 215 |
| Return Logs | 4 |
| Stress Total Ms | 119.5 |
| Today Bought | 213 |
| Today Sold | 27 |
| Total In Bank | -2650155.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (4ms)
- [PASS] **Borrow phone ledger sync** - OK (4ms)
- [PASS] **Sale + receivable ledger sync** - OK (4ms)
- [PASS] **Phone expense -> cash book sync** - OK (3ms)
- [PASS] **Food expense -> cash out sync** - OK (3ms)
- [PASS] **Wasool debit -> cash in sync** - OK (4ms)
- [PASS] **Delete phone cascades ledger** - OK (6ms)
- [PASS] **Deleting a phone with invoices on record is blocked, not silently orphaning them** - OK (13ms)
- [PASS] **Bulk delete skips phones blocked by invoices instead of aborting the whole batch** - OK (6ms)
- [PASS] **Bank opening balance rejects negative values** - OK (4ms)
- [PASS] **Signup backup runs in the background and still actually completes** - OK (619ms)
- [PASS] **Expense Summary includes phone, fixed, AND account-based expenses** - OK (625ms)
- [PASS] **export_all_data() includes every user-owned table (invoices, JVs, side investments, returns, ledger links)** - OK (686ms)
- [PASS] **Expense category migration backfills existing Contact-trick accounts** - OK (605ms)
- [PASS] **Delete account entry cascades cash book** - OK (4ms)
- [PASS] **Journal voucher create/delete** - OK (4ms)
- [PASS] **Purchase return flow** - OK (4ms)
- [PASS] **Sale return flow** - OK (4ms)
- [PASS] **Purchase return refund is capped at what was actually paid** - OK (7ms)
- [PASS] **Sale return refund is capped at what the customer actually paid** - OK (9ms)
- [PASS] **Purchases/expenses just after local midnight land in today's reports, not UTC-yesterday's** - OK (579ms)
- [PASS] **customer_recovery_analysis() oldest_outstanding_date is local, not raw UTC** - OK (574ms)
- [PASS] **purchase_invoice_counter persists; unknown setting keys raise instead of vanishing** - OK (564ms)
- [PASS] **Today summary includes sold-as-bought** - OK (5ms)
- [PASS] **Update phone investments (bug fix)** - OK (4ms)
- [PASS] **Udhar dashboard no double-count** - OK (5ms)
- [PASS] **Duplicate IMEI rejected** - OK (4ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (5ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (4ms)
- [PASS] **Fixed expense posts to cash book** - OK (4ms)
- [PASS] **Zero cash balance + new account** - OK (6ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (687ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (884ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (473ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (466ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (18ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (12ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (9ms)
- [PASS] **Duplicate explicit invoice number is rejected, not silently duplicated** - OK (11ms)
- [PASS] **Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness** - OK (4ms)
- [PASS] **Negative cash guard blocks by default, allows through with force=True** - OK (559ms)
- [PASS] **Negative bank guard blocks a withdrawal by default, allows through with force=True** - OK (580ms)
- [PASS] **Negative cash guard also blocks a bank deposit that would overdraw the drawer** - OK (579ms)
- [PASS] **Reversing one side investment doesn't touch the partner's other top-ups** - OK (585ms)
- [PASS] **Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing** - OK (566ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (10ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (2331ms)
- [PASS] **OTP verification locks out after too many wrong attempts** - OK (584ms)
- [PASS] **OTP expires after 10 minutes** - OK (575ms)
- [PASS] **Restore only touches the requesting user's rows, others untouched** - OK (1199ms)
- [PASS] **Restore rejects path traversal and another user's backup file** - OK (15ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (626ms)
- [PASS] **Restore succeeds cleanly with a concurrent open connection (no corruption)** - OK (592ms)
- [PASS] **Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)** - OK (10ms)
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