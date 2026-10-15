# Implementation Plan

Status vocabulary: Not started, In progress, Blocked, Verified, Released.

| Phase | Status | Current boundary |
|---|---|---|
| 0 Discovery/design | Verified | Repository, relationships, roles and IELTS keep-separate audit documented |
| 1 Foundation | In progress | Local schema/auth/scope verified; production provisioning/security verification remains |
| 2 Admissions/identity | In progress | Intake/decisions, individual/batch/conditional progression and immutable history verified; documents/imports/transfer/section-change UI remain |
| 3 Core education | In progress | Guarded attendance/corrections, text work/grading and student workload/history verified; private files and richer reports remain |
| 4 Assessment | In progress | Pilot scoring/moderation/publication/transcripts verified; calendars/scales/weights/exports remain |
| 5 Finance | In progress | Pilot invoice/payment/receipt/reversal verified; installments/refunds/late fees/general ledger remain |
| 6 Oversight | In progress | Pilot timetable/notices/effective settings/scoped summaries verified; fuller calendar/notifications/analytics remain |
| 7 Rollout | Not started | PostgreSQL, SMTP, security/accessibility, restore and hosted acceptance required |

## Unchanged progress scoring

Eight equally weighted pilot delivery milestones each contribute 12.5%. Seven now meet their documented local acceptance gates: foundation, scoped auth, identity/year progression, basic education, assessments/report cards, fees/accounting, and oversight/operations. **7/8 = 87.5%.** The denominator and milestone criteria are unchanged; the broader phases above remain separately tracked.

Milestone 7 acceptance is evidenced by correction review, timetable/notices/settings, role dashboards and batch workflow tests. Milestone 8 remains Not started until actual PostgreSQL/privacy/security/upload/SMTP/restore/accessibility/hosted pilot evidence exists. This score does not certify production readiness.

Maintain additive migrations, atomic services, source-of-truth histories and measured evidence. Update project_state.json/Markdown and regenerate PROJECT_STATUS.html with every checkpoint.

## Production candidate update

Production milestone 8 is now In progress: code/configuration hardening is implemented, but PostgreSQL concurrency/restore CI and actual deployment, SMTP/ClamAV, privacy/accessibility and human acceptance evidence must close before Verified.

## Release validation continuation (2026-10-15)

Parallel Luna owners added combined recovery, runtime preflight, isolated browser acceptance, CI wiring and authentication-throttle retention; an independent reviewer checked safeguards. The production gate remains open. First publish the workflow context correction and harnesses, then inspect actual hosted PostgreSQL/browser/container outcomes. Complete VPS-specific configuration, TLS/SMTP/scanner/persistence/recovery and human acceptance before final closure. The dashboard records gate-specific blockers rather than increasing the score for tooling alone.

## Reprioritized local acceptance

CI/VPS rollout is deferred by user request. Current work is local regression, reproduced defect fixes and the user-computer checklist. LOCAL_TEST_REPORT.md is the consolidated evidence/review index; TESTING_MVP.md is the handoff. Do not request hosting setup during this phase or relabel deferred production gates as passed.

## School scenario testing phase

72-case scenario matrix, connected request/service tests and the individual graduation guard are complete at their documented layers. Actual cloud-browser execution is blocked by local-URL policy; require a permitted accessible test target and do not bypass the restriction. Track automatic invoice generation and missing regular-portal lifecycle/history screens as product gaps, not passed tests.
