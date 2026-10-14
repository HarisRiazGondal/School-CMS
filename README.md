# School-CMS

A configurable school management platform built around a Django modular monolith.

## Current status

The repository was empty at project start. The current checkpoint establishes Phase 0 discovery/design artifacts and a minimal Django foundation. Application modules, migrations, and tests are not yet implemented.

Read [docs/ai-context/00_PROJECT_MEMORY.md](docs/ai-context/00_PROJECT_MEMORY.md) before continuing work. The durable project handoff is maintained under `docs/ai-context/`.

## Direction

- Django with PostgreSQL for deployment.
- School and optional campus boundaries in domain records.
- One immutable student identity with separate academic-year enrollments and contextual roll numbers.
- Backend-enforced permissions and audit trails.
- Django Admin for trusted maintenance and role-specific portals for daily workflows.

## Local setup

1. Create a virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env` and set a development secret.
4. Run `python manage.py check`.

No production deployment or database readiness is claimed yet.
