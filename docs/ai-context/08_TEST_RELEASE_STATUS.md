# Test and Release Status

- Phase: Phase 1 — Foundation, in progress.
- Release: Not started.
- Verification environment: clean clone of the default branch with dependencies installed.
- Passed: python manage.py check; python manage.py makemigrations --check --dry-run; python manage.py migrate --noinput; python manage.py test.
- Test result: 4 tests passed.
- Not yet verified: production PostgreSQL run, secure login/password reset, object-level authorization, uploads, deployment, accessibility, backup/restore, and browser flows.

## Release gates

- [x] Foundation source and initial migrations run cleanly in a local SQLite verification.
- [ ] Secure authentication and scoped permissions tested end-to-end.
- [ ] Student identity/enrollment/promotion lifecycle tests pass.
- [ ] Attendance, assessment, and financial invariants tested.
- [ ] Private uploads, backups, restore, and deployment verified.
- [ ] Pilot role journeys accepted.

Phase 1 remains In progress because authentication, object-level authorization, and future domain workflows are incomplete.
