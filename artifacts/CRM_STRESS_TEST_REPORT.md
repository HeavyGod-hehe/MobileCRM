# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-24 21:40:13
**Database:** `C:\Users\Talha yasin\.claude\jobs\89b65745/tmp/stress_absolute_final.db` (0.45 MB)

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
| Bulk Create 50 Phones Ms | 15.6 |
| Bulk Sold 25 Phones Ms | 6.7 |
| Cash Book Entries | 436 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 843000.0 |
| Dashboard Stock Worth | 12460800.0 |
| Dashboard Udhar | 1062500.0 |
| Db Size Mb | 0.45 |
| Ledger Links | 367 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 161 |
| Phones Sold | 55 |
| Phones Total | 218 |
| Return Logs | 4 |
| Stress Total Ms | 199.0 |
| Today Bought | 216 |
| Today Sold | 29 |
| Total In Bank | -2650155.0 |

## Test results

- [PASS] **Credit = shop received money, debit = shop gave money or billed new debt** - OK (1294ms)
- [PASS] **Pre-fix account_entries rows are flipped exactly once by the migration** - OK (3129ms)
- [PASS] **Purchase + udhar ledger sync** - OK (28ms)
- [PASS] **Borrow phone ledger sync** - OK (28ms)
- [PASS] **Sale + receivable ledger sync** - OK (32ms)
- [PASS] **Sell phone with no IMEI at all (direct + bulk)** - OK (29ms)
- [PASS] **Phone expense -> cash book sync** - OK (27ms)
- [PASS] **Food expense -> cash out sync** - OK (26ms)
- [PASS] **Wasool debit -> cash in sync** - OK (27ms)
- [PASS] **Delete phone cascades ledger** - OK (29ms)
- [PASS] **Deleting a phone with invoices on record is blocked, not silently orphaning them** - OK (84ms)
- [PASS] **Bulk delete skips phones blocked by invoices instead of aborting the whole batch** - OK (31ms)
- [PASS] **Bank opening balance rejects negative values** - OK (26ms)
- [PASS] **Signup backup runs in the background and still actually completes** - OK (1346ms)
- [PASS] **Expense Summary includes phone, fixed, AND account-based expenses** - OK (1275ms)
- [PASS] **export_all_data() includes every user-owned table (invoices, JVs, side investments, returns, ledger links)** - OK (1283ms)
- [PASS] **Expense category migration backfills existing Contact-trick accounts** - OK (1316ms)
- [PASS] **Delete account entry cascades cash book** - OK (27ms)
- [PASS] **Purchase return flow** - OK (27ms)
- [PASS] **Repair cycle (Bought -> In Repair -> Repaired -> Sold) keeps purchase ledger intact** - OK (27ms)
- [PASS] **Close the Month resets only the Overview tile, not Month Report/dashboard history** - OK (3539ms)
- [PASS] **Sale return flow** - OK (31ms)
- [PASS] **Purchase return refund is capped at what was actually paid** - OK (54ms)
- [PASS] **Sale return refund is capped at what the customer actually paid** - OK (54ms)
- [PASS] **Purchases/expenses just after local midnight land in today's reports, not UTC-yesterday's** - OK (0ms)
- [PASS] **customer_recovery_analysis() oldest_outstanding_date is local, not raw UTC** - OK (0ms)
- [PASS] **purchase_invoice_counter persists; unknown setting keys raise instead of vanishing** - OK (1327ms)
- [PASS] **Today summary includes sold-as-bought** - OK (27ms)
- [PASS] **Update phone investments (bug fix)** - OK (24ms)
- [PASS] **Udhar dashboard no double-count** - OK (29ms)
- [PASS] **Duplicate IMEI rejected** - OK (28ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (29ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (28ms)
- [PASS] **Fixed expense posts to cash book** - OK (32ms)
- [PASS] **Zero cash balance + new account** - OK (35ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (1475ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (902ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (506ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (506ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (87ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (70ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (63ms)
- [PASS] **Duplicate explicit invoice number is rejected, not silently duplicated** - OK (67ms)
- [PASS] **Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness** - OK (30ms)
- [PASS] **Negative cash guard blocks by default, allows through with force=True** - OK (1293ms)
- [PASS] **Negative bank guard blocks a withdrawal by default, allows through with force=True** - OK (1415ms)
- [PASS] **Negative cash guard also blocks a bank deposit that would overdraw the drawer** - OK (1307ms)
- [PASS] **Side investment never touches Cash/Bank/partner capital; reversal is per-event** - OK (1277ms)
- [PASS] **Device CRUD is isolated from Cash/Bank/Total Investment/Expected Liquid** - OK (1272ms)
- [PASS] **Reversing a legacy (pre money-model) side investment cleans up its old cash/capital effect** - OK (1309ms)
- [PASS] **Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing** - OK (1270ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (14ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (5226ms)
- [PASS] **OTP verification locks out after too many wrong attempts** - OK (1307ms)
- [PASS] **Hardware-ID password reset: wrong code/username rejected, valid code changes password** - OK (6418ms)
- [PASS] **Hardware-ID password reset locks out after too many wrong codes** - OK (1305ms)
- [PASS] **OTP expires after 10 minutes** - OK (1268ms)
- [PASS] **Restore only touches the requesting user's rows, others untouched** - OK (2788ms)
- [PASS] **Restore rejects path traversal and another user's backup file** - OK (105ms)
- [PASS] **Reset CRM wipes only the requesting user's data, keeps login intact, other users untouched** - OK (2764ms)
- [PASS] **Reset CRM succeeds (no FOREIGN KEY constraint failure) on a phone bought+sold through the bank** - OK (1352ms)
- [PASS] **Undo/redo restores and reapplies a phone delete correctly** - OK (1938ms)
- [PASS] **Undo/redo is per-user, and a new action after an undo discards the stale redo branch** - OK (3036ms)
- [PASS] **Reset CRM clears the user's undo history so it can't resurrect wiped data** - OK (1492ms)
- [PASS] **Concurrent backups (racing threads) never collide on the same destination filename** - OK (1372ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (1539ms)
- [PASS] **Restore succeeds cleanly with a concurrent open connection (no corruption)** - OK (1467ms)
- [PASS] **Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)** - OK (29ms)
- [PASS] **Windows updater preserves the customer's Data folder across a self-update swap** - OK (27ms)
- [PASS] **Signup/auto backup does not deadlock the database (self-.backup() regression)** - OK (1516ms)
- [PASS] **Opening-stock phones create ZERO cash/bank ledger rows** - OK (1294ms)
- [PASS] **Completed wizard on a fresh user drives liquidity_gap to ~0** - OK (1278ms)
- [PASS] **Fixed/overhead expenses never open a false Hisaab mein Farq gap** - OK (1257ms)
- [PASS] **Pay-later purchase leaves cash/bank untouched until a payment is recorded** - OK (1335ms)
- [PASS] **Selling an opening-stock phone posts the sale ledger only, profit computes normally** - OK (1243ms)
- [PASS] **Reclassifying an opening-stock phone away from 'opening' on edit reproduces the reported 77k liquidity gap** - OK (1263ms)
- [PASS] **Editing an opening-stock phone while keeping acquisition_type='opening' keeps liquidity_gap at 0** - OK (1282ms)
- [PASS] **Existing users with no setup_completed row are grandfathered past the wizard** - OK (1323ms)
- [PASS] **Month summary of a seeded test month matches hand-computed numbers** - OK (1274ms)
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