# Test and Release Status

**Expanded local pilot ready for testing. Production release: Not started.**

Latest integrated verification on 2026-10-15: **129 tests passed** in 77.553 seconds on Python 3.12 / Django 5.2 / SQLite.

| Check | Evidence |
|---|---|
| `DJANGO_DEBUG=true python manage.py check` | Passed, no issues |
| `DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run` | No changes detected |
| Fresh SQLite `migrate --noinput` | Passed |
| `DJANGO_DEBUG=true python manage.py test -v 1` | 129 passed |
| Dedicated independent review regressions | 9 passed, included in integrated suite |
| Parent policy/scope integration regressions | 4 passed, included in integrated suite |
| Fresh SQLite combined service acceptance | Publication; payment/reversal; admission/correction approvals; conditional batch; historical transcripts/fees; result hiding — passed |
| Demo reseed after finalized operations and changed settings | Counts/history preserved |
| `git diff --check` | Passed |
| PostgreSQL, hosted human/accessibility/privacy acceptance, real SMTP/restore | Not run |
| GitHub Actions | Workflow exists; remote success is not claimed by local tests |

New coverage includes admission approval/rejection/retries and rollback; account-link safeguards; batch preview/conflicts/conditional reasons/graduation/revalidation and atomic rollback; immutable attributed decisions; session/attendance ORM guards; correction approval/rejection/staleness/attribution; own attendance history and workload; effective settings/timezone; notice scope/revisions/audit rollback; timetable overlaps and active teacher scope; role-bounded summaries; scoped read-only Admin; cached activation and append-only audit regressions. The baseline assessment and financial coverage remains included.

Seven unchanged pilot milestone gates meet local acceptance = **87.5%**. Broader module scope and production release remain open. HTTP render/form tests supplement services; interactive human browser/accessibility/hosted acceptance is still required. Expected permission-denial logs are exercised by passing authorization tests.

- [x] Admissions decisions and individual/batch/conditional yearly progression.
- [x] Guarded attendance, correction decisions and student history/workload.
- [x] Scoped timetable/notices/settings/dashboards and independent bug review.
- [x] Assessment and finance history retained through progression/reseed.
- [ ] PostgreSQL concurrency, restore and production operating controls.
- [ ] Throttling/MFA, SMTP, private files, accessibility and hosted human pilot.

## Production release candidate — validation running

The 129-test result above is the prior checkpoint. New auth, private-files, configuration, operations and review suites pass locally. Eight PostgreSQL concurrency tests deliberately skip on SQLite. The first new integrated suite had183 tests with one deadline-test failure caused by advancing the shared clock beyond the new one-hour session expiry; the test now isolates deadline behavior with a longer fixture session and its33-test affected suite passes. The final full suite and PostgreSQL CI run are pending. Dependency audit is clean after upgrading pypdf6.20.1; static collection and source scan pass. PostgreSQL/Docker, real SMTP/ClamAV/private-volume restoration and human hosted acceptance are not yet established.
