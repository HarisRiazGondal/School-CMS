# School-CMS

A Django modular monolith for school administration, learning, assessment and fee workflows. The local pilot includes account access, school setup, admissions, permanent student identity and enrollment history, scoped classwork and attendance corrections, timetables, notices and school settings, objective/manual assessments, and immutable finance ledger records.

## Local development

Use Python 3.11 or newer and Django 5.2. From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py check
python manage.py test
```

The example environment is for local development only. For an isolated browser demo, create synthetic records with a password you choose:

```sh
python manage.py seed_demo --password 'choose-a-local-demo-password'
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The demo command is idempotent and restricted to `DEBUG=True`. It sets the known synthetic accounts to the operator-supplied password each time it runs. It creates a pending admission application, a one-day-old attendance mark with a pending correction request, school settings (only if absent), a timetable slot, and a published notice, alongside an open assessment and an unpaid invoice. It does not approve admissions, create assessment attempts, or collect payments. Reruns preserve operator changes and reviewed histories, including settings, notices, admission decisions, attendance corrections, attempts, invoices, payments, receipts, and ledger entries. Do not use demo records or credentials in a production database.

For the school lifecycle matrix, connected acceptance and UI gaps, see [docs/SCHOOL_SCENARIO_RESULTS.md](docs/SCHOOL_SCENARIO_RESULTS.md). For the earlier local results, fixes and review index, see [docs/LOCAL_TEST_REPORT.md](docs/LOCAL_TEST_REPORT.md). For test coverage and role-by-role acceptance steps, see [docs/TESTING_MVP.md](docs/TESTING_MVP.md). For deployment and runtime operations guidance, see [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Project direction

The data model preserves one permanent student identity across year-specific enrollment records. Role and school scope are enforced in application workflows. PostgreSQL is the deployment target; local SQLite is provided for development and testing. Review [docs/ai-context/00_PROJECT_MEMORY.md](docs/ai-context/00_PROJECT_MEMORY.md) for design invariants and current status.

## Production release candidate

See [production acceptance](docs/PRODUCTION_READINESS.md), [independent review](docs/PRODUCTION_REVIEW.md), [operations](docs/OPERATIONS.md) and [environment template](deploy/production.env.example). Production boot requires PostgreSQL, explicit HTTPS configuration, separate Django/MFA keys, persistent private scanned storage and SMTP. Run the release workflow and target-host acceptance before real pupil data. The final local suite runs227 tests:218 passed and9 PostgreSQL-only skips (8 concurrency + 1 live preflight). See [release evidence](docs/ai-context/08_TEST_RELEASE_STATUS.md) and [gate dashboard](docs/ai-context/PROJECT_STATUS.html).
