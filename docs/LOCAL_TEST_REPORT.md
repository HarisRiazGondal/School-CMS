# Local testing report and review index

Updated 15 October 2026 (Asia/Karachi). Current focus: test the local School-CMS pilot, fix reproducible defects, and prepare the user's own local acceptance. GitHub CI, VPS setup and hosted rollout are deferred by the user's instruction; they do not block the local checks below.

## Latest verification

**Final post-fix regression: 224 tests run, 215 passed, 9 PostgreSQL-only skips, no failures** (99.824 seconds). Python3.12.14 / Django5.2.18 / SQLite. The baseline retest also passed before the two fixes. Test the `codex/production-hardening-20261015` branch; the default main branch remains the earlier pilot snapshot.

Additional checks completed on disposable synthetic SQLite databases:

| Check | Observed result |
|---|---|
| Fresh database migration and synthetic seed |Passed |
| Five-role login/logout and portal journeys |Passed with CSRF-enforced Django HTTP clients |
| Linked-page crawl |73 role-scoped GETs; zero 404s, 500s or transport failures |
| Invalid forms |16 empty/malformed POSTs across eight forms; no server errors |
| Teacher/admin correction navigation |Teacher has no admin-review link; direct teacher access403; administrator access200 |
| Django system check / migration drift |Clean / no changes |
| Installed dependency compatibility |No broken requirements |
| Runtime dependency audit |No known vulnerabilities at this check |
| Bandit application-directory scan |No findings; existing narrow inline exceptions remain |

The 73 GETs are admin27, registrar12, teacher13, student13 and accountant8. These are role-scoped visits, not 73 distinct site routes. The invalid-form checks cover student registration, admission intake, assignment creation, fee plans, invoice issuance, school settings, timetable creation and notice creation. The full regression suite covers successful writes and retained histories separately.

Django HTTP-client checks exercise server-side behavior and HTML. They do not establish Chromium rendering, JavaScript execution, computed contrast, keyboard behavior or a completed axe scan.

## Bugs found and fixed in this pass

| Finding | Change | Verification |
|---|---|---|
| Excessively large financial values could raise an unhandled Decimal quantization error in service-level calls |Convert `InvalidOperation` into a Django validation error; preserve valid two-decimal behavior |Regression submits `1e999999` through fee-plan and payment services and verifies no financial writes; focused finance tests pass |
| Teacher oversight dashboard linked to the administrator-only attendance correction queue and displayed duplicate review information |Teacher action opens class attendance; only administrators receive the review-queue link/count |Post-fix role crawl confirms teacher link removal, teacher denial and administrator access |

The financial HTML forms already restrict amount size; the new guard also protects direct domain/service calls. The navigation fix changes the offered route while retaining the existing backend authorization.

## Functionality delivered so far

| Area | Implemented local pilot behavior |
|---|---|
| Accounts and access |Session login, POST logout, password-reset token flow, active membership/school scope, shared authentication throttling and optional local TOTP/recovery |
| School setup |Schools, campuses, academic years, terms, grades, sections, subjects and teaching assignments |
| Student operations |Pending admissions/decisions, registration, permanent UUID/STU identity, enrollment history and guarded individual/batch progression |
| Teaching and attendance |Assigned classwork, student submissions/revisions, grading/history, attendance, correction requests/admin decisions and student history |
| Assessment |Question banks, frozen assessment snapshots, attempts, objective/manual marking, administrator finalization/publication and historical report cards |
| Finance |Fee plans, invoices, exact two-decimal receivables, partial/full payments, immutable receipts and reasoned reversals |
| Oversight |Timetables, scoped notices, revisioned settings, effective policies and role dashboards |
| Hardening and operations |Encrypted MFA, private attachment validation/scanning/scope controls, auth-retention command, health/preflight, deployment configuration and guarded encrypted recovery tools |

Implementation of an operations tool does not mean its external service has been exercised locally. Global themes/branded exports, richer finance/accounting, guardian portal and other broader modules remain outside this pilot.

## Reports and reviews already available

| Document | What it contains |
|---|---|
| [LOCAL_TEST_REPORT.md](LOCAL_TEST_REPORT.md) |This latest local test result, new bug fixes and consolidated index |
| [PROJECT_REVIEW.md](PROJECT_REVIEW.md) |Functional/access/history review; fixes for stale scope, audit shortcuts, oversight writes and progression |
| [PRODUCTION_REVIEW.md](PRODUCTION_REVIEW.md) |Authentication/MFA, strict configuration, proxy trust, private-file and deployment safety review |
| [RELEASE_REVIEW.md](RELEASE_REVIEW.md) |Recovery/preflight review, retention and evidence boundaries; historical CI investigation |
| [TESTING_MVP.md](TESTING_MVP.md) |Your local setup, five demo roles and step-by-step admission/attendance/assessment/finance/promotion checks |
| [ai-context/08_TEST_RELEASE_STATUS.md](ai-context/08_TEST_RELEASE_STATUS.md) |Current test accounting and checks that remain unexecuted |
| [ai-context/PROJECT_STATUS.html](ai-context/PROJECT_STATUS.html) |Offline project dashboard generated from versioned state |
| [BROWSER_ACCEPTANCE.md](BROWSER_ACCEPTANCE.md) / [ACCESSIBILITY_ACCEPTANCE.md](ACCESSIBILITY_ACCEPTANCE.md) |Automated browser harness and remaining human accessibility checks |
| [RECOVERY_REHEARSAL.md](RECOVERY_REHEARSAL.md) / [RELEASE_PREFLIGHT.md](RELEASE_PREFLIGHT.md) |Recovery and runtime-check procedures, including their explicit limits |

Earlier reviews retain their historical test counts (for example129 or184). Use this report and the current test-release status for the latest totals; those snapshots are not separate tests to add together.

## Local checks still to perform

- Run the five-role checklist on your own computer, including layouts, keyboard navigation, field errors and complete workflows. Record the role, route, steps, expected/actual behavior and traceback for each issue, using synthetic data.
- A matching Chromium executable is absent in this workspace. Playwright is installed, but browser/axe execution remains unverified. Do not interpret the HTTP-client passes as a browser pass.
- Nine tests require PostgreSQL and skip under SQLite: eight concurrency cases and one live preflight check. A review also identified an enrollment/assessment-start race candidate for later PostgreSQL investigation; it has not been reproduced and is not counted as a confirmed local defect.
- Reset emails use console output locally. Actual SMTP delivery, live ClamAV scanning and real PostgreSQL/full recovery need those local services configured. Attachment scanning intentionally fails closed when a scanner is unavailable. Optional local MFA enrollment needs a separate Fernet key configured first.

No failures in these checks establishes coverage of the cases exercised, not absence of every possible bug. Hosting and production acceptance can resume separately when requested.
