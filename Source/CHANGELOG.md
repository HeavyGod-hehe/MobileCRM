# Changelog

## 2.4.13 — 2026-07-23

UI/UX bug-hunt pass (picked up Part 3 of `Changes To Be Done.txt`, previously
started and stopped early). Verified with a fresh browser-less audit of every
template/JS file plus live functional tests against a running instance
(signup, login, add/delete a cash book entry through the newly-guarded write
path). Backend suite (`test_crm.py`, `test_license_guard.py`) still 4/4 after
every change.

- Bug #25: 8 modals (Payment Method picker, inline New Account popups on
  Inventory/Journal, Bulk Sold, Reinvest Profit, Add Side Investment, and the
  two IMEI camera-scanner modals on Billing/Purchase Invoice) were missing
  from `MODAL_REGISTRY` in `ui.js`, so the Escape key silently did nothing on
  them — only the backdrop click or explicit Close button worked.
- The two IMEI camera-scanner modals (Billing, Purchase Invoice) never
  actually became visible/interactive: they were toggled with a raw `hidden`
  class, but app.css's unconditional `.modal-wrap { display: flex }` rule
  (loaded after `tailwind.min.css`) silently overrides Tailwind's
  `.hidden{display:none}` for any element carrying both classes — combined
  with `.open` never being added, the modal stayed at `opacity:0` /
  `pointer-events:none` even after "opening" it. Tapping "Scan IMEI" started
  the camera with nothing visible on screen. Switched both to the same
  `openModal()`/`closeModal()` helper every other modal in the app already
  uses correctly.
- Fixed 3 modals (Bulk Sold, Active Stock, Partner Customization) that
  nested a second independently-scrolling container inside the modal panel
  — on shorter screens this produced two stacked scrollbars and made content
  below the fold hard to reach. Switched them to the single-outer-scroll
  pattern (`modal-wrap-scroll`) already used correctly by the main
  Add/Edit Device modal.
- The mobile sidebar drawer had no backdrop and no outside-tap/Escape
  dismiss — the hamburger button was the only way to close it. Added a
  backdrop with click-to-close, wired into the same Escape handler as
  modals.
- 9 write actions (delete cash book entry, add cash book entry, delete
  journal voucher, add journal voucher, delete bank transaction, add/edit
  phone expense, update partner capital inline, add/edit partner, rename
  partner) called the API with no error handling at all. When the request
  failed for any reason (validation error, the negative-balance guard,
  "database busy"), the button did nothing visible — no toast, no feedback,
  indistinguishable from a dead button. All 9 now show the error via
  `toast(err.message, 'error')`, matching the pattern already used correctly
  elsewhere (e.g. Accounts' delete-entry flow).

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
