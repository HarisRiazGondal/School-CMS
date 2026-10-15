# Test and Release Status

## Latest school scenario checkpoint

**227 run,218 passed,9 PostgreSQL-only skips,no failures** in103.664s. Connected scenario runner:2 request/service lifecycle tests passed with actual CSRF/forms/views and domain checks; no browser/network transport. Post-fix student suite26 passed; prior independent edge suite78 passed. These are included/overlapping counts, not additive.

New graduation guard was reproduced red then passed after fix. Browser URL security policy blocked the local target; all72 planned browser rows remain unverified. Automatic class/year invoice generation is not implemented; explicit staff invoice issuance preserves old/new-year fees and history. See [scenario results](../SCHOOL_SCENARIO_RESULTS.md), [matrix](../SCHOOL_SCENARIO_MATRIX.md) and [JSON evidence](../school_scenario_evidence.json).

## Earlier local evidence


## Latest local acceptance — user-requested focus

**224 tests run, 215 passed, 9 PostgreSQL-only skips, no failures**, final post-fix run99.824s. Five-role CSRF HTTP journeys,73 role-scoped linked GETs and16 malformed form POST cases pass; no 404/500/transport failures in the final crawl. Fresh SQLite migrations, checks/drift, dependency compatibility/audit and application source scan pass.

Fixed two reproduced defects: excessive financial Decimal magnitude now raises ValidationError without writes; teacher oversight no longer links to the administrator review queue, while backend denial remains enforced. Browser/axe has not run (Chromium absent); nine PG-only tests skip. CI/VPS work is deferred. See [LOCAL_TEST_REPORT.md](../LOCAL_TEST_REPORT.md) for the complete evidence and review inventory.

## Prior release-validation checkpoint

**Release candidate; production acceptance pending. Pilot score 7/8 (87.5%).**

Final 2026-10-15 integrated local run: **223 tests run, 214 passed, 9 PostgreSQL-only skips, no failures**, Python3.12 / Django5.2.18 / SQLite. The skips are eight concurrency tests and one live PostgreSQL preflight test. They are not PostgreSQL passes.

| Check | Actual evidence |
|---|---|
| Final SQLite suite |214 passed, 9 PostgreSQL-only skips |
| Django check / migration drift |Clean / no changes |
| Fresh SQLite migrations |Passed including accounts0003 retention index |
| Dependency audit |No known vulnerabilities |
| Bandit Django application directories |0 findings; narrow reviewed inline exceptions; scripts excluded |
| Recovery bundle fixtures |Authentication/tamper/path/cleanup/disposable guards pass; PG subprocess mocked |
| Runtime preflight tests |Production checks fail/blocked on development setup as intended; no default probes |
| Release state validation |Rejects inconsistent totals, changed denominator/production criteria, incomplete gate evidence and inconsistent readiness |
| Browser bootstrap |Synthetic seed/server works; Chromium download corrupt at 0 MiB; browser/axe not run |
| Shell/Python/YAML/contracts/whitespace |Passed |
| Prior GitHub run #7 at 2fd821a |Failure, zero jobs, logs unavailable; no runtime evidence |
| Corrected PostgreSQL/recovery/browser/container CI |Configured; new exact-commit hosted run must be inspected |
| Target SMTP/TLS/ClamAV/volume/full recovery |Not exercised |
| Hosted human/privacy/accessibility pilot |Not performed |

The CI regression assertion was narrowed after integration revealed that runner context is valid in step-level artifact paths but unavailable in job-level env. Preflight's real PostgreSQL regression now uses a database-capable TestCase; SQLite skips it explicitly. The final integrated suite passed after corrections. Source-scan exceptions cover fixed Git argv and trusted configured scanner argv with no shell; SMTP close failures are reported rather than silently ignored.

The independent review found and closed restore code synthesizing disposable attestations, mismatched create/restore bundle size limits, and a DNS re-resolution window. Restore now requires caller attestations, a separate production database identity and disposable private-root acknowledgment. Complete encrypted bundles include quarantine/private files as well as the database. These local guards do not establish a successful real recovery.

Prior unchanged candidate evidence remains: static collection127 assets and synthetic production deploy checks pass with staged HSTS W005/W021 warnings. No Docker/PostgreSQL/browser runtime pass is claimed locally. See the gate matrix in project_state.json/PROJECT_STATUS.html and RELEASE_REVIEW.md. Main and the eight acceptance milestones remain unchanged; keep PR #1 draft.

## Hosted CI blocker confirmed after publication

Runs #8/#9 at 6e3b0a6558267ca3cbed8a3696811e4f5cea73eb each created five jobs but no runners or steps. The public job annotation confirms: "The job was not started because your account is locked due to a billing issue." The account owner must resolve this outside the repository before rerunning CI. No PostgreSQL, recovery, container or browser CI pass occurred.

Verified annotation: https://github.com/HarisRiazGondal/School-CMS/actions/runs/38771801513/job/116549229916

Follow-up CI configuration sets `DJANGO_SETTINGS_MODULE=schoolcms.settings` for standalone production-check Python and pins Ubuntu24.04 before the announced ubuntu-latest migration. Operations regressions pass7/7; no hosted execution is claimed. Keep milestone8 In progress and the score87.5%.
