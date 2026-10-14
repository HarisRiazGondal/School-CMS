# Product Requirements

## Objective

Give a school one coherent operating system for admissions, student records, academics, learning, assessment, examinations, and finance. Daily users receive purpose-built responsive workflows; backend permissions scope every record, search, aggregate, file, and export.

## P0 requirements

1. School, optional campus, academic year, term, grade, section, subject, and teacher assignment.
2. Secure authentication, account deactivation, password reset, role permissions, and school/campus scope.
3. Admissions, guardians, documents, registration, transfers, withdrawals, and re-admission.
4. Permanent student ID generated once on registration; never reused.
5. Separate historical Enrollment records for each academic year, including class, section, roll number, status, dates, and promotion outcome.
6. Previewed and authorized promotion with repeat, conditional, section change, transfer, withdrawal, re-admission, and graduation paths.
7. Project memory files and offline PROJECT_STATUS.html updated from verified state.

## P1 requirements

Attendance and corrections; teacher assignments; assignments/submissions; reusable assessment; exams/report cards; fee ledger and receipts; timetables, notices, dashboards, imports, and optional guardian portal.

## MVP boundary

Foundation/auth/scope, academic setup, admissions and identity, historical enrollment/promotion, minimum teacher/student workflows, and authorization/lifecycle tests. Library, transport, inventory, HR/payroll, broad integrations, SaaS billing, and advanced analytics follow foundation verification.

## Acceptance examples

- A student promoted from Class 1/A/Roll 18 to Class 2/B/Roll 07 keeps one permanent ID and both enrollment records remain queryable.
- Duplicate enrollment in one academic year and duplicate roll number in one section are rejected by policy and database constraints.
- A teacher cannot read or write an unassigned section by changing an object ID.
- A posted payment or finalized mark is corrected with an auditable compensating record.
