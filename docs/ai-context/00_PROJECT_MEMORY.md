# Project Memory

## Current checkpoint

School-CMS is an expanded local Django pilot with session authentication, scoped portals, academic foundation, permanent student identities/enrollment/promotion history, attendance, assignments/grading, assessments/transcripts, fees/receipts/reversals and audit events.

**75%: six of eight equally weighted pilot milestones meet documented local acceptance criteria.** This is the same denominator used at the 50% checkpoint. Full phase scope and production readiness remain incomplete.

Latest verification: **79 automated tests pass**; Django checks, migration-drift and migration application pass. A fresh SQLite database passed the combined assessment scoring/publication, payment/receipt/reversal, promotion/history and idempotent demo-reseed workflow. PostgreSQL and hosted production acceptance are unverified.

Current increments: Phase 4/5 pilot slices locally verified; broader Phases 1–6 retain unfinished scope. Milestones 7 (oversight/operations) and 8 (production release) remain Not started.

## Architecture and invariants

Django 5.2 modular monolith, server-rendered portals and database sessions; PostgreSQL intended for deployment, SQLite verified locally. Username login remains. Roles are active school memberships; teachers additionally require subject/section assignments; students require their linked identity and enrollment. Permission queries verify actual database user/school activation, including when callers hold cached objects.

Student UUID/STU code is permanent. Enrollment owns year, section and roll. Promotion creates a new year record and preserves prior placement. Re-admission requires prior active enrollment closure. Historical transcripts and fee statements remain accessible after promotion.

New apps: `assessment` owns school-subject question banks, frozen assessment copies, schedules/attempts/answers, objective/manual scoring, admin finalization/publication and historical transcripts. `finance` owns plans, historical-enrollment invoices, immutable Decimal receivable ledger, idempotent payments/receipts and reasoned reversals. No IELTS engine was copied.

Private access is scoped; financial reads and report-card reads are audited. Django superuser status alone grants no private school records. Normal model/queryset/service writes protect histories; privileged raw SQL remains outside those guards.

## Resume

Read this file, `09_NEXT_ACTIONS.md`, `project_state.json` and impacted design files; inspect code and trust verified behavior. Update Markdown and JSON, run `python scripts/render_status.py`, and commit checkpoints with code. No uncommitted work is intended after this checkpoint.

See `../TESTING_MVP.md` for five demo roles and browser workflows. Real SMTP/PostgreSQL/backup/hosted release remain gates; do not introduce real pupils' data based on local acceptance alone.
