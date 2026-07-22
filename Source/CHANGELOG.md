# Changelog

## 2.4.12 — 2026-07-22

Bug-fix pass covering 24 issues from the confirmed backlog (`Changes To
Be Done.txt`) and a follow-up audit (`artifacts/CRM_AUDIT_REPORT.md`).
Incremental fixes on the existing architecture — no rewrites, no new
features beyond what each fix required, `ledger_links`/
`_create_cash_book_synced` untouched in design. Full verification:
stress suite 55/55, fresh-DB smoke test, and existing-DB migration test
(applies cleanly and idempotently against a pre-2.4.12 database, all
existing data displays correctly) all passed — see the bugfix-pass
summary report for details on each item.

### Critical
- Restore is now a per-user logical operation instead of a full-file
  copy — restoring one user's backup no longer destroys every other
  account's data, and is sandboxed to that user's own backup folder.
- Restore no longer risks a locked/torn database file: WAL checkpoint,
  backup-API snapshot instead of a raw file copy, and a post-restore
  integrity check with automatic rollback on failure.
- Fixed the Windows in-app updater resolving the install path one
  directory too deep, which silently broke auto-update on Windows.

### High
- Password-reset OTP emails no longer send through another user's Gmail
  credentials.
- Removed the hardcoded Flask `secret_key` shared by every customer
  build; each installation now generates and persists its own.
- CI now actually bakes `CRM_LICENSE_SECRET` into release builds (a
  build-time env var alone had no effect on the shipped app).
- Invoice numbers are now enforced unique per user (existing duplicates
  are repaired automatically on upgrade).
- Side-investment top-ups get their own identity, so reversing one can
  no longer cascade into reversing every top-up a partner ever made.
- Added a Cash in Hand (Opening) field to Settings.
- Release manifests are now validated in CI before publishing, and the
  in-app updater degrades gracefully instead of crashing on a malformed
  manifest.

### Medium
- Cash and bank balances now have a soft negative-balance guard
  (confirmable with `force`, never a hard block).
- Returns can no longer refund more than was actually paid/received.
- Fixed a UTC-vs-local-time mismatch that could misclassify entries
  recorded near midnight into the wrong day's reports.
- `purchase_invoice_counter` was silently dropped by a stale settings
  allow-list; unknown setting keys now raise instead of vanishing.
- `CRM_HOST` now actually changes the bind address (with a non-loopback
  security warning).
- OTP verification is now rate-limited (5 attempts / 15 min lockout) and
  expires after 10 minutes instead of 15.
- Removed the dead "Google Drive sync" placeholder setting.
- Deleting a phone with invoices on record is now blocked instead of
  silently orphaning them.
- Bank opening balance can no longer be negative.
- Signup's backup now runs in the background instead of blocking (and
  possibly failing) the signup response.

### Low
- Removed the leftover `DEFAULT_USER` (shahir/test123) dev constant.
- Documented the CSRF gap explicitly (accepted while localhost-only).
- Expense Summary now includes the third expense path (credit entries on
  accounts marked as an expense category), which previously vanished
  from this one report even though the money was correctly tracked
  everywhere else. Expense-category accounts get a real checkbox instead
  of a hidden Contact-field trick.
- XSS audit: confirmed every user-text render path escapes correctly;
  no exploitable finding, no code change needed.
