You are the lead QA and debugging agent for School-CMS. Clone the current release branch onto our PC, run the actual software locally, and test it as a working school across two academic years. Execute the work; do not stop at a plan or repeat earlier test results as your own.

Repository: https://github.com/HarisRiazGondal/School-CMS
Release branch: codex/production-hardening-20261015
Reference code checkpoint: 4a0680f7181aaf6b267941ab4b1785976841d4d4
The default main branch is an older snapshot. Record the actual checked-out commit and any subsequent changes.

1. Read before working

Read AGENTS.md, README.md and these files:
- docs/ai-context/00_PROJECT_MEMORY.md
- docs/ai-context/09_NEXT_ACTIONS.md
- docs/SCHOOL_SCENARIO_MATRIX.md — the 72-case starting checklist
- docs/SCHOOL_SCENARIO_RESULTS.md and docs/SCHOOL_EDGE_RESULTS.md
- docs/TESTING_MVP.md
- docs/PROJECT_REVIEW.md, docs/PRODUCTION_REVIEW.md and docs/RELEASE_REVIEW.md

The last recorded suite ran 227 tests: 218 passed, nine PostgreSQL-only skips, no failures. Two connected request/service journeys passed. These are historical baselines, not evidence that your PC or browser passes. Our cloud browser could not access the local URL; actual browser acceptance is still outstanding.

2. Use multiple agents with clear ownership

Prefer GPT-6 Luna workers when available. Otherwise use available capable agents and report that substitution. Use up to six workers concurrently plus yourself as coordinator; respect the runtime's limits and queue work when needed.

| Agent | Ownership and checks |
|---|---|
| 1 — Environment, authentication and safeguards | Python/dependencies, clean migrations, demo startup, login/logout/reset, CSRF, active/deactivated sessions, role boundaries, optional MFA, private-file validation and operational prerequisites. |
| 2 — Admissions and student lifecycle | Pending intake, approve/reject, duplicate rolls, permanent identity, guardians, individual/batch promotion, repeat/conditional/graduation, rollback, retained history and supported re-admission services. |
| 3 — Timetable, attendance and oversight | Teacher assignments, valid/conflicting schedules, room/section/teacher conflicts, attendance roster/duplicates, corrections/review/window boundaries, notices/audiences, settings/revisions and Asia/Karachi timing. |
| 4 — Learning, assessment and marks | Assignments, submission/revision/grading, question types, schedules/attempt limits, answer-key privacy, objective/manual marks, invalid marks, admin finalization/publication, visibility policies and historical report cards. |
| 5 — Fees and finance | Class/year fee plans, invoice matching, concessions, partial/full payments, receipts, duplicate/idempotent submissions, overpayments, reversals, exact balances, financial scope and post-promotion history. |
| 6 — Browser QA and independent review | Sole controller of the shared browser; execute the feature agents' UI cases, capture evidence, check responsive layouts/keyboard/labels/errors, independently reproduce reported bugs and verify fixes. |

Each worker must inspect real code, run relevant checks and report evidence. Give workers separate fixture databases/worktrees or serialize conflicting changes. Do not let several agents mutate the same browser session/database simultaneously. The coordinator owns shared settings, final integration, report consolidation and the last full regression run. Review fixes independently; an author's claim is not verification.

3. Prepare a safe local checkout

Use a new directory and QA branch; preserve any existing checkout, database and .env. On Windows PowerShell, use this as the starting sequence and adapt paths to the actual PC:

```powershell
git clone --branch codex/production-hardening-20261015 --single-branch https://github.com/HarisRiazGondal/School-CMS.git School-CMS-local-qa
cd School-CMS-local-qa
git switch -c qa/local-school-scenarios
git rev-parse HEAD
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path ".env")) { Copy-Item ".env.example" ".env" }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe scripts/school_scenario_acceptance.py
.\.venv\Scripts\python.exe manage.py seed_demo --password 'REPLACE-WITH-A-LOCAL-SYNTHETIC-PASSWORD'
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Replace the password placeholder. Use DEBUG=true, an isolated local SQLite database and loopback binding. Inspect inherited configuration first: never point tests at a real school database or real SMTP. Use synthetic pupil/guardian/contact details and record provisioning separately from browser workflows.

Open http://127.0.0.1:8000/ in the PC's permitted local browser. The demo users are demo-admin, demo-registrar, demo-teacher, demo-accountant and demo-student, using the supplied demo password. The school admin portal is /oversight/schools/demo-school/; Django's separate /admin/ maintenance interface requires a properly provisioned staff account.

For the existing automated browser smoke, install its separate dependencies and run it from another terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-e2e.txt
.\.venv\Scripts\python.exe -m playwright install chromium
npm ci --prefix tests/e2e
.\.venv\Scripts\python.exe scripts/browser_acceptance.py
```

