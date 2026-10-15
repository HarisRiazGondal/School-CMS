# School lifecycle scenario results

15 October 2026 · Synthetic records only · Release branch `codex/production-hardening-20261015`.

## Scope and current outcome

The requested school scenario plan is [SCHOOL_SCENARIO_MATRIX.md](SCHOOL_SCENARIO_MATRIX.md):72 scenarios for admissions/identity, schedules/notices, attendance/corrections, assignments/marks, fees and progression/history. It is broader than the automated journeys below. These results do not assert that every matrix input was executed.

The cloud-browser stage is **blocked**. Opening the local application address was rejected by the browser URL security policy; the browser then explicitly prohibited workarounds, indirect execution, proxying or alternate browser surfaces. No workaround or alternate browser was used after that restriction. No cloud-browser scenario passed, no screenshots were collected, and no visual or axe result is claimed. A permitted, browser-accessible test deployment is needed for the actual UI stage.

Independent, in-process Django request/service checks were completed using disposable test databases. They do not perform network access to the blocked address or turn the blocked browser test into a pass.

## Executed evidence

| Check | Result |
|---|---|
| Connected service-level school lifecycle |Passed |
| Five-role request/form/CSRF lifecycle |Passed |
| Isolated scenario runner |2 tests passed, no errors/failures/skips; JSON evidence below |
| Focused edge/lifecycle regressions |78 passed before the new graduation regression |
| Graduation fix/student suite |26 passed after the guard fix |
| Final integrated suite |227 run, 218 passed, 9 PostgreSQL-only skips, no failures (103.664s) |
| PostgreSQL concurrency module |8 skipped on SQLite; not passes |
| Browser, visual, keyboard, axe |Blocked by cloud-browser URL policy |

Machine-readable evidence: [school_scenario_evidence.json](school_scenario_evidence.json). Run `python scripts/school_scenario_acceptance.py` to reproduce the two connected journeys on isolated SQLite. The runner parses actual test counts and reports failure when either journey is missing, fails or skips. It sends no external email, starts no browser, makes no network requests and discards its temporary database.

## What the request-level journey actually did

The Crescent Model School fixture has Class 7 in 2026–27 and Class 8 in 2027–28, Mathematics, a teaching assignment and five synthetic role accounts. Academic setup, accounts and the explicit student-account linking step are fixture/service preparation; they are not claimed as portal UI operations. Everything else below goes through CSRF-enforced Django views/forms, with database assertions after the responses:

1. Registrar signs in and submits Ayesha Example's pending admission; the learner has no permanent identity yet. A registrar decision attempt leaves it pending. Administrator approval creates the student and first enrollment.
2. Administrator schedules Monday Mathematics 09:00–09:45 in room R-7. An overlapping slot is rejected; only the first remains.
3. Teacher records the learner absent, requests a reasoned correction, and administrator approval changes the mark to present while preserving correction history.
4. Teacher publishes an assignment; student submits work; teacher records 88.00 with feedback.
5. Teacher creates an assessment, objective and manual questions, attaches/opens it; student starts and submits. An over-maximum manual mark is rejected. A valid 2.50/3 mark plus objective 2/2 produces 4.50/5. Teacher finalization is denied; administrator finalizes/publishes; student report card shows the result.
6. Accountant creates class/year plans for PKR 10,000 andPKR 12,000. Plans alone produce no invoices. The Class 7 invoice is explicitly issued for PKR 10,000; a PKR 3,000 payment produces a receipt and leaves PKR 7,000 due.
7. Registrar previews promotion without mutation and cannot confirm. Administrator confirms Class 8 placement. Permanent UUID/STU code remain unchanged; the earlier enrollment is marked promoted and links to the successor.
8. Promotion itself produces no invoice. Accountant explicitly issues the Class 8 invoice for PKR 12,000. The earlier balance remainsPKR 7,000, both years remain in the student's statement, and the old assessment remains in the transcript.
9. Accountant reverses the earlierPKR 3,000 payment with a reason. Class 7 balance returns to PKR 10,000; the original receipt remains accessible.

The separate service journey also verifies rejection without student creation, teacher booking conflicts, cross-school denials, duplicate invoice/payment/reversal behavior, a PKR 1,000 concession, and occupied-roll/cross-school promotion refusal. Its concession example isPKR 10,000 minusPKR 1,000 = PKR 9,000; a PKR 3,000 payment leaves PKR 6,000 and reversal restores PKR 9,000. These are separate fixtures, not contradictory balances for the same invoice.

## Bug reproduced and fixed

**Graduation accepted a target placement at the individual service boundary.** The regular form and batch path rejected that combination, but `preview_promotion` and its commit caller silently ignored a supplied target year/section and could graduate the student anyway. A new regression failed before the fix. Preview now rejects any nonempty graduation target before changes are made; commit uses that same guard. Post-fix assertions verify active status, enrollment count and audit count remain unchanged for year-only, section-only and combined targets. The focused 26-test student run passed.

## Product and test gaps found

| Gap | Meaning |
|---|---|
| Automatic invoice/fee generation |Not implemented. Supported: class/year fee plan plus explicit accountant invoice issuance. Promotion preserves old balances and does not reprice posted invoices. |
| Automatic result/fee-driven promotion eligibility |Not asserted by this workflow. Current progression is an explicit administrative decision; the scenario does not prove a policy engine links marks or debts to promotion. |
| Withdrawal/re-admission and student-account linking portal actions |Guarded services exist; dedicated regular-portal forms/routes are absent. Fixture/service preparation does not establish a complete UI workflow. |
| Dedicated revision-history viewer |Published notice/settings revisions are retained at model/service level; the inspected edit templates do not offer a dedicated history viewer. |
| Cloud browser |All72 matrix browser rows remain blocked/unverified. Server-side HTML responses do not prove rendering, JavaScript, keyboard focus, responsive layout or console behavior. |
| PostgreSQL concurrency |Nine full-suite cases require PostgreSQL; SQLite cannot verify row locks or real simultaneous-operation behavior. The previously noted assessment-start/enrollment-close race remains unverified. |
| External services |Live scanner/signatures, real SMTP delivery, persistent-file recovery and production hosting were not exercised. Their fixture/configuration tests are separate evidence. |

See [SCHOOL_EDGE_RESULTS.md](SCHOOL_EDGE_RESULTS.md) for exact edge-regression mappings and [LOCAL_TEST_REPORT.md](LOCAL_TEST_REPORT.md) for earlier local checks. Continue actual UI acceptance from the matrix when a permitted browser target is available. Do not count the 72-row plan, two connected journeys and full-suite total as disjoint tests or add them together.
