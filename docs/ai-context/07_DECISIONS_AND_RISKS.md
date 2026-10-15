# Decisions and Risks

## Current decisions

- Django 5.2 modular monolith with same-origin templates and sessions; no React/API split, queues or caches for this pilot.
- One permanent Student UUID and STU code; year-specific Enrollment stores roll number and preserved placement/history.
- SchoolClass denotes Grade and Section is a year-bound SectionOffering. Campus may be null for a schoolwide offering; Term belongs to AcademicYear.
- No blanket superuser access to private student/learning records. Active school roles and teacher/student relationships determine scope; sensitive student reads and changes are audited.
- IELTS projects remain separate; school scoring will be implemented independently after their feasibility audit.
- Assessment question-bank items are copied into frozen assessment snapshots; raw answers/marks are distinct from finalized score and policy snapshots.
- Result publication is per attempt and does not close the scheduled assessment for other students. After deadline, only already saved answers may be submitted.
- Finance balances are exact Decimal sums of immutable ledger rows; invoice uniqueness and payment/reversal idempotency prevent ordinary duplicate postings. Reversal preserves the original receipt/payment.
- PKR is the synthetic demo currency; fee plans carry configurable three-letter currency codes and currencies are reported separately without conversion.
- Pending admission intake creates no Student until admin approval; the separately authorized walk-in registration path remains available.
- Batch confirmation locks and revalidates all rows; conditional reasons and immutable attributed source/target decision snapshots preserve yearly history.
- Attendance records and session context use guarded services; corrections retain the proposal and admin/system decision rather than silently rewriting history.
- School settings and published notice edits retain revisions; timetable/notices/dashboards enforce active matching school roles and exact teacher assignments.
- Student result visibility affects student views and service reads; authorized teachers/admins retain result access. Teacher notice authoring is limited to assigned sections.

## Remaining limits and release risks

- Local synthetic-data pilot only; no hosted deployment or production readiness is claimed.
- PostgreSQL row-lock/concurrency acceptance, real SMTP, throttling/MFA, private file uploads, backup restoration and hosted human/accessibility acceptance remain unverified.
- Transfer/section-change correction UI, admission documents/imports, formal calendar/notification delivery and richer analytics remain backlog.
- Terminology and branding render on oversight pages. Global theming and branded report-card export are not implemented. Policy controls are allowlisted and cover late work, correction windows, student result visibility and notice expiry.
- Assessment uses versioned fixed A/B/C/D/F bands and configurable pass thresholds; exam calendars, weights and richer scales remain future work.
- Finance is a two-decimal receivable ledger with one invoice per enrollment/plan, partial payments, concessions and reversals; installments, refunds, late fees and a full general ledger remain future work.
- Normal ORM/service guards protect history; privileged raw SQL bypass and PostgreSQL cross-school scheduling/concurrency behavior remain release concerns.

## Policy boundaries

Username login; one enrollment per student/year; section/date attendance sessions; default late text work allowed until grading; immutable permanent identities; admin decisions and confirmation. Correction age defaults to seven school-local calendar days; notice expiry defaults to no automatic expiry; student results are visible by default. These policies have effective consumers and tests, not inert settings controls.

Campus consistency is validated, but staff memberships are school-wide rather than campus-restricted. Notice authoring checks both persisted source and proposed target scope. History protection is application-level and does not replace production database/operator controls. Treat synthetic test evidence as a pilot gate, not authorization to introduce real minors' data before release acceptance.

## Production candidate update

Production hardening has been implemented with targeted local evidence. Outstanding acceptance remains environment-specific: PostgreSQL, full container startup, file-volume/secret ownership, TLS, real SMTP, current ClamAV signatures, restored files/database, monitoring and hosted human privacy/accessibility. Preserve87.5% until all milestone 8 criteria are evidenced.

## Evidence accounting and recovery decisions

Preserve the eight milestone denominator and unchanged production criteria. A validated evidence record is only a schema/accounting check and still requires independent operator review. Recovery bundles include private files and quarantine with the encrypted database dump; restoration is limited to explicitly disposable empty targets and a quiesced application. Do not synthesize disposable attestations inside restore tooling. Authentication-throttle cleanup is bounded and dry-run by default; operator scheduling/monitoring remains a target deployment task.
