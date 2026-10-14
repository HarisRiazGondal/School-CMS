# Architecture

## Status

Phase 0 design draft; Django foundation scaffold has been committed, but no domain models or migrations exist.

## Shape

Use a modular Django monolith with PostgreSQL in deployment. Keep domain logic in explicit service functions and transaction boundaries. Retain Django Admin for trusted maintenance and build custom role workflows for regular staff, students, and finance users.

## App boundaries

- accounts: custom User, membership, roles, permissions, account status.
- schools: School, Campus, settings.
- academics: AcademicYear, Term, Grade, SectionOffering, Subject, timetable.
- people: Student, Guardian, StaffProfile, TeacherProfile.
- admissions: applications, decisions, documents.
- enrollments: Enrollment, roll assignment, promotion, transfer, withdrawal.
- attendance: sessions, records, corrections.
- learning: teacher assignments, assignments, submissions, feedback.
- assessment: questions, quizzes, exams, marks, report cards.
- finance: fee plans, invoices, payments, receipts, ledger, adjustments.
- communications: notices and notifications.
- audit: append-oriented sensitive-action events.

Authorization is action + resource + school/campus/academic scope + workflow state. Views and APIs must scope querysets; services repeat critical checks. Superuser status does not imply unlogged access to private student or finance records.

## Transaction services

register_student, preview_promotion, commit_promotion, record_attendance, correct_attendance, finalize_assessment, post_payment, and reverse_payment use atomic transactions and preserve history.

## Deployment

Environment-managed secrets, HTTPS, PostgreSQL, private media storage, controlled migrations, structured logs, and tested backup/restore. Avoid Redis/Celery until a measured need exists.
