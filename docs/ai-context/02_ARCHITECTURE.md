# Architecture

## Status

Phase 1 foundation is in progress. The repository now contains a Django entrypoint, custom User and SchoolMembership schema, School/Campus/AcademicYear, SchoolClass/Section/Subject, admin registrations, and baseline tests. No migrations or runtime verification exist yet.

## Shape

Use a modular Django monolith with PostgreSQL in deployment. Keep domain logic in explicit service functions and transaction boundaries. Retain Django Admin for trusted maintenance and build custom role workflows for regular staff, students, and finance users.

## Current app boundaries

- accounts: custom User, membership, roles, permissions, account status.
- schools: School, Campus, academic-year settings.
- academics: SchoolClass, year-bound Section, Subject; reconcile terminology with the planned Grade/SectionOffering model before dependent modules.
- people: Student, Guardian, StaffProfile, TeacherProfile.
- admissions: applications, decisions, documents.
- enrollments: Enrollment, roll assignment, promotion, transfer, withdrawal.
- attendance: sessions, records, corrections.
- learning: teacher assignments, assignments, submissions, feedback.
- assessment: questions, quizzes, exams, marks, report cards.
- finance: fee plans, invoices, payments, receipts, ledger, adjustments.
- communications: notices and notifications.
- audit: append-oriented sensitive-action events.

Authorization is action + resource + school/campus/academic scope + workflow state. Views and APIs must scope querysets; services repeat critical checks. The current helper proves active role membership only; it is not yet a complete object-level authorization layer. Superuser status does not imply unlogged access to private student or finance records.

## Transaction services

register_student, preview_promotion, commit_promotion, record_attendance, correct_attendance, finalize_assessment, post_payment, and reverse_payment use atomic transactions and preserve history.

## Deployment

Environment-managed secrets, HTTPS, PostgreSQL, private media storage, controlled migrations, structured logs, and tested backup/restore. Avoid Redis/Celery until a measured need exists.
