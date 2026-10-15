# School scenario edge-check results

## Scope and evidence boundary

These results cover focused existing Django regression tests for selected negative and lifecycle edges in [`SCHOOL_SCENARIO_MATRIX.md`](SCHOOL_SCENARIO_MATRIX.md). They are service/form/test-client checks, **not cloud-browser evidence**. The cloud-browser policy explicitly blocks access to this local application URL and prohibits trying a workaround, proxy, or alternate browser. Therefore no browser, accessibility-tree, screenshot, or visual UI result is claimed. This is a policy block, not a missing-binary diagnosis. Matrix rows outside the mappings below remain unverified.

## Executed commands

On checkout `e1975c6209bcbf4b31c24e36acc8e68cbb5d97a9`, using the local SQLite development database:

```sh
DJANGO_DEBUG=true python manage.py test \
  tests.test_students_operations tests.test_students tests.test_oversight_core \
  tests.test_assessment tests.test_assessment_http tests.test_finance \
  tests.test_finance_http tests.test_auth tests.test_review_regressions --verbosity 1
```

**Result:** 78 tests passed, no failures; Django system check clean.

```sh
DJANGO_DEBUG=true python manage.py test tests.test_postgres_concurrency --verbosity 1
```

**Result:** 8 tests skipped, no failures; Django system check clean. The module explicitly skips unless the database vendor is PostgreSQL. These skips include concurrent payment/reversal idempotency, invoice issuance, admission approval, batch promotion, cross-school timetable booking, assessment attempt limits, attendance correction requests, and correction lock ordering. They are not passes.

The graduation-with-target regression described below was added after the 78-test run and was not part of that result. The parent applied the service guard and ran `tests.test_students tests.test_students_operations`: 26 tests passed, including the new preview/commit no-write regression. The final integrated result is recorded in SCHOOL_SCENARIO_RESULTS.md.

## Matrix coverage mapping

| Matrix IDs | Existing focused regression(s) exercised | Result and limit |
| --- | --- | --- |
| ADM-01–05 | `test_pending_admission_intake_creates_no_student_until_admin_approval`; `test_admission_rejection_is_idempotent_and_final_decision_is_immutable`; `test_only_school_admin_decides_and_approval_registration_rolls_back`; `test_application_scope_and_intake_ui_are_scoped_and_pending` (`tests.test_students_operations`) | Covered by local service/form tests; not an end-to-end browser run. |
| ID-01–04 | `test_registration_creates_stable_school_scoped_code_and_year_context`; `test_registration_rejects_mismatched_year_and_other_school`; `test_re_admission_reuses_identity_only_after_active_enrollment_is_closed` (`tests.test_students`) | Covered by local lifecycle tests. |
| SCH-02–05 | `test_timetable_rejects_teacher_section_and_room_overlaps_and_allows_nonconflicting_slots`; `test_timetable_requires_live_assignment_membership_and_school_admin_creation` (`tests.test_oversight_core`); `test_timetable_queryset_mutation_cannot_bypass_overlap_validation` (`tests.test_review_regressions`) | Teacher/section/room conflicts and guarded mutation covered locally. PostgreSQL cross-school simultaneous-booking test is skipped. |
| SCH-09, PRO-11 | `test_student_timetable_hides_slot_after_teacher_membership_is_deactivated`; `test_cached_school_membership_does_not_survive_database_deactivation` (`tests.test_review_regressions`); `test_inactive_membership_is_denied`; `test_inactive_user_and_school_are_denied`; `test_stale_user_object_does_not_bypass_database_deactivation` (`tests.test_auth`) | Local checks cover database deactivation and scoped timetable. A reused cloud-browser session was not tested. |
| ASM-07, ASM-15 | `test_scope_attempt_limit_and_schedule_deadline_enforced`; `test_student_must_wait_for_open_time` (`tests.test_assessment`); `test_late_submit_preserves_last_saved_answers_and_ignores_late_body` (`tests.test_assessment_http`) | Schedule, attempt limit, and late-submit behavior covered locally. Concurrent starts are among the skipped PostgreSQL tests. |
| ASM-09, ASM-10–12, ASM-14 | `test_authoring_choices_are_scoped_and_other_school_roles_are_denied`; `test_mcq_and_manual_mark_admin_publish_and_historical_report`; `test_finalize_conflict_is_visible_until_all_manual_answers_are_marked` (`tests.test_assessment_http`); `test_final_result_survives_student_promotion_and_is_grouped_in_historical_year` (`tests.test_assessment`) | Service and Django test-client workflows cover role scope, grading/finalization/publication, and historical result persistence. No visual/browser evidence. |
| FIN-08–12 | `test_payment_and_reversal_are_idempotent_and_reversal_restores_balance`; `test_reused_payment_key_with_different_parameters_is_rejected`; `test_rejects_invalid_amount_currency_overpayment_and_concession`; `test_role_school_and_student_scope_are_enforced` (`tests.test_finance`); `test_fee_plan_invoice_partial_full_payment_receipt_reversal_and_reconciliation`; `test_student_cannot_select_someone_else_or_post_financial_changes`; `test_teacher_and_cross_school_staff_cannot_read_or_mutate_finance` (`tests.test_finance_http`) | Single-process idempotency, reversal, malformed inputs and role scope covered locally. Simultaneous retry/reversal is skipped on SQLite. |
| PRO-01–05, PRO-07–09 | `test_batch_promotion_preview_and_commit_support_all_year_outcomes_and_retry`; `test_batch_rejects_malformed_duplicate_roll_and_conflict_without_mutation`; `test_batch_requires_conditional_reason_and_graduation_has_no_target`; `test_individual_conditional_preview_requires_and_displays_reason`; `test_batch_transaction_rolls_back_prior_rows_if_later_insert_fails` (`tests.test_students_operations`); `test_preview_is_read_only_and_commit_preserves_identity_and_history`; `test_duplicate_target_year_and_wrong_target_school_rejected_without_writes`; `test_registrar_can_preview_but_only_admin_can_confirm` (`tests.test_students`) | Preview, batch rollback, repeat/conditional/graduation outcomes and admin-only confirmation covered by local regressions. Simultaneous promotion remains PostgreSQL-only and skipped. |
| PRO-06 | `test_graduation_keeps_existing_enrollment_and_creates_no_new_row`; `test_batch_requires_conditional_reason_and_graduation_has_no_target`; parent-added `test_graduation_rejects_target_placement_in_preview_and_commit_without_writes` | No-target graduation is covered. A direct individual-service gap was reproduced during review: `preview_promotion()` / `commit_promotion()` accepted target fields for graduation and ignored them, although form and batch paths reject them. The parent has now added a service guard in preview (also used by commit), so the known defect is **fixed and verified by the 26-test post-fix student run**. The regression was added after the 78-test run, so that run does not establish the fix. |

## Remaining evidence gaps

- No scenario in this document has been executed in the cloud browser. Policy explicitly blocks the local URL and disallows another browser, proxy, or workaround.
- Eight PostgreSQL-only concurrency tests were skipped on SQLite. Their absence does not demonstrate lock correctness or production concurrency behavior.
- This focused set does not execute every row in the 72-scenario matrix, fixture creation in the browser, or a complete five-role journey.
- `PRO-06` is fixed and its new regression passed in the post-fix 26-test student suite. The older 78-test run remains separate historical evidence.
- No live mail, scanner, MFA-key, off-host recovery, or production-host behavior was exercised.
