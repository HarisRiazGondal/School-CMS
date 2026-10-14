# School-CMS working instructions

Read `docs/ai-context/00_PROJECT_MEMORY.md`, `09_NEXT_ACTIONS.md`, and impacted design documents before every task. Inspect actual code and reconcile documentation drift before making changes.

Keep increments reviewable. Preserve permanent student identities, academic-year enrollment history, backend school/role scope, audit attribution and transactional writes. Never silently overwrite finalized records. Keep secrets and real pupil data outside the repository.

Run appropriate automated tests, migration-drift checks and clean migrations. Record actual results and limitations. Check status scoring against the named acceptance criteria; percentages refer to the documented pilot milestones, not production readiness.

`docs/ai-context/project_state.json` is the dashboard source. After updating it, run `python scripts/render_status.py`. Update affected Markdown documents, test/release status, next actions and the progress log in the same commit as the code.

**MANDATORY CONTINUITY CHECKPOINT: Before ending this task, update all affected `docs/ai-context/*.md` memory files and regenerate `docs/ai-context/PROJECT_STATUS.html` with the verified current phase, changes, decisions, test results, blockers, and exact next actions, so a new agent can resume without any prior chat history.**
