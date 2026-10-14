# Test and Release Status

**Local pilot ready for testing. Production release: Not started.**

Environment: Python 3.12, Django 5.2, SQLite. Latest integrated test suite: **48 tests, all passed**. No counts are inferred from planned tests.

| Check | Result |
|---|---|
| DJANGO_DEBUG=true python manage.py check | Passed, no issues |
| DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run | Passed, no pending model changes |
| DJANGO_DEBUG=true python manage.py migrate --noinput | Passed |
| DJANGO_DEBUG=true python manage.py test | 48 passed |
| Fresh SQLite migrations and seed_demo twice | Passed, synthetic fixture idempotent |
| git diff --check | Passed |
| PostgreSQL, hosted acceptance, accessibility, real SMTP/restore | Not run |
| GitHub Actions CI | Workflow added; remote execution not claimed |

Coverage: academic scope/campus/term constraints, authentication/CSRF/reset/deactivation, student identity/year/roll/history/progression, protected normal ORM writes, role/service/HTTP scope, attendance duplicates, submissions/revisions/grading and audit payload/append guards. HTTP tests render pages and submit forms; they do not replace interactive human browser acceptance.

Scoring: four of eight defined pilot milestones verified locally = 50%. Full phase/release acceptance remains open.

- [x] Local clean schema and role workflows tested with synthetic data.
- [x] Individual student progression preserves prior-year placement.
- [x] Teacher/student core workflows scoped and tested.
- [ ] Full admissions/batch/conditional/correction requirements.
- [ ] Assessment, finance and complete oversight.
- [ ] PostgreSQL, throttling/MFA, SMTP, private uploads and restored backups.
- [ ] Hosted pilot, accessibility review and production authorization/privacy review.
