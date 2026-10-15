# Realistic school scenario matrix

## Purpose and evidence rules

This matrix is the run sheet for a synthetic end-to-end school day and two-year student lifecycle. It is grounded in the current Django routes, forms, services and model guards. It is the scenario plan with a separate browser-execution column; current non-browser results are recorded in SCHOOL_SCENARIO_RESULTS.md. A code path or existing automated test does not count as a successful browser run. Record browser result, date, build/commit, account role and any screenshot or error next to each scenario after execution. Do not mark a scenario passed when a required browser, PostgreSQL, mail, scanner, or other service is unavailable.

The working scenario uses a fictional Pakistani school, **Crescent Model School** (`crescent-demo`), timezone `Asia/Karachi`, with one `Main Campus`, academic years **2026–27** and **2027–28**, grades/classes **7** and **8**, sections **7-A** and **8-A**, Mathematics and English, and currency **PKR**. Use synthetic identities only:

| Account | School role | Intended use |
| --- | --- | --- |
| `scenario-admin` | School admin | Approvals, final decisions, settings, school-wide oversight |
| `scenario-registrar` | Registrar | Intake, roster and history, previews; no admin-only confirmations |
| `scenario-math-teacher` | Teacher | Active Mathematics assignment in 7-A; assigned-section work |
| `scenario-english-teacher` | Teacher | Active English assignment in 8-A; proves exact assignment scope |
| `scenario-accountant` | Accountant | Fee plans, invoices, payments and reversals |
| `scenario-student-seven` | Student | Synthetic learner in 7-A, with a linked student account |
| `scenario-student-eight` | Student | Synthetic learner in 8-A, with a linked student account |
| `scenario-outsider` | No Crescent membership | Cross-school and no-membership denial cases |

Create academic years, grades, sections, subjects, memberships and teacher assignments before browser scenarios. The two fee plans are explicitly **PKR 10,000 for Grade 7 / 2026–27** and **PKR 12,000 for Grade 8 / 2027–28**. The supported workflow is manual fee-plan creation followed by manual invoice issuance against one matching enrollment and plan. The application does **not** automatically create class/year invoices when a student is registered or promoted. Do not infer invoices or payments from a plan existing.

## Execution status

**All 72 rows: BLOCKED in the cloud browser.** The requested local URL was rejected by the cloud browser security policy, which explicitly prohibits workarounds/proxies/alternate browsers. In-process request/service checks were executed separately; see SCHOOL_SCENARIO_RESULTS.md and SCHOOL_EDGE_RESULTS.md. No row is a browser pass. The automated local baseline and PostgreSQL-only skips are documented separately in `LOCAL_TEST_REPORT.md`; those results do not cover this scenario matrix. Browser execution should use the actual cloud browser and the real application UI, not direct test-client or ORM calls. If setup requires creating fixture records outside the UI, record that separately and do not count setup as workflow coverage.

Result key for later updates: `PASS` means the browser reached the expected result; `FAIL` means reproducible wrong behavior; `BLOCKED` means an environmental prerequisite prevented the test; `NOT RUN` means not attempted. Record unsupported behavior as `UNIMPLEMENTED` with the product boundary, rather than a pass/fail assertion against a feature the app does not claim.

## Admissions and permanent identity

Relevant routes: `/students/crescent-demo/students/`, `/students/crescent-demo/students/admissions/`, `/students/crescent-demo/students/admissions/intake/`, `/students/crescent-demo/students/register/`. Admission decisions are POST-only and admin-only in the service. Intake creates an application, not a Student; approval creates the permanent identity and first enrollment in the same transaction.

