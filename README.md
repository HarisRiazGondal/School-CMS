# School-CMS

A configurable school management platform built around a Django modular monolith.

## Current status

The repository started empty. Phase 0 design artifacts and a Phase 1 foundation are now committed. The foundation includes Django entrypoints/settings, a custom user and school membership schema, School/Campus/AcademicYear, SchoolClass/Section/Subject models, admin registrations, and baseline tests. Migrations and runtime verification are still pending.

Read [docs/ai-context/00_PROJECT_MEMORY.md](docs/ai-context/00_PROJECT_MEMORY.md) before continuing work. The durable project handoff is maintained under docs/ai-context/.

## Direction

- Django with PostgreSQL for deployment.
- School and optional campus boundaries in domain records.
- One immutable student identity with separate academic-year enrollments and contextual roll numbers.
- Backend-enforced permissions and audit trails.
- Django Admin for trusted maintenance and role-specific portals for daily workflows.

## Local setup

1. Create a virtual environment.
2. Install requirements.txt.
3. Copy .env.example to .env and set a development secret.
4. Run python manage.py check, generate migrations, migrate, and run tests.

No production deployment, migration, or database readiness is claimed until those commands have been run and recorded.
