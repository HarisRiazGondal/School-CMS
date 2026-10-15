# Project Memory

## Current checkpoint

School-CMS has a saved production release candidate on branch `codex/production-hardening-20261015`, draft PR1. Main remains the verified87.5% pilot; do not merge/release merely because hardening code exists. Production milestone8 is In progress.

**Local verification:183 tests run,175 passed,8 PostgreSQL-only concurrency tests skipped**, Python3.12 / Django5.2.18 / SQLite. Dependency audit has no known vulnerabilities after upgrading pypdf6.20.1; source scan has0 findings with narrow reviewed exceptions. Checks, drift, static manifest and fresh SQLite migrations pass. Default deploy check retains intentional W005/W021 until subdomain/preload acceptance.

The first draftPR GitHub CI run reported failure; connector job logs returned404/BlobNotFound and job steps were empty. Real PostgreSQL, restore and container evidence remain pending. The CI workflow has been consolidated into the existing `.github/workflows/tests.yml` and includes SQLite, PostgreSQL17/concurrency+restore, dependency/source and container-build jobs. Actual target-host SMTP/TLS/ClamAV/private-file recovery and human acceptance are still open. Score remains **7/8 =87.5%**, not production-ready.

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

Resume from draft PR1 and `09_NEXT_ACTIONS.md`; inspect actual CI results. Local uid namespace maps only root, with no Docker; a Playwright browser download failed, so no local PostgreSQL/container/browser runtime acceptance was claimed. Never bypass PostgreSQL's root protection. Keep all code and memory checkpoints on the release branch until release gates are evidenced.
