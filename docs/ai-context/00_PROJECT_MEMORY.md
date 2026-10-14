# Project Memory

## Rehydration summary

School-CMS is a configurable school operating platform for one school initially, with explicit school and optional campus boundaries. The core lifecycle is admissions, one permanent student identity, historical academic-year enrollments, contextual roll numbers, promotion, role-scoped teaching/attendance/learning, assessments, and auditable fees.

## Verified state

- Repository: HarisRiazGondal/School-CMS.
- Initial state: empty Git repository; no prior source, branches, migrations, tests, or deployment configuration.
- Current phase: Phase 0 — Discovery and design, in progress.
- Smallest Phase 1 slice started: Django project settings/entrypoints and environment baseline committed.
- No local Django command or test has been run in this environment; test evidence is unavailable.
- IELTS audit completed against ielts-prep and IELTS-Essay-Writing-checker-. They remain separate; no code was reused.

## Invariants

- Student has one immutable internal identity for the full lifecycle.
- Roll number belongs to a year-specific enrollment/section context and may change.
- Promotion creates a new enrollment and preserves every earlier enrollment and outcome.
- Attendance, marks, and posted financial entries require controlled corrections or reversals.
- Authorization is enforced in backend services and querysets, scoped to school/campus/class/section/subject.

## Proposed stack

Django modular monolith, PostgreSQL for deployment, Django Admin for trusted maintenance, and role-specific portals. Start with server-rendered Django workflows; introduce an API or React frontend only when a verified requirement justifies it.

## Resume instructions

Read this file, 09_NEXT_ACTIONS.md, and impacted design files before changing code. Verify repository behavior over assumptions. Update the memory files and PROJECT_STATUS.html after every implementation increment.