| ID | Role and scenario | Expected result / observable evidence | Status |
| --- | --- | --- | --- |
| ADM-01 | Registrar submits a valid new Grade 7 / 2026–27 application for synthetic **Ayesha Noor**, roll `7-021`, with guardian details. | Application appears pending; no Student or Enrollment exists until approval. | BROWSER BLOCKED |
| ADM-02 | Admin approves ADM-01. | One Student and one active enrollment are created atomically in 7-A; application points to that identity; stable `STU-…` code is shown. | BROWSER BLOCKED |
| ADM-03 | Admin rejects a separate application for **Bilal Ahmed**. | Final rejected application is retained; no Student or Enrollment is created. | BROWSER BLOCKED |
| ADM-04 | Registrar attempts the approval/rejection POST for a pending application. | Request is forbidden; application remains pending and no student identity is created. | BROWSER BLOCKED |
| ADM-05 | Submit intake with a section from 2027–28 while selecting 2026–27. | Form rejects year/section mismatch; no application or identity is created. | BROWSER BLOCKED |
| ADM-06 | Approve an application whose selected 7-A roll has since been taken by a registered student. | Approval reports the enrollment conflict; transaction creates no partial Student and application remains pending for resolution. | BROWSER BLOCKED |
| ADM-07 | Replay the same final decision on an already-approved application. | Existing decision/identity is returned; no duplicate Student or Enrollment is made. A conflicting second final decision is refused. | BROWSER BLOCKED |
| ID-01 | Registrar uses walk-in registration for **Hamza Raza**, valid 7-A placement. | One permanent Student and first active Enrollment are created; code is school-scoped and remains stable. | BROWSER BLOCKED |
| ID-02 | Try registering a student into 7-A while selecting the 2027–28 year. | Rejected because section academic year does not match; no partial identity remains. | BROWSER BLOCKED |
| ID-03 | Try re-admitting an already-active student to 8-A. | Rejected until the current active placement is closed. | BROWSER BLOCKED |
| ID-04 | Admin closes a placement as withdrawn, then registrar re-admits the same student to a later valid year/section. | Old Enrollment remains in history with withdrawn outcome; new active Enrollment is added; Student UUID/code are unchanged. | BROWSER BLOCKED |
| ID-05 | Registrar registers a different learner using a roll number already occupied in the same section. | Database uniqueness conflict is reported as a validation error; no partial identity/enrollment remains. | BROWSER BLOCKED |

## Timetable, notices and school settings

Relevant pages: `/oversight/schools/crescent-demo/`, `/oversight/schools/crescent-demo/timetable/new/`, `/oversight/schools/crescent-demo/notices/`, `/oversight/schools/crescent-demo/settings/`. Timetable overlap checks cover teacher, section and room for same-weekday time ranges. Teacher notice management is limited to an actively assigned section; school-wide settings and notices are admin-only.

| ID | Role and scenario | Expected result / observable evidence | Status |
| --- | --- | --- | --- |
| SCH-01 | Admin adds Monday Mathematics, 09:00–09:45, 7-A, room `R-7`. | Slot saves and appears on school/teacher/student scoped timetable where applicable. | BROWSER BLOCKED |
| SCH-02 | Admin adds an overlapping time for the same teacher on another section. | Conflict is rejected and original slot remains unchanged. | BROWSER BLOCKED |
| SCH-03 | Admin adds a different teacher to an overlapping slot for the same section. | Section conflict is rejected. | BROWSER BLOCKED |
| SCH-04 | Admin books `R-7` for a different section in the same campus at an overlapping time. | Room conflict is rejected; room comparison is case-insensitive. | BROWSER BLOCKED |
| SCH-05 | Admin or teacher submits an end time equal to or earlier than start time. | Form/model validation rejects the slot without writing it. | BROWSER BLOCKED |
| SCH-06 | Math teacher creates a notice for assigned 7-A and attempts to choose 8-A or a school-wide notice. | Assigned-section notice is accepted; unassigned or school-wide scope is unavailable/refused. | BROWSER BLOCKED |
| SCH-07 | English teacher attempts to edit the Math teacher's 7-A notice. | Access is denied; notice text and revision history do not change. | BROWSER BLOCKED |
| SCH-08 | Admin edits a published notice; then views its revision history. | Prior published content is retained as an immutable revision with actor attribution. | BROWSER BLOCKED |
| SCH-09 | Student opens notices and timetable. | Only published notices for the student's audience/active section and that section's active timetable are visible. | BROWSER BLOCKED |
| SCH-10 | Admin submits malformed settings JSON or unsupported policy key. | Validation error is shown; prior setting/version remains intact. | BROWSER BLOCKED |

## Attendance and correction workflow

Relevant pages: `/learning/sections/<section-id>/attendance/`, `/learning/sections/<section-id>/attendance/record/`, `/learning/attendance/corrections/`, `/learning/attendance/records/<record-id>/correct/`, `/learning/attendance/history/`. A session covers exactly the active roster in its section/year; corrections preserve the proposal and require admin review.

