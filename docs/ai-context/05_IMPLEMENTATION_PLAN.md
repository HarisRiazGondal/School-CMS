# Implementation Plan

Status vocabulary: Not started, In progress, Blocked, Verified, Released.

## Phase 0 — Discovery and design

Status: In progress. Repository inspection found an empty repo. Requirements, architecture, data model, permissions, IELTS reuse audit, risks, and memory artifacts are being committed. Acceptance requires agreement on permanent identity/enrollment history, scoped permissions, and truthful status.

## Phase 1 — Foundation

Status: In progress. Django entrypoints, settings, environment example, dependency baseline, and admin URL are committed. Next: custom User, School/Campus, AcademicYear/Term, Grade, SectionOffering, Subject, memberships, migrations, admin registration, and authorization tests.

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
