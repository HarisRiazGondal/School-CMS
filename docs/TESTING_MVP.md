# MVP test and browser acceptance guide

## Automated checks

Run these from the repository root with the project environment active:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
```

`makemigrations --check --dry-run` must report no model changes pending. The test suite covers the supported account and school workflows, identity/enrollment lifecycle, learning workflows, and authorization boundaries. Run it against a fresh local database when validating a clean checkout.

## Synthetic browser demo

Create or refresh the demo data in a development environment:

```sh
python manage.py seed_demo --password 'choose-a-local-demo-password'
python manage.py runserver
```

Visit <http://127.0.0.1:8000/> and use the password supplied to the command with one of these usernames. The dashboard is at `/`; student records are at `/students/demo-school/students/`; the role-scoped learning portal is at `/learning/`.

| Role | Username | Acceptance path |
| --- | --- | --- |
| School admin | `demo-admin` | Sign in, then open student records and the learning portal. |
| Registrar | `demo-registrar` | Open `/students/demo-school/students/` and verify the current-year enrollment. |
| Teacher | `demo-teacher` | Open `/learning/` and see the assigned class section. |
| Student | `demo-student` | Open `/learning/` and see the learner's active enrollment and published classwork. |

These usernames and all names/records are synthetic. The command does not embed a password; the operator supplies one. It refuses to run when `DEBUG` is false. Run the command twice with the same password to verify it remains idempotent: it should not create duplicate school, memberships, year, section, students, enrollments, assignments, or teacher links.

## Key acceptance checks

- A user without an active school membership cannot access a school workflow after signing in.
- A student sees their own profile/enrollment and published classwork only.
- A teacher sees classwork only for sections and subjects to which they are assigned.
- A registrar can verify a learner's year-specific enrollment and contextual roll number.
- Deactivated accounts lose access, including existing sessions.
- Login forms use CSRF protection; logout uses a state-changing POST.

Record actual command output and any gaps in `docs/ai-context/08_TEST_RELEASE_STATUS.md` before treating a check as passed.

## Promotion test

The demo includes a next academic year with Grade 8 / B. Sign in as demo-admin, open Casey’s student history, preview a promotion to that year/section with a new roll number, then confirm. The code and UUID stay the same; the prior-year row remains visible with its outcome. Registrar users may preview but cannot confirm. The demo seed does not reset completed enrollment history.
