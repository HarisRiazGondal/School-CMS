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
| assessment | Reusable question bank snapshots, scheduled attempts, answers, raw scoring and finalized/published policy snapshots with historical transcripts |
| finance | Fee plans, immutable invoices/payment/receipt/ledger records and compensating reversals |
| oversight | Revisioned school settings and policies, scoped notices/timetable and role-bounded operations summaries |

## Request flow

URL → Django session identity/active-account middleware → view scope/form querysets → service role/assignment checks → validated transaction + database uniqueness → audit metadata → scoped template response. Form CSRF is enforced; no browser JWTs or local-storage credential storage exists.

Password hashes are owned by Django; no raw passwords or secrets are committed. Reset links use Django's time-limited token flow. Production settings reject missing/placeholder secrets and secure cookies; SMTP/proxy/HSTS settings must be configured per hosting. Public login throttling and MFA remain release work.

Student/Enrollment protected writes and placement changes go through services; promotion locks and revalidates rather than trusting a preview. Attendance checks the exact active roster. Work publication/submission/grading and audit writes are atomic. Scoped read-only private Admin views are supplementary maintenance tools, not the regular-user product UI.

Deployment: PostgreSQL, HTTPS, environment-managed configuration, controlled migrations, private uploads, backups and tested restores; see `../OPERATIONS.md`. Only SQLite runtime acceptance is verified so far.

## Assessment and finance request boundaries

Assessment views scope authoring choices and student enrollment before forms render. Teacher assignment controls marking; school admins alone finalize and publish complete attempts. Published results are frozen. Bank questions are copied into assessment-specific snapshots so later bank authoring does not change earlier exams. Deadline submissions use already saved work; incoming late answers are ignored. Admin report-card selectors validate scope and UUID input; student selectors always resolve their own profile.

Finance views and services require accountant/admin membership to write; students may read only their own historical invoices/receipts. Atomic posting, invoice/plan uniqueness and per-school idempotency keys enforce ordinary duplicate protection. Balances are calculated from signed immutable ledger entries using exact Decimal row sums, including SQLite verification. Currency groups are never mixed. The ledger is a receivables subledger, not a complete general ledger.

## Oversight operations boundary

Admission intake creates a pending application, with permanent Student/Enrollment creation only on an authorized atomic approval. The separate legacy walk-in registration path remains explicit. Batch previews do not write; admin confirmation locks and revalidates the batch and creates attributed immutable decision snapshots. Conditional progression retains its reason and source/target history.

Attendance creation is service-controlled. Corrections capture old/new values and a reason, then require school-admin review; the original record changes only on approval, with the proposal and audit attribution retained. Expired pending proposals are closed with system attribution. Student attendance history spans old enrollments.

SchoolSetting revisions retain terminology, contact details, IANA timezone, bounded report branding and allowlisted policies. Effective policies govern late classwork, correction age, student result visibility and default notice expiry. Notice form times use the selected school's zone; timetable wall-clock times are labelled with that zone. Terminology/branding affect oversight pages; they do not promise a global theme or report export. Timetable overlap checks serialize through school rows; PostgreSQL concurrency acceptance remains open.

Teacher dashboards use matching active school membership and exact section/subject assignment pairs. Students receive only their own records and published results permitted by policy; accountants receive financial summaries. Private oversight Admin registrations are scoped and read-only. Application-level queryset guards prevent normal history rewrites; privileged SQL remains outside the boundary.

## Production candidate update

Production candidate: sole DB-throttled ModelBackend, required or opted-in TOTP login with encrypted MFA secrets and one-use recovery, five-minute password-bound pending sessions, role-independent MFA middleware (including Admin). Strict configuration requires PostgreSQL, explicit HTTPS hosts/origins, separate secret keys, persistent private storage/scanner and SMTP. WhiteNoise serves immutable static files; private data uses cache/security headers and scoped streamed file downloads. Readiness checks DB and migrations, liveness is process-only. Compose/Gunicorn/Caddy and recovery scripts remain subject to runtime acceptance.
