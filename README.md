# School-CMS

A Django modular monolith for school administration, learning, assessment and fee workflows. The local pilot includes account access, school setup, permanent student identity and enrollment history, scoped classwork and attendance, objective/manual assessments, and immutable finance ledger records.

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

Open <http://127.0.0.1:8000/>. The demo command is idempotent and restricted to `DEBUG=True`. It sets the known synthetic accounts to the operator-supplied password each time it runs. It creates an open assessment and an unpaid invoice without creating an attempt or collecting a payment. Later reruns preserve assessment attempts, invoices, payments, receipts, and ledger history. Do not use demo records or credentials in a production database.

For test coverage and role-by-role acceptance steps, see [docs/TESTING_MVP.md](docs/TESTING_MVP.md). For deployment and runtime operations guidance, see [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Project direction

The data model preserves one permanent student identity across year-specific enrollment records. Role and school scope are enforced in application workflows. PostgreSQL is the deployment target; local SQLite is provided for development and testing. Review [docs/ai-context/00_PROJECT_MEMORY.md](docs/ai-context/00_PROJECT_MEMORY.md) for design invariants and current status.
