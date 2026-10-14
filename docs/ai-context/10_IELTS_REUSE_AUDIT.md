# IELTS Reuse Feasibility

Inspected repositories: `HarisRiazGondal/ielts-prep` and `HarisRiazGondal/IELTS-Essay-Writing-checker-` (2026-10-14 discovery). No source was copied into School-CMS.

| Source | Observed implementation | Feasibility |
|---|---|---|
| ielts-prep | Flask/SQLAlchemy/Jinja/Flask-Login; User password_hash and Role; auth forms. Imported routes, templates/static and tests missing from inspected tree. Default admin credentials hardcoded; ephemeral session secret fallback. Writing analysis uses word-count/length heuristics. | Keep separate. Learn from flow concepts; implement Django auth independently. It does not supply a complete reusable quiz engine. |
| IELTS-Essay-Writing-checker- | Flask/CORS evaluate/batch/topics endpoints; heavy generic T5/BERT NLP models and heuristic scoring. Referenced GloVe/fine-tuned assets and frontend not present. API docs and response field names disagree. Tests are manual localhost request scripts. | Keep separate. A future essay feedback adapter could be evaluated behind a stable contract; do not import IELTS band scoring into school grades. |

Extract/adapt: question/review UX ideas and a narrowly defined optional essay-feedback interface after contract and accuracy validation. Rewrite: school question banks, attempts, objective scoring, manual grades and permissions in Django. Remain separate: IELTS datasets, training, IELTS band assumptions and external model infrastructure.

## Proposed assessment boundary

A school assessment owns scheduled questions and attempt policy. `score_attempt(attempt, scoring_policy)` returns authoritative raw item marks plus review flags. An optional essay adapter returns advisory feedback with model/version metadata; it cannot finalize a school mark. Teacher review, finalization, publication and grading-policy versions stay in School-CMS.

## Remaining audit limitations

No IELTS runtime or model-accuracy tests were executed. No validated licensing/extraction approval or reliable scorer calibration is established. This audit supports the keep-separate decision; it is not evidence of scoring quality or completed assessment implementation.