| ID | Role and scenario | Expected result / observable evidence | Status |
| --- | --- | --- | --- |
| ATT-01 | Math teacher records 7-A attendance for the synthetic active roster: Ayesha present, Hamza absent, another learner late. | One dated session and one record per active enrollment are stored with the chosen marks. | BROWSER BLOCKED |
| ATT-02 | Teacher omits one active student or posts an enrollment from another section. | Exact-roster validation rejects the entire session; no partial marks are saved. | BROWSER BLOCKED |
| ATT-03 | Teacher records a second attendance session for the same section/date. | Duplicate session is rejected; original records remain unchanged. | BROWSER BLOCKED |
| ATT-04 | Teacher requests a correction from absent to present with reason and corrected note. | Pending request records old/new values and reason; original attendance remains absent pending decision. | BROWSER BLOCKED |
| ATT-05 | Admin approves ATT-04. | Attendance changes to present; correction retains requester, reviewer, timestamps and before/after context. | BROWSER BLOCKED |
| ATT-06 | Admin rejects a different pending correction. | Original status/note remain unchanged; rejected request stays in history with reviewer attribution. | BROWSER BLOCKED |
| ATT-07 | Teacher submits an empty or over-limit correction reason. | Form rejects it; no correction request is created. | BROWSER BLOCKED |
| ATT-08 | Admin reviews a request older than configured correction window; also check the exact allowed-age boundary in school-local time. | Stale request is auto-rejected/refused according to policy; no stale mark change is applied. Exact date boundary should be recorded. | BROWSER BLOCKED |
| ATT-09 | Student opens attendance history while another student is selected/known. | Only own historical marks are returned; IDs/query parameters cannot select another student. | BROWSER BLOCKED |
| ATT-10 | Accountant or unrelated teacher requests the correction queue/review URL. | Forbidden; no request status or attendance record changes. | BROWSER BLOCKED |

## Assignments, assessment marks and publication

Relevant pages: `/learning/`, `/assessments/`, `/assessments/new/`, `/assessments/questions/new/`, `/assessments/<assessment-id>/`, `/assessments/report-card/`. Assignments are a separate workflow from assessments: assignment submissions can receive feedback/grade; assessment attempts follow scheduled windows and explicit submit, mark, finalize and publish stages.

| ID | Role and scenario | Expected result / observable evidence | Status |
| --- | --- | --- | --- |
| ASM-01 | Math teacher publishes an assignment for 7-A with a future due time. | Assigned 7-A students see it as upcoming; 8-A student and unrelated teacher cannot access it. | BROWSER BLOCKED |
| ASM-02 | Student-seven submits a response before due time. | One submission is stored for the student's active year-specific enrollment; duplicate submit updates the same submission rather than another learner's work. | BROWSER BLOCKED |
| ASM-03 | Math teacher grades the submission with grade and feedback. | Grade/feedback are visible to that student; unrelated teacher/student cannot read or alter them. | BROWSER BLOCKED |
| ASM-04 | Teacher authors an assessment for 7-A Mathematics with future open/close times and a bounded attempt limit. | Draft is created for the same school, section, subject, year and optional matching term. | BROWSER BLOCKED |
| ASM-05 | Teacher tries mismatched subject/section, term/year, close-before-open, malformed score or no MCQ choices. | Form/service rejects malformed or cross-scope values without creating a usable assessment/question. | BROWSER BLOCKED |
| ASM-06 | Admin opens an assessment with no attached questions, then with at least one valid question. | Empty assessment stays draft; valid nonempty assessment opens only before close time. | BROWSER BLOCKED |
| ASM-07 | Student-eight attempts to start the 7-A assessment; student-seven starts outside the schedule or above attempt limit. | Wrong active enrollment is denied; outside-window/limit errors do not create attempts. | BROWSER BLOCKED |
| ASM-08 | Student-seven starts within the window, answers objective and manual questions, saves, then submits. | Answers are tied to the active 7-A/2026–27 Enrollment; objective score is calculated; manual score remains pending. | BROWSER BLOCKED |
| ASM-09 | Student or nonassigned teacher views assessment detail/attempt; inspect page source and rendered content. | Student sees own attempt only and no answer key; unrelated teacher cannot see assessment or marks. | BROWSER BLOCKED |
| ASM-10 | Assigned teacher marks manual answer above its maximum or gives non-finite score, then submits a valid mark. | Invalid score is rejected; valid bounded mark is saved with feedback; teacher cannot finalize/publish. | BROWSER BLOCKED |
| ASM-11 | Admin finalizes before manual questions are graded; then after all answers are graded. | First finalization is refused; second freezes the calculated score, grade and grading-policy snapshot. | BROWSER BLOCKED |
| ASM-12 | Admin publishes the finalized result; student opens report card. | Published result appears only for owning student/authorized school admin; result visibility policy is honored. | BROWSER BLOCKED |
| ASM-13 | Set `student_results_visible=false`, then view as student and teacher/admin. | Student-facing result/transcript is hidden; authorized school staff retain their permitted view. | BROWSER BLOCKED |
| ASM-14 | After ASM-12, promote the student to 8-A and inspect history/report card. | Published result remains attached to the prior-year attempt/enrollment and remains in historical transcript per visibility policy. | BROWSER BLOCKED |
| ASM-15 | Submit after close with answers previously saved; separately try saving new answers after close. | Existing saved answers can be submitted; post-deadline edits are rejected and not silently persisted. | BROWSER BLOCKED |

