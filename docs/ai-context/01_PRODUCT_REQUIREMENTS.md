# Product Requirements

Source: user-supplied configurable Django school platform brief (2026-10-14). Full scope includes SIS, learning, admissions, examinations and school finance; this checkpoint is a locally testable subset.

| Requirement | Current evidence | Remaining |
|---|---|---|
| School/campus/year/grade/section/subject/term | Models, constraints, migrations and tests | Custom academic-setup screens and richer curricula/timetables |
| Authentication and scope | Session login/logout/reset; active roles; teacher assignments; student ownership; HTTP denial tests | Throttling, MFA, hosted SMTP and production security verification |
| Permanent student identity | Immutable UUID/STU code; guarded registration and duplicate constraints | Imports/duplicate candidate review and controlled demographic corrections |
| Admission and yearly placement | Registrar registration, guardians and enrollment history | Application intake/approval, documents and validated imports |
| Promotion/history | Individual preview/confirmed admin commit, repeat/graduation, controlled exit/re-admission services | Batch/conditional outcomes, transfer/section-change UI and promotion-rule configuration |
| Attendance | Assigned roster, exact session data and duplicate protection | Correction requests/approval, student summaries and absentee reports |
| Learning | Text work/submission, due dates, revisions, grading feedback | Private file submissions, tasks and actionable overdue/completed dashboards |
| Assessment/exams | IELTS reuse audit and independent interface proposal | Quiz engine, marks/moderation/report cards/transcripts |
| Finance | Design only | Fees, ledger, receipts/reversals/reconciliation |
| Oversight and release | Role portals, memory docs and offline status | Notices/calendar/configuration, PostgreSQL/backup/accessibility/hosted pilot |

## Journeys

1. Registrar signs in → chooses permitted school → validates registration and guardian → generates permanent student identity → creates one year enrollment and contextual roll number.
2. School admin opens student history → previews next-year grade/section/roll → resolves conflicts → explicitly confirms → old placement persists and a new enrollment is created.
3. Assigned teacher opens roster → records complete session → duplicate/replaced sessions are rejected; correction workflow is future work.
4. Teacher publishes text work → student sees only eligible published work → submits/updates response before grading → teacher grades and provides feedback → graded revisions and student ownership are preserved.
5. Accountant invoice/payment/reversal journey is planned and unimplemented.

Optional/later: guardian portal, library, transport, inventory, HR/payroll, broad integrations and SaaS billing. Prioritize remaining identity/scope workflows before optional modules.
