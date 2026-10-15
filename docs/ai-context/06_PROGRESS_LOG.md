# Progress Log

## 2026-10-14 — Pilot increment to four verified milestones

Baseline: repository checkpoint `309c3d3bfcb7c2edc9e7df5dabdf936d7a5dab15` had foundational schema and four tests. Multiple GPT-6 Luna agents owned auth, identity, learning, audit, operations and independent security review; parent integrated academic constraints, pilot HTTP tests, CI and status generation.

Changed domains: accounts/session middleware and auth templates; academics Term/Campus constraints and migration; new students, learning and audit apps with migrations; synthetic demo command; scoped role portals; tests; README/operations/testing docs; AGENTS.md; GitHub checks workflow; scripts/render_status.py and project_state.json; all affected AI-context files and HTML.

Verified: system check, migration-drift check, migration application and **48 automated tests passed**. Fresh SQLite database migration plus demo seeding twice retained stable counts. Browser HTTP tests cover CSRF logins, all role dashboards, attendance, student submission, promotion preview/non-writing, denied registrar confirmation, authorized admin confirmation and retained history. No hosted browser or production PostgreSQL acceptance is claimed.

Fixed during review: inactive-session cleanup; cross-school section saves; teacher/student inactive-school scope; constructed-instance identity/history mutations and protected queryset writes; active re-admission conflicts; registration/promotion database-race errors; overlong generated codes; post-grade submission edits and grade revision history; seed history reset.

First four of eight defined pilot milestones meet local acceptance criteria (50%). Phases 1–3 remain In progress for broader requirements. Assessment, finance, complete oversight and production rollout remain unimplemented.

Next: complete admissions decisions and batch/conditional promotion with conflict previews and rollback tests, then attendance corrections before expanding assessment/finance.

## 2026-10-14 — Assessment and finance checkpoint (75%)

Base checkpoint: `fde9149f11e9291ee675e7c29731835387906b9e`. Six Luna agents handled assessment core/UI, finance core/UI, demo/docs and independent review; parent integrated routes/dashboard, activation guards, status documents and publication.

Changed: new assessment and finance apps/services/forms/templates/URLs/migrations/tests; demo-accountant and safe assessment/invoice fixtures; dashboard links; learning/accounts active-state queries; operations/test guide/README; all affected memory documents and generated status.

Acceptance: **79 tests passed**; Django check, migration drift, migrate and whitespace check passed. Fresh SQLite acceptance covered scoring/manual grading/admin publication, partial payment/receipt/reversal, promotion with old transcript/fee history and idempotent reseeding. Expected denial tests pass. PostgreSQL and hosted acceptance were not run.

Review fixes: duplicate-invoice DB uniqueness and friendly race handling; exact Decimal totals instead of SQLite SUM residue; required reversal reason; unpublished/other-school results and stale enrollment denial; per-attempt publication without closing other students' window; finite marks/high configured pass threshold; safe admin report selector; late-body exclusion; database activation checks for stale User/School objects.

No IELTS code was copied. Progress is six of the unchanged eight pilot milestones (75%). Operations/oversight and production release remain open; broad unfinished module scope is documented rather than counted as released.

## 2026-10-15 — Oversight and operations checkpoint (87.5%)

Base: `fcb97554497e8196078ffe6f2f242415965679dd` (verified 75%). Six GPT-6 Luna agents owned student operations, attendance, oversight core/UI, demo/docs and independent review; parent integrated policies, activation/audit guards, cross-module acceptance and the checkpoint. Interrupted uncommitted oversight work was rebuilt from the durable baseline rather than counted as complete.

Changed: admission intake/decisions, controlled student account linking, batch/conditional progression and immutable attributed snapshots; guarded attendance session/record writes, corrections and student history/workload; new oversight app (settings/revisions/policies, timetable, notices/revisions, summaries and scoped Admin); demo/test/operating docs; root routes/navigation; all affected memory/JSON and generated status. Additive migrations: students 0002/0003, learning 0004/0005, oversight 0001.

Verified: **129 tests passed**, checks/drift/whitespace clean; fresh SQLite migrations and combined publication/payment-reversal/admission/correction/conditional-batch/history/policy/reseed acceptance passed. Independent reviewer regressions9 and parent scope/policy regressions4 are included. PostgreSQL, hosted acceptance and remote CI success remain unverified.

Review fixes: cached activation, audit/history queryset bypasses, forged promotion decisions, conditional reason preview wiring, stale teacher timetable rows, timetable Admin relation scoping, notice source/target authorization, school settings serialization, atomic notice/timetable audit writes and attendance session recontextualization. No unresolved local blocker is known within the reviewed pilot scope; production and broader-module limits remain explicit.

Seven of eight unchanged local pilot milestone gates now meet criteria (**87.5%**); production release remains Not started. Next: PostgreSQL concurrency and deployment/security/SMTP/restore/hosted acceptance.
