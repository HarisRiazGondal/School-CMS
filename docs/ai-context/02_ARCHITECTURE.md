# Architecture

Django 5.2 modular monolith with templates, CSRF and database sessions. No extra API/frontend split or worker infrastructure is required by the current pilot. `requirements.txt` bounds Django to the tested 5.2 series.

| App | Current ownership |
|---|---|
| accounts | Custom User, school role grants, active-session enforcement, portal home |
| schools | School, Campus, AcademicYear, synthetic demo management command |
| academics | SchoolClass (Grade), year-bound Section (SectionOffering), Subject, Term |
| students | Student/Guardian/Enrollment, scoped registration/history, preview/confirmation and lifecycle services |
| learning | TeacherAssignment, attendance sessions/records, assignments, submissions and grade/revision history |
| audit | Actor/school-scoped metadata events, limited JSON payloads and ordinary append guards |
| assessment, finance, communications | Planned; no implementation claim |

## Request flow

URL → Django session identity/active-account middleware → view scope/form querysets → service role/assignment checks → validated transaction + database uniqueness → audit metadata → scoped template response. Form CSRF is enforced; no browser JWTs or local-storage credential storage exists.

Password hashes are owned by Django; no raw passwords or secrets are committed. Reset links use Django's time-limited token flow. Production settings reject missing/placeholder secrets and secure cookies; SMTP/proxy/HSTS settings must be configured per hosting. Public login throttling and MFA remain release work.

Student/Enrollment protected writes and placement changes go through services; promotion locks and revalidates rather than trusting a preview. Attendance checks the exact active roster. Work publication/submission/grading and audit writes are atomic. Scoped read-only private Admin views are supplementary maintenance tools, not the regular-user product UI.

Deployment: PostgreSQL, HTTPS, environment-managed configuration, controlled migrations, private uploads, backups and tested restores; see `../OPERATIONS.md`. Only SQLite runtime acceptance is verified so far.
