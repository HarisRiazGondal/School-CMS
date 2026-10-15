# Project Memory

## Current checkpoint

School-CMS is a Django school pilot with session authentication, scoped portals, permanent student identities, admission decisions, individual/batch yearly progression, guarded attendance/corrections, classwork, assessments/transcripts, fees/receipts/reversals and school oversight.

**87.5%: seven of the same eight equally weighted pilot milestones meet documented local acceptance criteria.** This score measures pilot milestones, not complete product scope or production readiness. Milestone 7 (oversight/operations) is Verified; milestone 8 (production release) is In progress.

Last completed pilot checkpoint verification on 2026-10-15: **129 automated tests passed**. Django checks, migration drift and fresh SQLite migrations pass. A combined fresh-database workflow passed assessment publication, payment/reversal, admission approval, attendance correction, conditional batch progression, historical transcripts/fees, hidden student results and history-preserving reseeding. Dedicated reviewer regressions: 9 passed; parent policy/scope regressions: 4 passed, included in the full suite. PostgreSQL and hosted acceptance are unverified.

## Architecture and invariants

Django 5.2 modular monolith, server-rendered same-origin portals and database sessions. Username login remains. Active school memberships plus teacher assignments/student ownership determine scope; cached Python activity flags never substitute for database checks. No blanket superuser access to private records.

Permanent Student UUID/STU code does not change across years. Enrollment stores year/section/roll and preserves completed outcomes. Pending intake creates no identity; admin approval registers atomically. The separate walk-in registration path remains. Admin-only batch confirmation revalidates under locks, commits all rows or none, and retains PromotionDecision snapshots, conditional reasons and batch attribution. Portal links use the controlled admin account-link service.

Attendance session context and records reject normal direct rewrites. Reasoned correction proposals preserve old/new values; school admins approve/reject, and stale proposals are system-closed. Students retain their historical attendance and current upcoming/overdue/completed/graded workload.

Assessment snapshots/answers/raw marks/finalized policy values remain distinct; only admins finalize/publish. Finance balances are exact Decimal ledger sums; original receipts/payments survive reasoned reversals. Historical transcripts and fee statements survive promotion.

The new oversight app owns validated/versioned school settings, notice revisions, conflict-checked timetable slots and role-bounded summaries. Settings apply school timezone and four effective policies (late submission, correction age, student result visibility, notice expiry). Teacher notices are limited to assigned sections. Terminology/branding render on oversight pages; global themes and branded export are not claimed. Normal model/queryset/service guards protect histories; privileged raw SQL remains outside those guards.

## Resume

Read this file, `09_NEXT_ACTIONS.md`, `project_state.json` and impacted design files; inspect actual code. The previous durable baseline was `fcb97554497e8196078ffe6f2f242415965679dd` (75%); the 2026-10-15 increment rebuilds and verifies oversight. Migrations include students 0002/0003, learning 0004/0005 and oversight 0001. No pending migration drift is intended.

Use `../TESTING_MVP.md` for five-role synthetic workflows and `../PROJECT_REVIEW.md` for resolved findings and limits. Update affected Markdown/JSON, regenerate HTML with `python scripts/render_status.py`, and commit checkpoints with code. Next work is production validation and the separately tracked broader backlog; do not count code presence as release evidence.

## Production hardening in progress — 2026-10-15

Added DB-backed login/reset/MFA throttling, encrypted TOTP and one-use recovery, required/opt-in MFA session gates, strict production startup/proxy/cookie settings, private file scanning and guarded historical downloads, nonroot deployment/health/static configuration, concurrency fixes with eight PostgreSQL-only regressions, and guarded encrypted backup/restore scripts. Dependencies are pinned; pypdf was updated to 6.20.1 after a failed audit, and the repeat audit reports no known vulnerabilities. Bandit has reviewed narrow false-positive exceptions.

This checkpoint is a release candidate, not a production release. Last baseline full verification was129; new integrated verification and GitHub PostgreSQL/restore CI are pending. Local uid namespace maps only root and has no Docker, so PostgreSQL server startup is not available; do not bypass its root protection. A Playwright browser download also failed. Mark production milestone8 In progress, keep score87.5%, and replace these pending results with actual CI evidence before closing the gate.
