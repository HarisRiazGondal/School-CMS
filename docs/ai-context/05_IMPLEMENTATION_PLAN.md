# Implementation Plan

Status vocabulary: Not started, In progress, Blocked, Verified, Released.

| Phase | Status | Current boundary |
|---|---|---|
| 0 Discovery/design | Verified | Repository, relationships, roles/workflows and IELTS keep-separate audit documented |
| 1 Foundation | In progress | Local schema/auth/scope verified; production database/provisioning/security verification remains |
| 2 Admissions/identity | In progress | Registration/individual progression/history verified; intake/approval, batch/conditional and correction UI remain |
| 3 Core education | In progress | Attendance/text work/grading verified; correction approvals, files and fuller student dashboards remain |
| 4 Assessment | In progress | Pilot bank/attempt/scoring/moderation/publication/transcript gate verified; exam calendars, richer scales/weights/exports remain |
| 5 Finance | In progress | Pilot plan/invoice/payment/receipt/reversal/statement gate verified; installments/refunds/late fees/approvals/general ledger remain |
| 6 Oversight | Not started | Timetable/notices/settings and complete scoped operations required |
| 7 Rollout | Not started | PostgreSQL, SMTP, security/accessibility, restore and hosted acceptance required |

## Unchanged progress scoring

Eight equally weighted pilot delivery milestones each contribute 12.5%. Six now meet their documented local acceptance gates: foundation, scoped auth, identity/year progression, basic education, assessments/report cards, and fees/accounting. **6/8 = 75%.** The same criteria/denominator were defined before the work; full phase scope is tracked separately above. This score does not certify production readiness.

Milestone 7 requires correction approvals, timetable/notices/settings, scoped dashboards and batch workflows. Milestone 8 requires actual PostgreSQL/security/upload/SMTP/restore/accessibility/hosted pilot evidence. Do not mark them complete because of code presence.

Maintain additive migrations, atomic services, source-of-truth histories and measured test evidence. Update project_state.json/Markdown and run scripts/render_status.py after each increment.
