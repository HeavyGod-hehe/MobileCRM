# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-01 12:29:25
**Database:** `\tmp\crm_stress_test.db` (0.21 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **21** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 51 |
| Bulk Create 50 Phones Ms | 15.9 |
| Bulk Sold 25 Phones Ms | 8.3 |
| Cash Book Entries | 415 |
| Cash In Hand | -7331425.0 |
| Dashboard Net Profit | 810000.0 |
| Dashboard Stock Worth | 12375800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.21 |
| Journal Vouchers | 20 |
| Ledger Links | 389 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 158 |
| Phones Sold | 51 |
| Phones Total | 210 |
| Return Logs | 2 |
| Stress Total Ms | 287.2 |
| Today Bought | 209 |
| Today Sold | 26 |
| Total In Bank | -2667500.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (31ms)
- [PASS] **Borrow phone ledger sync** - OK (30ms)
- [PASS] **Sale + receivable ledger sync** - OK (28ms)
- [PASS] **Phone expense -> cash book sync** - OK (22ms)
- [PASS] **Food expense -> cash out sync** - OK (17ms)
- [PASS] **Wasool debit -> cash in sync** - OK (17ms)
- [PASS] **Delete phone cascades ledger** - OK (21ms)
- [PASS] **Delete account entry cascades cash book** - OK (26ms)
- [PASS] **Journal voucher create/delete** - OK (23ms)
- [PASS] **Purchase return flow** - OK (23ms)
- [PASS] **Sale return flow** - OK (21ms)
- [PASS] **Today summary includes sold-as-bought** - OK (20ms)
- [PASS] **Update phone investments (bug fix)** - OK (20ms)
- [PASS] **Udhar dashboard no double-count** - OK (28ms)
- [PASS] **Duplicate IMEI rejected** - OK (20ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (20ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (25ms)
- [PASS] **Fixed expense posts to cash book** - OK (20ms)
- [PASS] **No orphan cash ledger links** - 
- [PASS] **No orphan account ledger links** - 
- [PASS] **Bulk delete reduces ledger links** - links 389 -> 358, cb 415 -> 385

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