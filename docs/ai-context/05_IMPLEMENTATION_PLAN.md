# Implementation Plan

Use: Not started, In progress, Blocked, Verified, Released.

| Phase | Status | Current boundary / acceptance still needed |
|---|---|---|
| 0 Discovery/design | Verified | Empty repo confirmed; requirements/relationships/permissions/workflows/IELTS audit documented |
| 1 Foundation | In progress | Local schema/auth/portals verified; PostgreSQL and fuller provisioning/authorization/privacy release checks remain |
| 2 Admissions/identity | In progress | Registration, individual outcomes and history verified; intake approval, batch/conditional, transfer/section correction UI remain |
| 3 Core education | In progress | Basic assigned attendance/text work/grading verified; correction approvals, student attendance/to-do and files remain |
| 4 Assessment | Not started | Attempt rules/scoring/moderation/report-card and authorization tests required |
| 5 Finance | Not started | Decimal ledger, reconciliation/reversal and scope tests required |
| 6 Oversight | Not started | Notices, timetable, policy editor and scoped analytics required |
| 7 Rollout | Not started | PostgreSQL, SMTP, uploads, security/accessibility, restore and hosted pilot required |

## Defined progress score

Eight **pilot delivery milestones**, each 12.5%, are defined in `project_state.json`. Count only milestones with Verified local acceptance criteria; 4/8 currently verified gives **50%**. This score is a deliberately defined pilot delivery measure, not completion of every requirement or of production readiness. The full phase table above retains unfinished scope.

First four gates: clean foundation/academic schema; session auth and scoped portals; identity/year progression; basic attendance/classwork. Remaining four: assessment/report cards; fees/accounting; complete oversight/operations; production pilot release. Their exact acceptance criteria are rendered into PROJECT_STATUS.html.

Run focused tests on every increment and integrated checks before commits. Keep migrations additive, preserve old rows, and update status source and impacted Markdown in the same commit.
