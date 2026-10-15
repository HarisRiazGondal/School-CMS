# Project Memory

## Current checkpoint

Release branch `codex/production-hardening-20261015`, draft PR #1. The next release validation increment implements authenticated database-plus-private-files bundles and guarded restore/rehearsal, a read-only runtime preflight, isolated five-role Playwright/axe acceptance, bounded authentication throttle retention (accounts0003), and nine explicit dashboard release gates. Independent Luna review found and corrected restore-attestation, bundle-limit, preflight DNS/TLS, PostgreSQL-test and CI context issues.

**Final local verification: 223 tests run, 214 passed, 9 PostgreSQL-only tests skipped, no failures.** Checks, migration drift, fresh SQLite migrations, dependency audit and application-directory Bandit scan pass. Operational scripts are reviewed/tested separately, outside the Bandit scan. Chromium download failed with a corrupt 0 MiB archive; no browser runtime pass is claimed.

The prior GitHub run #7 at `2fd821a715eb85e83e6834e62cad9cf7ebc776df` failed with zero jobs and unavailable logs. Invalid job-level runner context was corrected; hosted verification of the new exact commit remains required. Existing VPS selected but host/IP, SSH user, public domain and approved access remain unavailable. Main is unchanged, PR stays draft. Score remains **7/8 = 87.5%**; production milestone8 In progress. Evidence accounting validates records and totals, not authenticity or production approval.

## Architecture and invariants

Django 5.2 modular monolith, server-rendered same-origin portals and database sessions. Username login remains. Active school memberships plus teacher assignments/student ownership determine scope; cached Python activity flags never substitute for database checks. No blanket superuser access to private records.

Permanent Student UUID/STU code does not change across years. Enrollment stores year/section/roll and preserves completed outcomes. Pending intake creates no identity; admin approval registers atomically. The separate walk-in registration path remains. Admin-only batch confirmation revalidates under locks, commits all rows or none, and retains PromotionDecision snapshots, conditional reasons and batch attribution. Portal links use the controlled admin account-link service.

Attendance session context and records reject normal direct rewrites. Reasoned correction proposals preserve old/new values; school admins approve/reject, and stale proposals are system-closed. Students retain their historical attendance and current upcoming/overdue/completed/graded workload.

Assessment snapshots/answers/raw marks/finalized policy values remain distinct; only admins finalize/publish. Finance balances are exact Decimal ledger sums; original receipts/payments survive reasoned reversals. Historical transcripts and fee statements survive promotion.

The new oversight app owns validated/versioned school settings, notice revisions, conflict-checked timetable slots and role-bounded summaries. Settings apply school timezone and four effective policies (late submission, correction age, student result visibility, notice expiry). Teacher notices are limited to assigned sections. Terminology/branding render on oversight pages; global themes and branded export are not claimed. Normal model/queryset/service guards protect histories; privileged raw SQL remains outside those guards.

## Resume

Read this file, `09_NEXT_ACTIONS.md`, `project_state.json` and impacted design files; inspect actual code. The previous durable baseline was `fcb97554497e8196078ffe6f2f242415965679dd` (75%); the 2026-10-15 increment rebuilds and verifies oversight. Migrations include students 0002/0003, learning 0004/0005 and oversight 0001. No pending migration drift is intended.

Use `../TESTING_MVP.md` for five-role synthetic workflows and `../PROJECT_REVIEW.md` for resolved findings and limits. Update affected Markdown/JSON, regenerate HTML with `python scripts/render_status.py`, and commit checkpoints with code. Next work is production validation and the separately tracked broader backlog; do not count code presence as release evidence.

## Production hardening implementation

Shared DB throttles cover account+IP, account-global and source-IP buckets; TOTP secrets are Fernet-encrypted and one-use recovery uses keyed hashes. Required and opted-in accounts must complete MFA, with password-bound five-minute pending sessions and replay protection. Production settings fail closed without PostgreSQL, explicit hosts/HTTPS origins, distinct secret keys, persistent private storage/scanner and SMTP.

Private assignment/submission files use opaque keys, bounded content/PDF checks, quarantine, owner-only permissions and guarded historical downloads. Nonroot/read-only deployment, liveness/readiness/static assets, lock ordering fixes, safe encrypted database recovery scripts and accessibility semantics are implemented. New migrations: accounts0002 and privatefiles0001. Existing memory/design invariants remain in force.

Resume from draft PR #1 and `09_NEXT_ACTIONS.md`; inspect actual CI results. Local uid namespace maps only root, with no Docker; a Playwright browser download failed, so no local PostgreSQL/container/browser runtime acceptance was claimed. Never bypass PostgreSQL's root protection. Keep all code and memory checkpoints on the release branch until release gates are evidenced.

## Latest continuation details

Use `docs/RELEASE_REVIEW.md` and the recovery/preflight/browser/retention/evidence runbooks. Check Actions for the exact published commit before claiming any hosted runtime result. Run `python scripts/render_status.py` after every state change. The final local suite includes eight PostgreSQL concurrency skips plus one live-preflight skip; do not call these passes. Full target acceptance remains the only route to production closure.
