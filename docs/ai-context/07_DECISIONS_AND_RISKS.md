# Decisions and Risks

## Current decisions

- Django 5.2 modular monolith with same-origin templates and sessions; no React/API split, queues or caches for this pilot.
- One permanent Student UUID and STU code; year-specific Enrollment stores roll number and preserved placement/history.
- SchoolClass denotes Grade and Section is a year-bound SectionOffering. Campus may be null for a schoolwide offering; Term belongs to AcademicYear.
- No blanket superuser access to private student/learning records. Active school roles and teacher/student relationships determine scope; sensitive student reads and changes are audited.
- IELTS projects remain separate; school scoring will be implemented independently after their feasibility audit.

## Current limitations and release risks

- The pilot runs locally with synthetic data. No hosted deployment or production readiness is claimed.
- PostgreSQL, real SMTP delivery, rate limiting/MFA, private file uploads and backup restoration are not verified.
- Application/approval intake, conditional and batch promotions, transfer and section-correction browser flows remain incomplete.
- Attendance correction approvals, quizzes, examinations, report cards and finance are not implemented.
- History and audit guards cover normal model/service/queryset paths; privileged raw SQL can bypass application guards. Production database controls and concurrency tests remain release work.

## Nonblocking policy defaults

Username login, one enrollment per student/year, one section/date attendance session, text submissions may be late but are locked after grading, friendly IDs generated as STU sequence per school, campus-null schoolwide sections, admin confirmation for individual promotion. Re-admission requires prior active placement to be closed. Batch/conditional promotion and configurable scoring/fee policies are not silently inferred.

## Operational limits

Student/audit identity protections are application guards, not guarantees against privileged raw SQL. PostgreSQL locking/uniqueness race behavior needs database-specific verification. Public login throttling, production SMTP/proxy settings, retention policies and tested restore must be completed before real minors' data is introduced.
