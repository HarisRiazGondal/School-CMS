# Independent project review

Latest local acceptance (15 October2026): **224 run,215 passed,9 PostgreSQL-only skips,no failures**, after the financial-validation and teacher-navigation fixes. See [LOCAL_TEST_REPORT.md](LOCAL_TEST_REPORT.md) for the consolidated report and index. Earlier counts below are historical snapshots; CI/VPS work is currently deferred.


## Scope

Reviewed the active student identity and enrollment safeguards, live membership and school authorization checks, assessment transcript access, finance statement and invoice access, audit event write paths, and the milestone 7 oversight models and services. Review focused on cross-school access, stale authorization state, queryset write shortcuts, retained history, and the project test baseline.

## Findings and changes

- **Closed: stale membership authorization.** Membership and school activity are checked against the database in `active_school_memberships`, assessment enrollment/transcript access, and finance invoice/statement access. The new regression test prefetches memberships, deactivates one in the database, then verifies access is denied.
- **Closed: audit queryset write shortcuts.** Audit events reject queryset `update`, `delete`, `bulk_update`, and `bulk_create`; the regression suite verifies these paths cannot alter or add event rows.
- **Closed: oversight history and validation bypasses.** School setting and notice writes use guarded querysets; revision rows reject queryset changes and deletes; timetable changes reject queryset write shortcuts; attendance correction requests reject queryset creation, mutation, and deletion. Regression tests cover these ORM paths, including a forged correction approval and a timetable overlap update.
- **Closed: oversight Django Admin scope.** Oversight admin registrations are now read-only and limited to active school-admin memberships, including for superusers. Changes should go through the scoped school portal and services.
- **Closed: conditional decision preview.** The individual promotion preview now passes the required condition reason to the validation service; the batch preview carries the reason through confirmation. Review tests exercise both flows and verify the persisted decision is attributed to the confirming school admin.
- **Closed: live timetable scope.** Student timetables now require the assigned teacher's active account and active same-school teacher membership. The timetable Admin queryset also applies school scope through its assignment relation.

## Verification

- Dedicated review regressions: `DJANGO_DEBUG=true python manage.py test tests.test_review_regressions -v 1` — **9 tests passed**; Django system check clean.
- Migration drift: `DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run` — **No changes detected** after adding the promotion decision migration.
- Final parent integrated run: `DJANGO_DEBUG=true python manage.py test -v 1` — **129 tests passed**. The missing promotion migration and conditional preview integration errors are resolved.
- Parent fresh SQLite combined acceptance passed publication, payment/reversal, admissions/corrections, conditional batch, historical access and safe reseeding. Four parent policy/scope regressions also pass, including denial of notice takeover by changing its target section.
- PostgreSQL concurrency, hosted deployment, SMTP, private-file handling, backup restoration, and human pilot acceptance were not verified in this review. Application-level guards do not protect against privileged raw SQL.

## Next review action

No unresolved local blocker is known within the reviewed pilot scope. Keep PostgreSQL locking/concurrency, production security/privacy, backup restoration, accessibility and hosted human acceptance as release gates; automated review does not establish absence of all defects.