The smoke owns a separate disposable database/server. It is not the complete 72-case school acceptance. If a dependency, browser or permission is unavailable, record the blocker accurately. Do not bypass browser/network security controls, expose the development server publicly, disable protections to make tests pass, or treat a Django test client as browser execution.

4. Test a realistic school lifecycle

Create an isolated Pakistan school fixture with Asia/Karachi timezone, two academic years, Classes 7 and 8, multiple sections, Mathematics/English, assigned and unassigned teachers, at least three pupils, guardians, a registrar, accountant and administrator, plus a second school for access-denial checks. Use dates consistent with the test clock. Record any setup through services/admin separately; do not claim unavailable portal forms were exercised.

Start with all 72 matrix cases, expand when inspection reveals further meaningful cases, and track every case individually. Include valid, invalid, duplicate/retry, unauthorized, stale-state and boundary inputs. Test actual browser interactions wherever a UI exists, and separately verify persisted outcomes.

Complete this linked journey in order:
- Registrar submits a pending admission; admin approves it; reject a separate application. Confirm stable student identity, correct enrollment and no partial records on failure.
- Schedule lessons, reject overlapping teacher/section/room bookings, take attendance, propose a correction and approve/reject it as the correct role.
- Publish homework, submit as the learner, grade as the assigned teacher and inspect feedback/history.
- Create an assessment with objective and manual questions; save/submit answers; reject an invalid mark; mark correctly; finalize/publish as admin; verify the student's report card.
- Issue a Class 7 fee of PKR 10,000. A PKR 3,000 payment must leave PKR 7,000 due. Verify the receipt, retries, overpayment rejection and reasoned reversal. Test concessions on a separate invoice/fixture so balances remain unambiguous.
- Preview promotion without writing, reject registrar confirmation and invalid targets, then promote as admin into Class 8. Confirm UUID/STU code persists and earlier marks, attendance, receipts and balances remain intact.
- Verify promotion creates no invoice automatically. Explicitly issue the Class 8/year plan for PKR 12,000 and confirm it does not overwrite or reprice the earlier invoice.
- Test repeat year, conditional placement with required reason, graduation without a target, rejection of graduation with a target, valid/invalid batch decisions and all-or-nothing rollback.
- Test students accessing other pupils, teachers accessing unassigned sections, outsiders guessing IDs, deactivated memberships and direct protected URLs.

Also inspect browser console/network errors, empty states, form-error visibility, repeated clicks, navigation/back/refresh, desktop/mobile layouts, keyboard focus and accessible controls. Run axe where available; automated checks do not replace human accessibility review.

5. Treat missing features honestly

Automatic invoice generation/repricing is not implemented. Promotion is an explicit administrative decision; marks/debt-driven automatic eligibility is not established. Withdrawal/re-admission and student-account linking have guarded services but lack dedicated regular-portal routes. Inspected notice/settings forms lack a dedicated revision-history viewer. Confirm these against the checked-out version and record product gaps; do not mark them passed or silently build new policy/financial automation.

SQLite cannot verify PostgreSQL row locks. If an isolated PostgreSQL service is legitimately available, run the suite against it, including tests.test_postgres_concurrency. Otherwise record the skips. Real scanner/signature, SMTP and full recovery checks need their services configured; mocks are not live-service evidence. Missing scanners must fail closed. Use approved local configuration for optional MFA; keep keys/passwords out of commits and reports.

6. Fix, verify and deliver

Reproduce confirmed bugs, add meaningful regressions where appropriate, and make minimal fixes within existing behavior. Preserve authorization, immutable history, exact Decimal finance, audit attribution and transactions. Do not implement new business rules without approval. Use isolated reviewable commits; do not merge main, force-push, deploy, spend money or change account/billing/security settings as part of this local QA task.

After fixes, rerun affected checks and the final full suite, migration drift and clean migration checks. Record actual totals; skipped/blocked/unsupported cases are not passes, and overlapping focused/full runs must not be added together.

Deliver:
- docs/LOCAL_PC_QA_REPORT.md — environment, OS/Python/browser, tested commit, commands, results, verified workflows and limitations.
- docs/LOCAL_PC_SCENARIO_RESULTS.csv — scenario ID, role, execution layer, expected/actual result, PASS/FAIL/BLOCKED/NOT RUN/UNIMPLEMENTED, evidence path and bug ID.
- docs/LOCAL_PC_BUG_REGISTER.md — severity, reproduction steps, expected/actual behavior, cause, fix commit and independent retest result.
- Screenshots and restricted diagnostic logs for actual UI checks, with no credentials or real pupil data.
- Updated affected docs/ai-context memory, test/release status and project_state.json; run python scripts/render_status.py.

Maintain brief progress updates while working. Finish with verified results, remaining bugs/product gaps and an explicit statement of whether actual local-browser testing ran. Do not claim “everything works,” 100% completion or production readiness unless the stated scope and evidence support it. Start now with repository inspection and parallel agent assignments.
