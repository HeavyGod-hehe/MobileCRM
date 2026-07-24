# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-24 02:57:37
**Database:** `C:/Users/Talha yasin/MobileCRM-src/MobileCRM-Themed-CRM/MobileCRM-repo/Source/../../scratch_stress_final.db` (0.45 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **75** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 53 |
| Bulk Create 50 Phones Ms | 16.3 |
| Bulk Sold 25 Phones Ms | 7.0 |
| Cash Book Entries | 430 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 820000.0 |
| Dashboard Stock Worth | 12455800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.45 |
| Journal Vouchers | 20 |
| Ledger Links | 401 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 161 |
| Phones Sold | 52 |
| Phones Total | 215 |
| Return Logs | 4 |
| Stress Total Ms | 208.2 |
| Today Bought | 213 |
| Today Sold | 27 |
| Total In Bank | -2650155.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (29ms)
- [PASS] **Borrow phone ledger sync** - OK (38ms)
- [PASS] **Sale + receivable ledger sync** - OK (41ms)
- [PASS] **Phone expense -> cash book sync** - OK (37ms)
- [PASS] **Food expense -> cash out sync** - OK (37ms)
- [PASS] **Wasool debit -> cash in sync** - OK (38ms)
- [PASS] **Delete phone cascades ledger** - OK (44ms)
- [PASS] **Deleting a phone with invoices on record is blocked, not silently orphaning them** - OK (139ms)
- [PASS] **Bulk delete skips phones blocked by invoices instead of aborting the whole batch** - OK (53ms)
- [PASS] **Bank opening balance rejects negative values** - OK (37ms)
- [PASS] **Signup backup runs in the background and still actually completes** - OK (1304ms)
- [PASS] **Expense Summary includes phone, fixed, AND account-based expenses** - OK (1300ms)
- [PASS] **export_all_data() includes every user-owned table (invoices, JVs, side investments, returns, ledger links)** - OK (1256ms)
- [PASS] **Expense category migration backfills existing Contact-trick accounts** - OK (1199ms)
- [PASS] **Delete account entry cascades cash book** - OK (37ms)
- [PASS] **Journal voucher create/delete** - OK (37ms)
- [PASS] **Purchase return flow** - OK (37ms)
- [PASS] **Sale return flow** - OK (37ms)
- [PASS] **Purchase return refund is capped at what was actually paid** - OK (56ms)
- [PASS] **Sale return refund is capped at what the customer actually paid** - OK (56ms)
- [PASS] **Purchases/expenses just after local midnight land in today's reports, not UTC-yesterday's** - OK (0ms)
- [PASS] **customer_recovery_analysis() oldest_outstanding_date is local, not raw UTC** - OK (0ms)
- [PASS] **purchase_invoice_counter persists; unknown setting keys raise instead of vanishing** - OK (1243ms)
- [PASS] **Today summary includes sold-as-bought** - OK (40ms)
- [PASS] **Update phone investments (bug fix)** - OK (38ms)
- [PASS] **Udhar dashboard no double-count** - OK (42ms)
- [PASS] **Duplicate IMEI rejected** - OK (37ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (43ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (36ms)
- [PASS] **Fixed expense posts to cash book** - OK (37ms)
- [PASS] **Zero cash balance + new account** - OK (50ms)
- [PASS] **Mixed-activity ledger reconciliation (220 randomized transactions)** - OK (1503ms)
- [PASS] **Concurrent double-sell on the same phone is rejected, not double-posted** - OK (910ms)
- [PASS] **Concurrent double-return on the same sale is rejected, not double-refunded** - OK (517ms)
- [PASS] **Concurrent double-return on the same purchase is rejected, not double-refunded** - OK (512ms)
- [PASS] **Concurrent double-edit of the same phone expense stays consistent (last-write-wins, no duplicates)** - OK (121ms)
- [PASS] **Concurrent double-delete of the same phone is idempotent (no crash, no double-reversal)** - OK (95ms)
- [PASS] **Concurrent invoice creation gets distinct numbers (confirms existing lock holds)** - OK (75ms)
- [PASS] **Duplicate explicit invoice number is rejected, not silently duplicated** - OK (113ms)
- [PASS] **Invoice dedupe migration repairs pre-existing duplicates and restores uniqueness** - OK (52ms)
- [PASS] **Negative cash guard blocks by default, allows through with force=True** - OK (1424ms)
- [PASS] **Negative bank guard blocks a withdrawal by default, allows through with force=True** - OK (1349ms)
- [PASS] **Negative cash guard also blocks a bank deposit that would overdraw the drawer** - OK (1302ms)
- [PASS] **Reversing one side investment doesn't touch the partner's other top-ups** - OK (1210ms)
- [PASS] **Side investment reversal refuses ambiguous pre-fix legacy data instead of guessing** - OK (1241ms)
- [PASS] **License activation is hardware-bound; reuse on another machine fails** - OK (25ms)
- [PASS] **Forgot-password OTP flow end to end (SMTP transport mocked, real app logic)** - OK (5132ms)
- [PASS] **OTP verification locks out after too many wrong attempts** - OK (1300ms)
- [PASS] **Hardware-ID password reset: wrong code/username rejected, valid code changes password** - OK (6584ms)
- [PASS] **Hardware-ID password reset locks out after too many wrong codes** - OK (1317ms)
- [PASS] **OTP expires after 10 minutes** - OK (1190ms)
- [PASS] **Restore only touches the requesting user's rows, others untouched** - OK (2612ms)
- [PASS] **Restore rejects path traversal and another user's backup file** - OK (107ms)
- [PASS] **Reset CRM wipes only the requesting user's data, keeps login intact, other users untouched** - OK (2565ms)
- [PASS] **Reset CRM succeeds (no FOREIGN KEY constraint failure) on a phone bought+sold through the bank** - OK (1311ms)
- [PASS] **Undo/redo restores and reapplies a phone delete correctly** - OK (1931ms)
- [PASS] **Undo/redo is per-user, and a new action after an undo discards the stale redo branch** - OK (3106ms)
- [PASS] **Reset CRM clears the user's undo history so it can't resurrect wiped data** - OK (1508ms)
- [PASS] **Concurrent backups (racing threads) never collide on the same destination filename** - OK (1372ms)
- [PASS] **Backup taken pre-migration restores and cleanly re-migrates after a schema bump** - OK (1668ms)
- [PASS] **Restore succeeds cleanly with a concurrent open connection (no corruption)** - OK (1444ms)
- [PASS] **Updater resolves real Windows and Mac install paths (no phantom one-level-too-deep path)** - OK (56ms)
- [PASS] **Windows updater preserves the customer's Data folder across a self-update swap** - OK (31ms)
- [PASS] **Signup/auto backup does not deadlock the database (self-.backup() regression)** - OK (1380ms)
- [PASS] **Opening-stock phones create ZERO cash/bank ledger rows** - OK (1216ms)
- [PASS] **Completed wizard on a fresh user drives liquidity_gap to ~0** - OK (1173ms)
- [PASS] **Pay-later purchase leaves cash/bank untouched until a payment is recorded** - OK (1185ms)
- [PASS] **Selling an opening-stock phone posts the sale ledger only, profit computes normally** - OK (1266ms)
- [PASS] **Reclassifying an opening-stock phone away from 'opening' on edit reproduces the reported 77k liquidity gap** - OK (1287ms)
- [PASS] **Editing an opening-stock phone while keeping acquisition_type='opening' keeps liquidity_gap at 0** - OK (1314ms)
- [PASS] **Existing users with no setup_completed row are grandfathered past the wizard** - OK (1198ms)
- [PASS] **Month summary of a seeded test month matches hand-computed numbers** - OK (1277ms)
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