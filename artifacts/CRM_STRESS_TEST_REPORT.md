# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-25 04:41:00
**Database:** `/tmp/crm_stress_test.db` (0.45 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **82** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 119 |
| Bank Transactions | 53 |
| Bulk Create 50 Phones Ms | 5.1 |
| Bulk Sold 25 Phones Ms | 2.3 |
| Cash Book Entries | 436 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 843000.0 |
| Dashboard Stock Worth | 12460800.0 |
| Dashboard Udhar | 50000.0 |
| Db Size Mb | 0.45 |
| Ledger Links | 367 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 161 |
| Phones Sold | 55 |
| Phones Total | 218 |
| Return Logs | 4 |
| Stress Total Ms | 62.6 |
| Today Bought | 216 |
| Today Sold | 29 |
| Total In Bank | -2650155.0 |

## Test results

- [PASS] **Credit = shop received money, debit = shop gave money or billed new debt** - OK (203ms)
- [PASS] **Pre-fix account_entries rows are flipped exactly once by the migration** - OK (260ms)
- [PASS] **Purchase + udhar ledger sync** - OK (4ms)
- [PASS] **Borrow phone ledger sync** - OK (3ms)
- [PASS] **Sale + receivable ledger sync** - OK (4ms)
- [PASS] **Sell phone with no IMEI at all (direct + bulk)** - OK (3ms)
- [PASS] **Phone expense -> cash book sync** - OK (2ms)
- [PASS] **Food expense -> cash out sync** - OK (2ms)
- [PASS] **Wasool debit -> cash in sync** - OK (2ms)
- [PASS] **Delete phone cascades ledger** - OK (3ms)
- [PASS] **Deleting a phone with invoices on record is blocked, not silently orphaning them** - OK (9ms)
- [PASS] **Bulk delete skips phones blocked by invoices instead of aborting the whole batch** - OK (4ms)
- [PASS] **Bank opening balance rejects negative values** - OK (2ms)
- [PASS] **Signup backup runs in the background and still actually completes** - OK (211ms)
- [PASS] **Expense Summary includes phone, fixed, AND account-based expenses** - OK (205ms)
- [PASS] **export_all_data() includes every user-owned table (invoices, JVs, side investments, returns, ledger links)** - OK (212ms)
- [PASS] **Expense category migration backfills existing Contact-trick accounts** - OK (207ms)
- [PASS] **Delete account entry cascades cash book** - OK (3ms)
- [PASS] **Purchase return flow** - OK (2ms)
- [PASS] **Repair cycle (Bought -> In Repair -> Repaired -> Sold) keeps purchase ledger intact** - OK (4ms)
- [PASS] **Close the Month resets only the Overview tile, not Month Report/dashboard history** - OK (2413ms)
- [PASS] **Sale return flow** - OK (3ms)
- [PASS] **Purchase return refund is capped at what was actually paid** - OK (6ms)
- [PASS] **Sale return refund is capped at what the customer actually paid** - OK (6ms)
- [PASS] **Purchases/expenses just after local midnight land in today's reports, not UTC-yesterday's** - OK (206ms)
- [PASS] **customer_recovery_analysis() oldest_outstanding_date is local, not raw UTC** - OK (206ms)
- [PASS] **purchase_invoice_counter persists; unknown setting keys raise instead of vanishing** - OK (204ms)
- [PASS] **Today summary includes sold-as-bought** - OK (3ms)
- [PASS] **Update phone investments (bug fix)** - OK (4ms)
- [PASS] **Udhar dashboard no double-count** - OK (4ms)
- [PASS] **Duplicate IMEI rejected** - OK (3ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (4ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (3ms)
- [PASS] **Fixed expense posts to cash book** - OK (2ms)
- [PASS] **Zero cash balance + new account** - OK (3ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (261ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (838ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (437ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (437ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (11ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (8ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (6ms)
- [PASS] **Duplicate explicit invoice number is rejected, not silently duplicated** - OK (4ms)
- [PASS] **Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness** - OK (1ms)
- [PASS] **Negative cash guard blocks by default, allows through with force=True** - OK (208ms)
- [PASS] **Negative bank guard blocks a withdrawal by default, allows through with force=True** - OK (209ms)
- [PASS] **Negative cash guard also blocks a bank deposit that would overdraw the drawer** - OK (205ms)
- [PASS] **Side investment never touches Cash/Bank/partner capital; reversal is per-event** - OK (202ms)
- [PASS] **Device CRUD is isolated from Cash/Bank/Total Investment/Expected Liquid** - OK (205ms)
- [PASS] **Reversing a legacy (pre money-model) side investment cleans up its old cash/capital effect** - OK (203ms)
- [PASS] **Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing** - OK (205ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (2ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (825ms)
- [PASS] **OTP verification locks out after too many wrong attempts** - OK (203ms)
- [PASS] **Hardware-ID password reset: wrong code/username rejected, valid code changes password** - OK (987ms)
- [PASS] **Hardware-ID password reset locks out after too many wrong codes** - OK (203ms)
- [PASS] **OTP expires after 10 minutes** - OK (201ms)
- [PASS] **Restore only touches the requesting user's rows, others untouched** - OK (423ms)
- [PASS] **Restore rejects path traversal and another user's backup file** - OK (10ms)
- [PASS] **Reset CRM wipes only the requesting user's data, keeps login intact, other users untouched** - OK (409ms)
- [PASS] **Reset CRM succeeds (no FOREIGN KEY constraint failure) on a phone bought+sold through the bank** - OK (213ms)
- [PASS] **Undo/redo restores and reapplies a phone delete correctly** - OK (275ms)
- [PASS] **Undo/redo is per-user, and a new action after an undo discards the stale redo branch** - OK (445ms)
- [PASS] **Reset CRM clears the user's undo history so it can't resurrect wiped data** - OK (225ms)
- [PASS] **Concurrent backups (racing threads) never collide on the same destination filename** - OK (211ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (236ms)
- [PASS] **Restore succeeds cleanly with a concurrent open connection (no corruption)** - OK (226ms)
- [PASS] **Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)** - OK (4ms)
- [PASS] **Windows updater preserves the customer's Data folder across a self-update swap** - OK (1ms)
- [PASS] **Signup/auto backup does not deadlock the database (self-.backup() regression)** - OK (214ms)
- [PASS] **Opening-stock phones create ZERO cash/bank ledger rows** - OK (206ms)
- [PASS] **Completed wizard on a fresh user drives liquidity_gap to ~0** - OK (208ms)
- [PASS] **Fixed/overhead expenses never open a false Hisaab mein Farq gap** - OK (207ms)
- [PASS] **Pay-later purchase leaves cash/bank untouched until a payment is recorded** - OK (208ms)
- [PASS] **Selling an opening-stock phone posts the sale ledger only, profit computes normally** - OK (206ms)
- [PASS] **Reclassifying an opening-stock phone away from 'opening' on edit reproduces the reported 77k liquidity gap** - OK (207ms)
- [PASS] **Editing an opening-stock phone while keeping acquisition_type='opening' keeps liquidity_gap at 0** - OK (204ms)
- [PASS] **Existing users with no setup_completed row are grandfathered past the wizard** - OK (206ms)
- [PASS] **Month summary of a seeded test month matches hand-computed numbers** - OK (208ms)
- [PASS] **No orphan cash ledger links** - 
- [PASS] **No orphan account ledger links** - 
- [PASS] **Bulk delete reduces ledger links** - links 367 -> 336, cb 436 -> 406

## Sync architecture verified

- Inventory purchase/sale/borrow -> cash book + accounts via `ledger_links`
- Phone expenses -> cash book out (+ optional account)
- Account Wasool (credit) -> cash book in
- Expense category debit (Food) -> cash book out
- Delete phone / account entry / cash book -> cascade reversal
- Returns post refunds without duplicate account rows

## Known limitations (not blocking)


## Recommendations

- All automated sync tests passed under stress load - core ledger logic is consistent.
- Keep pytest CI green on every push to Version007.
- Invoices remain print-only records; sales post through inventory.