# Implementation Plan

Status vocabulary: Not started, In progress, Blocked, Verified, Released.

## Phase 0 — Discovery and design

Status: Verified for the current repository discovery checkpoint. The repo was empty, the requirements/design set was created, and the IELTS repositories were inspected. This does not mean application features are complete.

## Phase 1 — Foundation

Status: In progress. Committed: Django entrypoints/settings, environment and dependency baseline, custom User, SchoolMembership, School/Campus/AcademicYear, SchoolClass/Section/Subject, admin registrations, and baseline tests. Remaining: generate and verify migrations, run check/migrate/tests, add object-level authorization and secure login/password-reset/account-deactivation flows, and reconcile terminology before dependent modules.

Acceptance: clean setup passes check/migrations/tests; custom authentication and scoped permissions deny anonymous, inactive, wrong-role, and cross-school access; model constraints are verified against the database.

## Phase 2 — Admissions and identity

Status: Not started. Applications, registration, guardians, immutable IDs, Enrollment, roll numbers, promotion preview/commit, transfers and re-admission.

## Phase 3 — Core education

Status: Not started. Teacher assignments, attendance, assignments, submissions, feedback, and student to-do workflow.

## Phase 4 — Assessment and examinations

Status: Not started. Keep IELTS separate; implement school assessment rules independently after the audit.

## Phase 5 — Finance

Status: Not started. Decimal-safe fee ledger, invoices, payments, receipts, concessions, reversals, and reports.

## Phase 6 — Oversight/configuration

Status: Not started. Dashboards, notices, timetable, policy settings, optional guardian portal, and MFA decision.

## Phase 7 — Quality/release

Status: Not started. Authorization/security, accessibility, backup/restore, performance, pilot acceptance, deployment gates.

No phase is Verified or Released without actual test evidence.
