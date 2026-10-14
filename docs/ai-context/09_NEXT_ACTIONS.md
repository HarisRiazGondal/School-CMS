# Next Actions

Current: local pilot, 48 passing tests, 4/8 pilot milestones verified (50%); Phase 2/3 broader scope In progress.

1. Complete admissions application/decision workflow and batch/conditional promotion previews with conflict and rollback tests.
2. Add attendance correction approvals, student attendance history and overdue/completed learning dashboards.
3. Implement independent question-bank/attempt/scoring/exam/report-card module; use the recorded IELTS keep-separate boundary.
4. Implement Decimal-safe fee plans, invoices, payment/receipt/reversal ledger and accountant authorization tests.
5. Validate PostgreSQL, SMTP delivery, throttling/MFA, private uploads, backup restoration and hosted pilot acceptance before release.

Before implementation: read impacted memory files, inspect models/services and use existing registrations/promotions instead of bypassing guarded writes. After work: run focused/integrated checks, update project_state.json and affected Markdown, run `python scripts/render_status.py` and commit a reviewable checkpoint. Do not reuse IELTS scoring without a new evidence-based adapter review.
