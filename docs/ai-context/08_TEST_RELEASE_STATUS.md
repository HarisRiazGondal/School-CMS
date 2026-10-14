# Test and Release Status

**Expanded local pilot ready for testing. Production release: Not started.**

Latest integrated suite: **79 tests, all passed**, Python 3.12 / Django 5.2 / SQLite.

| Check | Evidence |
|---|---|
| DJANGO_DEBUG=true python manage.py check | Passed, no issues |
| DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run | Passed, no pending changes |
| DJANGO_DEBUG=true python manage.py migrate --noinput | Passed |
| DJANGO_DEBUG=true python manage.py test | 79 passed |
| Fresh SQLite migrate + combined service workflow | Passed: scoring/publication, payment/receipt/reversal, promotion/history |
| Demo reseed after those operations | Preserved attempts/answers/payment/receipt/ledger/invoice/question counts |
| git diff --check | Passed |
| PostgreSQL, hosted acceptance, real SMTP/backup restoration | Not run |
| GitHub Actions | Workflow exists; remote CI success is not claimed by local tests |

New coverage: bank snapshots; MCQ/true-false/exact short answer/manual scoring; attempt limits/schedules/deadline writes; complete admin-only finalization/publication; immutable results and historical transcripts; authoring/student scope; admin selector UUID/scope; Decimal partial/full payment, currency/amount validation, idempotency, reversals/reasons, immutable receipt/ledger, history, reconciliation and CSRF/role denials. Baseline 48-test coverage remains included.

Six unchanged pilot milestone gates meet local acceptance = **75%**. Broader phase requirements and production release remain open. HTTP-render/form tests supplement service tests; interactive human browser/accessibility/hosted acceptance is still required.

- [x] Pilot assessments and report-card/transcript journey verified.
- [x] Pilot fees/payment/receipt/reversal journey verified.
- [x] Fresh SQLite migrations and safe repeatable demo setup verified.
- [ ] Complete admissions/batch/conditional/attendance correction/oversight.
- [ ] PostgreSQL financial concurrency and restore verification.
- [ ] Throttling/MFA, SMTP, private files, accessibility and hosted pilot.
