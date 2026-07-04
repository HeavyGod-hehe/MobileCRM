# Mobile CRM - Logic Review & Stress Test Report

**Generated:** 2026-07-04 06:38:45
**Database:** `/tmp/crm_p3stress.db` (0.29 MB)

## Summary

| Metric | Value |
|--------|-------|
| Tests passed | **22** |
| Tests failed | **0** |
| Warnings | 0 |

## Stress load results

| Metric | Count / Value |
|--------|---------------|
| Account Entries | 159 |
| Bank Transactions | 52 |
| Bulk Create 50 Phones Ms | 13.3 |
| Bulk Sold 25 Phones Ms | 6.1 |
| Cash Book Entries | 421 |
| Cash In Hand | -7099925.0 |
| Dashboard Net Profit | 810000.0 |
| Dashboard Stock Worth | 12375800.0 |
| Dashboard Udhar | 1023500.0 |
| Db Size Mb | 0.29 |
| Journal Vouchers | 20 |
| Ledger Links | 392 |
| Orphan Ledger Account Links | 0 |
| Orphan Ledger Cash Links | 0 |
| Phones Bought | 158 |
| Phones Sold | 51 |
| Phones Total | 210 |
| Return Logs | 2 |
| Stress Total Ms | 137.3 |
| Today Bought | 209 |
| Today Sold | 26 |
| Total In Bank | -2662500.0 |

## Test results

- [PASS] **Purchase + udhar ledger sync** - OK (4ms)
- [PASS] **Borrow phone ledger sync** - OK (2ms)
- [PASS] **Sale + receivable ledger sync** - OK (3ms)
- [PASS] **Phone expense -> cash book sync** - OK (2ms)
- [PASS] **Food expense -> cash out sync** - OK (2ms)
- [PASS] **Wasool debit -> cash in sync** - OK (2ms)
- [PASS] **Delete phone cascades ledger** - OK (3ms)
- [PASS] **Delete account entry cascades cash book** - OK (4ms)
- [PASS] **Journal voucher create/delete** - OK (4ms)
- [PASS] **Purchase return flow** - OK (4ms)
- [PASS] **Sale return flow** - OK (4ms)
- [PASS] **Today summary includes sold-as-bought** - OK (3ms)
- [PASS] **Update phone investments (bug fix)** - OK (3ms)
- [PASS] **Udhar dashboard no double-count** - OK (4ms)
- [PASS] **Duplicate IMEI rejected** - OK (2ms)
- [PASS] **Sale price edit re-syncs cash book** - OK (4ms)
- [PASS] **Bulk sold udhar requires buyer account** - OK (3ms)
- [PASS] **Fixed expense posts to cash book** - OK (2ms)
- [PASS] **Zero cash balance + new account** - OK (4ms)
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