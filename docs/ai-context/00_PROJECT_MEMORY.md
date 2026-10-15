# Project Memory

## Current checkpoint

User reprioritized to local testing and review; CI/VPS/hosted work is deferred. Continue on `codex/production-hardening-20261015`, draft PR #1. Main remains unchanged. Local pilot testing can proceed without resolving the hosting prerequisites.

**Latest verification: 224 tests run, 215 passed, 9 PostgreSQL-only skips, no failures** (Python3.12.14 / Django5.2.18 / SQLite). Fresh migrations/seed, five-role CSRF HTTP journeys, 73 role-scoped linked GETs, 16 malformed form submissions, system/drift checks, dependency compatibility/audit and application-directory Bandit all pass. Chromium is absent; HTTP-client checks are not browser/axe execution.

Two new defects were reproduced and fixed: financial Decimal quantization overflow now becomes ValidationError with no writes; teacher oversight navigation no longer offers the admin-only correction queue or duplicate review metric. The teacher route stays403; admin review stays200. See `docs/LOCAL_TEST_REPORT.md` for latest evidence and report inventory, and `docs/TESTING_MVP.md` for local role checklists/Windows setup. A PostgreSQL enrollment/assessment-start race is an unverified review candidate, not a reproduced local bug.

Production milestone remains In progress, score7/8=87.5%; this is separate from the current local-testing goal. Existing CI billing and target-host facts are retained as deferred history below. No request for server/billing details is needed during local acceptance.

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

## Hosted CI blocker confirmed after publication

Runs #8/#9 at 6e3b0a6558267ca3cbed8a3696811e4f5cea73eb each created five jobs but no runners or steps. The public job annotation confirms: "The job was not started because your account is locked due to a billing issue." The account owner must resolve this outside the repository before rerunning CI. No PostgreSQL, recovery, container or browser CI pass occurred.

Verified annotation: https://github.com/HarisRiazGondal/School-CMS/actions/runs/38771801513/job/116549229916

Follow-up CI configuration sets `DJANGO_SETTINGS_MODULE=schoolcms.settings` for standalone production-check Python and pins Ubuntu24.04 before the announced ubuntu-latest migration. Operations regressions pass7/7; no hosted execution is claimed. Keep milestone8 In progress and the score87.5%.