## Fees, invoices and payments

Relevant pages: `/finance/`, `/finance/schools/crescent-demo/`, `/finance/schools/crescent-demo/plans/new/`, `/finance/schools/crescent-demo/invoices/new/`, invoice/payment/receipt URLs, `/finance/statement/`. Finance does not automatically generate invoices. A fee plan is scoped by school, academic year and optionally grade; an invoice is issued manually once per enrollment/plan pair. Amounts below are synthetic PKR values, not tuition recommendations.

| ID | Role and scenario | Expected result / observable evidence | Status |
| --- | --- | --- | --- |
| FIN-01 | Accountant creates Grade 7 / 2026–27 annual fee plan for **PKR 10,000.00**. | Plan is stored for Crescent, selected year and Grade 7 only. | BROWSER BLOCKED |
| FIN-02 | Accountant creates Grade 8 / 2027–28 annual fee plan for **PKR 12,000.00**. | Plan is stored for Grade 8 and that academic year; currency remains PKR. | BROWSER BLOCKED |
| FIN-03 | Accountant issues the Grade 7 plan against Ayesha's 7-A/2026–27 enrollment. | Exactly one invoice is issued with a charge ledger row for PKR 10,000 and matching school/year/grade. | BROWSER BLOCKED |
| FIN-04 | Accountant attempts Grade 8 plan against the Grade 7 enrollment or another academic year. | Plan/enrollment mismatch is rejected; no invoice or charge row is written. | BROWSER BLOCKED |
| FIN-05 | Accountant retries the same enrollment/plan invoice issuance. | Duplicate invoice is rejected/idempotently prevented; prior balance remains unchanged. | BROWSER BLOCKED |
| FIN-06 | Accountant issues a Grade 8 invoice for the matching 8-A/2027–28 enrollment with a valid concession below PKR 12,000. | Charge and negative concession rows produce the exact net invoice balance. | BROWSER BLOCKED |
| FIN-07 | Accountant tries a concession equal to or greater than the fee plan amount, negative, NaN or excessive magnitude. | Validation error; invoice/ledger remains unchanged. | BROWSER BLOCKED |
| FIN-08 | Accountant posts a partial PKR payment, retries same key and parameters, then tries same key with changed amount. | One payment, receipt and ledger credit exist for exact partial amount; identical retry returns same payment; changed parameters are rejected. | BROWSER BLOCKED |
| FIN-09 | Accountant attempts overpayment, wrong currency, zero, negative, excess fractional precision or extreme magnitude. | Validation error; no payment/receipt/ledger writes. | BROWSER BLOCKED |
| FIN-10 | Accountant reverses a payment with a reason, retries same key/reason, and then changes reason or key. | One compensating positive ledger row restores balance; same retry is idempotent; changed reason/key conflicts are refused; original payment/receipt stay. | BROWSER BLOCKED |
| FIN-11 | Student-seven views statement, own invoice and receipt; then requests student-eight's invoice/receipt. | Own financial records render; another student's records and all mutations are forbidden. | BROWSER BLOCKED |
| FIN-12 | Teacher, registrar or outsider opens school finance or tries payment mutation; accountant tries school settings/student admin pages. | Cross-role route access is forbidden; no financial or unrelated school data changes. | BROWSER BLOCKED |
| FIN-13 | Roster contains a student without an invoice after a plan is created or after promotion. | No automatic invoice is assumed or created; accountant must explicitly issue invoice for the relevant enrollment/plan. Record as expected product boundary. | BROWSER BLOCKED |

## Promotion, history and role boundaries

Relevant pages: `/students/crescent-demo/students/<student-code>/`, individual promotion preview/confirm routes, `/students/crescent-demo/students/promotions/batch/`. Preview is read-only. Admin confirms. Batch confirmation revalidates all submitted rows and is all-or-nothing. Target placements must be a later year in the same school with matching section/year.

