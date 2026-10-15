# Product Requirements

Source: user-supplied configurable Django school platform brief (2026-10-14). Full scope includes SIS, learning, admissions, examinations and school finance; this checkpoint is a locally testable subset.

| Requirement | Current evidence | Remaining |
|---|---|---|
| School/campus/year/grade/section/subject/term | Models, constraints, migrations and tests | Custom academic-setup screens and richer curricula and academic-setup UX |
| Authentication and scope | Session login/logout/reset; active roles; teacher assignments; student ownership; HTTP denial tests | Throttling, MFA, hosted SMTP and production security verification |
| Permanent student identity | Immutable UUID/STU code; guarded registration and duplicate constraints | Imports/duplicate candidate review and controlled demographic corrections |
| Admission and yearly placement | Pending intake, admin approval/rejection, walk-in registration, guardians and enrollment history | Documents and validated imports |
| Promotion/history | Individual/batch preview and admin commit, conditional reasons, repeat/graduation, preserved decisions, exit/re-admission | Transfer/section-change UI and promotion-rule configuration |
| Attendance | Assigned roster, service-only writes, attributed correction approval and student history | Rich absentee reports/notifications |
| Learning | Text work/submission, workload status, due dates, revisions, policy-controlled grades/feedback | Private file submissions and richer task planning |
| Assessment/exams | Bank/scheduled attempts, objective/manual marks, finalization/publication, historical report cards/transcripts tested | Exam calendars, weights, richer scale configuration and branded exports |
| Finance | Fee plans, invoices/concessions, exact partial/full payments, receipts/reversals, statements and currency-separated balances tested | Refunds, installment schedules, late fees, expenses and approvals |
| Oversight and release | Scoped summaries, timetable, notices, revisioned settings, memory and offline status | Full calendar/report exports, PostgreSQL/backup/accessibility/hosted pilot |

## Journeys

1. Registrar signs in → chooses permitted school → validates registration and guardian → generates permanent student identity → creates one year enrollment and contextual roll number.
2. School admin opens student history → previews next-year grade/section/roll → resolves conflicts → explicitly confirms → old placement persists and a new enrollment is created.
3. Assigned teacher opens roster → records complete session → duplicate/replaced sessions are rejected → teacher proposes reasoned correction → admin approves/rejects → original and decision evidence remain.
4. Teacher publishes text work → student sees only eligible published work → submits/updates response before grading → teacher grades and provides feedback → graded revisions and student ownership are preserved.
5. Accountant signs in → creates a school/year fee plan → issues an enrollment invoice with optional concession → posts partial/full payment with an idempotency key → opens receipt → reverses with confirmation/reason if required → balance reconciles from append-only ledger. Student sees only own historical statement/receipts.

Optional/later: guardian portal, library, transport, inventory, HR/payroll, broad integrations and SaaS billing. Prioritize remaining identity/scope workflows before optional modules.

6. Registrar records a pending application without issuing an identity → school admin reviews and approves/rejects → approval registers identity/enrollment/guardian atomically. The walk-in registration workflow remains available separately.
7. Admin previews a batch of promoted/repeated/conditional/graduated outcomes → resolves row conflicts and supplies conditional reasons → confirms the revalidated batch → all outcomes and immutable snapshots commit together or none do.
8. Admin changes bounded school policies or publishes a notice/timetable → relevant school-role portals apply the policy and scope → settings and published-notice edits preserve revisions.
