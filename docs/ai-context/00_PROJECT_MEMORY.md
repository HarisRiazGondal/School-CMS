# Project Memory

## Current checkpoint

School-CMS began empty. It is now a local, testable Django pilot with authentication, scoped portals, academic foundation, student identity/enrollment/promotion, attendance, text assignments/submissions/grading and audit events. No assessment, finance or production release is complete.

Current work: Phase 2/3 increments **In progress**. **50% of eight equally weighted pilot implementation milestones** meet the local acceptance criteria in `project_state.json`; this measures those slices and does not certify completion of the full product brief. Phase 2/3 still have broader requirements outstanding.

Verified: **48 automated tests pass**, Django system/migration-drift checks pass, fresh SQLite migrations apply and synthetic demo seeding is idempotent. PostgreSQL and hosted production acceptance are unverified.

## Architecture and invariants

Django 5.2 modular monolith; server-rendered portals and sessions; PostgreSQL intended for deployment, SQLite verified locally. User login remains username-based. `SchoolMembership` may grant multiple school-scoped roles. No teacher access from role alone: an active subject/section assignment is required. Student access uses their linked user and active membership/enrollment.

`Student` has one immutable UUID and school-scoped generated `STU-` code. `Enrollment` holds year, section and roll number. Promotion creates a new year record and closes the old one atomically; preview never writes. Re-admission requires the prior active enrollment to be closed. Corrections to immutable placement are not exposed as silent edits.

`SchoolClass` is the current Grade model; `Section` is a year-bound SectionOffering with optional Campus; Term is separate. Avoid renaming persisted models without explicit migrations.

History/audit guards cover normal application writes, including protected queryset mutations; raw database access remains an operational privilege. Student and learning Admin interfaces are scoped/read-only; no blanket private-record access from superuser status.

## Resume

Read this file, `09_NEXT_ACTIONS.md`, `project_state.json` and impacted docs before changes. Trust tested code when docs disagree. Run tests and record real results, then regenerate HTML with `python scripts/render_status.py`. The status source and Markdown must be updated together. No uncommitted work is intended after the checkpoint commit.

IELTS projects were inspected and kept separate; see `10_IELTS_REUSE_AUDIT.md`.