| ID | Role and scenario | Expected result / observable evidence | Status |
| --- | --- | --- | --- |
| PRO-01 | Registrar previews Ayesha's 7-A/2026–27 promotion to 8-A/2027–28 with new roll `8-014`. | Preview shows source, target and can-commit result; no source status or Enrollment changes. | BROWSER BLOCKED |
| PRO-02 | Registrar submits individual promotion confirmation. | Forbidden; source remains active and history unchanged. | BROWSER BLOCKED |
| PRO-03 | Admin confirms valid promotion from PRO-01. | Source is marked promoted; one new active Enrollment is linked by previous enrollment; UUID and student code persist; both years appear in history. | BROWSER BLOCKED |
| PRO-04 | Try target section from another school, mismatched year, same/earlier academic year, occupied target roll or existing student/year row. | Preview/commit refuses conflict; source and history remain unchanged. | BROWSER BLOCKED |
| PRO-05 | Admin previews a repeat-year outcome into a later year and a conditional placement without reason. | Valid repeat preview allowed; missing/overlong conditional reason is rejected before commit. | BROWSER BLOCKED |
| PRO-06 | Admin graduates a student with no target; separately submits graduation with a target section/year. | No-target graduation preserves history and creates no successor; target on graduation is rejected. | BROWSER BLOCKED |
| PRO-07 | Registrar previews a batch containing multiple valid rows, then leaves without confirming. | Preview has no mutations. All rows still have their prior active statuses and no successors. | BROWSER BLOCKED |
| PRO-08 | Admin confirms a valid two-student batch. | All outcomes commit; immutable decision snapshots share a batch ID and retain actor/source/target details. | BROWSER BLOCKED |
| PRO-09 | Admin confirms batch containing malformed UUID, duplicate source, duplicate target roll, stale source or invalid target. | Entire batch is rejected/rolled back; no partial statuses, successor enrollments or decision history. | BROWSER BLOCKED |
| PRO-10 | Student-seven opens another student's detail, enrollment history, transcript or invoice by substituting URL identifier. | Denied or not found; no cross-student disclosure. | BROWSER BLOCKED |
| PRO-11 | Deactivate a teacher membership/assignment or student membership, then reuse an existing browser session. | Relevant scoped access is denied using live user/membership/assignment state; stale session does not preserve school access. | BROWSER BLOCKED |
| PRO-12 | User belongs to another school but guesses Crescent slug, object UUID, assessment ID or receipt ID. | School/object access is denied without leaking protected payloads. | BROWSER BLOCKED |

## Out of scope or service-dependent

These are not implied passes or hidden features of the matrix:

- Automatic fee-plan creation, automatic invoice generation, installment schedules, currency conversion, late fees and refunds are not part of the current finance workflow. Test FIN-13 as a product boundary; do not expect a generated invoice.
- A browser-only run cannot validate PostgreSQL row-lock/concurrency behavior. Promotion batch atomicity and the reviewed assessment-start/enrollment-close race require PostgreSQL concurrency tests; report them as `BLOCKED` or `NOT RUN` if no PostgreSQL execution is available.
- MFA setup/login requires a valid encryption key and is outside these school operational workflows. File attachment acceptance requires configured malware scanning; an unavailable scanner must fail closed and is not evidence of a successful upload.
- Email delivery, off-host recovery, production persistence, and cloud scanner behavior require their configured external services and are not proven by synthetic browser data.
- Real pupil information, actual bank details, real phone numbers and credentials must not be entered. Use a disposable database and synthetic accounts only.

## Result log template

Copy this block for each browser session and fill it from observed evidence:

```text
Build / commit:
Browser and date:
Environment / school fixture:
Accounts and roles exercised:
Scenario IDs attempted:
PASS IDs:
FAIL IDs (role, URL, steps, expected vs actual, screenshot/error):
BLOCKED / NOT RUN IDs and reason:
UNIMPLEMENTED boundaries:
Data cleanup / disposable database confirmation:
```

## Additional portal gaps found by inspection

The request-level run uses Crescent Model School, years2026–27/2027–28, Grade7/8 and Ayesha Example. The service-level run uses an equivalent isolated Scenario North fixture and Amina Learner in the same years; its results do not assert that every exact matrix input was executed.

Withdrawal/re-admission (ID-03/04) and account linking are guarded service operations, with no dedicated regular-portal form/routes in the current URL configuration. Setup/linking performed by fixtures is not UI coverage. Published notice/settings revisions are retained and tested at model/service level, but the notice edit/settings templates do not contain a dedicated revision-history viewer. Those requested browser-visible actions require product/UI work in addition to an accessible browser target.

The full matrix contains72 scenarios, not72 browser passes. Automatic invoice generation is unimplemented; class/year plans with explicit invoice issuance are supported and verified at request/service level.
