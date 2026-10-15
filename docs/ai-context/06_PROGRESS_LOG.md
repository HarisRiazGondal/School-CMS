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

## 2026-10-15 — Production hardening release candidate

Added auth/MFA, strict settings, private files, concurrency regressions/fixes, deployment/recovery tooling and accessibility semantics with six Luna owners including independent review. Local targeted suites/scans pass; integrated suite, PostgreSQL CI and target-host acceptance remain in progress. Pilot score remains87.5%; production milestone 8 is In progress.

### Production candidate local validation and first CI attempt

Final local suite 183 run/175 pass/8 PG skips; checks/drift, dependency/source scans and static collection pass. Deadline fixture was isolated from the new session expiry and affected tests pass. Candidate saved in draft PR #1; first CI failure has no retrievable logs/steps, so no PostgreSQL/container/restore success is claimed. Consolidated jobs into the existing workflow and added a container build/nonroot-manifest smoke job. Production milestone 8 remains In progress, score 87.5%.

### Final local release-candidate checkpoint

Final suite 184 run/176 passed/8 PG skips after testing cleanup of temporary pgpass files on early backup validation failure and sanitizing/uniquely naming encrypted artifacts. Status renderer now displays the actual production milestone state. User selected existing VPS; host/domain/access remain missing. CI initial run and retry report failure, with both log requests returning404 and steps empty; the latest workflow run is not returned. No PG/container/restore success is claimed; PR #1 remains draft.

## 2026-10-15 — Release validation and recovery checkpoint

Six Luna owners handled CI, combined recovery, browser acceptance, runtime preflight, independent review and authentication retention. Parent integrated evidence-accounting guardrails and final status/docs. Changed: complete authenticated database/private-file recovery bundles and disposable rehearsal; no-network-by-default preflight with explicit operator probes; loopback synthetic five-role Playwright/axe runner; corrected CI job-env context and hosted harness wiring; bounded dry-run auth-throttle retention plus accounts0003 index; release-gate matrix and validator.

Review fixes: restore no longer manufactures disposable attestations; complete bundle size bounds match restore; preflight pins validated IP through verified TLS; live PG test can query its database; browser runner isolates inherited settings and keeps CSP intact; expected denial diagnostics are narrowly scoped. Exact-document wording assertions were excluded from the final regression suite.

Final local validation: **223 run, 214 passed, 9 PostgreSQL-only skips, no failures**. Django check/drift, fresh SQLite migrations, dependency audit, application-directory Bandit, script syntax/compilation and whitespace checks pass. Chromium install returned corrupt 0 MiB archive; browser runtime not run. Previous GitHub run#7 failed with zero jobs/logs unavailable; current correction still needs hosted verification. Target VPS connection/domain, real SMTP/scanner/persistence/recovery and human acceptance remain open. Score stays87.5%, PR draft, main unchanged.

### Hosted run diagnosis after publication

Runs #8/#9 at 6e3b0a6558267ca3cbed8a3696811e4f5cea73eb each created five jobs but no runners or steps. The public job annotation confirms: "The job was not started because your account is locked due to a billing issue." The account owner must resolve this outside the repository before rerunning CI. No PostgreSQL, recovery, container or browser CI pass occurred.

The connector could read jobs/check-run counts but could not read annotations; a public browser inspection of the exact job page exposed the billing-lock error without sign-in. No billing/payment or account setting was changed. The workflow now sets the settings module for standalone Python and pins Ubuntu24.04 against the announced runner-image migration. Targeted operations checks pass7/7. Account-owner action and VPS details remain blockers to production100.

## 2026-10-15 — Local testing, two bug fixes and report handoff

User deferred CI/VPS prerequisites and requested local bug testing plus an inventory of reports/reviews. Parent reran a clean dependency setup and full suite; two existing Luna reviewers independently inspected workflows and local HTTP behavior. Baseline223-run suite passed. Review reproduced a Decimal quantization exception for huge financial values; it now returns ValidationError, with a service regression asserting no financial writes. Local link crawling exposed a teacher dashboard action into the administrator-only correction queue; template now offers class attendance and restricts the review queue/count to administrators. Backend scope is preserved.

Final post-fix suite: **224 run,215 passed,9 PostgreSQL-only skips,no failures** in99.824s. Fresh SQLite migrations/seed, five-role CSRF client journeys,73 role-scoped GETs,16 invalid-form POSTs, checks/drift, dependency compatibility/audit, application Bandit and whitespace pass. Chromium absent; no browser/axe pass claimed. Enrollment/assessment-start PostgreSQL race remains an unverified review candidate.

Added LOCAL_TEST_REPORT.md with feature/review index and current evidence; extended TESTING_MVP Windows/local handoff; updated review pointers and all affected memory/state/HTML. New focus is user local acceptance and reproducible issue capture; hosted release gates remain separately open, without asking for deployment details now.

## 2026-10-15 — Realistic school scenarios and connected request/service acceptance

Defined72 school scenarios before lifecycle acceptance, using synthetic Pakistan school data and Class7/8 PKR10,000/12,000 fee examples. Cloud browser rejected the local URL and explicitly prohibited workarounds; no further browser/proxy attempt was made. Actual UI stage remains blocked, with zero browser passes.

Added repeatable isolated scenario runner, one cross-module domain test and one five-role CSRF/form/view journey. Verified admission/denial/approval, timetable conflict, attendance correction, classwork88/feedback, assessment4.50/5/admin publication, partial payment/reversal, promotion/new-year invoices and retained UUID/STU/transcript/financial history. Explicit invoice issuance works; automatic billing is absent. Inspection also found regular-portal gaps for withdrawal/re-admission/account linking and revision-history viewing.

Reproduced and fixed individual graduation with supplied target fields being silently accepted; preview/commit now reject before mutations. New regression checks status/enrollment/audit invariants. Student-focused26 passed. Final full suite **227 run,218 passed,9 PostgreSQL-only skips,no failures** (103.664s); two connected journeys pass; checks/drift, compilation/application source scan and whitespace clean. New matrix/results/edge report/JSON and affected memory/state/HTML record partial evidence honestly. User goal of actual cloud-browser testing still needs a permitted accessible test target; no claim of all72 scenarios passed or production closure.
