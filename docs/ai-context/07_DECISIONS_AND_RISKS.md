# Decisions and Risks

## Decisions

- D-001: Start with one school and explicit optional campus boundaries; defer SaaS billing.
- D-002: Immutable internal student identity; separate human-facing admission code.
- D-003: Academic-year Enrollment owns class, section, roll number, status, dates, and outcome.
- D-004: Promotion previews conflicts, then commits atomically and preserves source history.
- D-005: Django modular monolith/PostgreSQL; server-rendered workflows first.
- D-006: IELTS projects remain separate; reuse requires evidence and a clean adapter boundary.

## Risks

- Empty repository means all architectural choices are provisional until foundation runs.
- IELTS projects contain hardcoded credentials/incomplete routes, missing model assets, stale API docs, and heuristic scoring; copying them would introduce security and correctness risks.
- Student/finance scope leakage, duplicate enrollments, partial promotions, and silent financial edits require authorization tests, constraints, transactions, and audit events.
- Adding React, queues, or caches early may increase operational cost without evidence.

## Open policy choices

Student code format, one-vs-multiple enrollments per academic year, campus rules, grading scales, attendance correction authority, currency, fee reversals, and promotion criteria.
