# MVP test and browser acceptance guide

## Automated checks

Run these from the repository root with the project environment active:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
```

`makemigrations --check --dry-run` must report no model changes pending. The test suite covers account and school workflows, identity/enrollment lifecycle, learning, assessment and finance workflows, and authorization boundaries. `tests/test_demo75.py` verifies reseeding after assessment submission and payment posting. `tests/test_demo87.py` checks the admissions and attendance-correction fixtures, and confirms changed settings/notices and reviewed histories survive reseeding. Run both against a fresh local database when validating a clean checkout.

## Synthetic browser demo

Create or refresh the demo data in a development environment:

```sh
python manage.py seed_demo --password 'choose-a-local-demo-password'
python manage.py runserver
```

Visit <http://127.0.0.1:8000/> and use the password supplied to the command with one of these usernames. The dashboard is at `/`; student records are at `/students/demo-school/students/`; the role-scoped learning portal is at `/learning/`.

| Role | Username | Acceptance path |
| --- | --- | --- |
| School admin | `demo-admin` | Sign in, then open student records, admissions, attendance corrections, oversight and the learning portal. |
| Registrar | `demo-registrar` | Open `/students/demo-school/students/`, verify the current-year enrollment, and review the admissions queue. |
| Teacher | `demo-teacher` | Open `/learning/` and see the assigned class section, attendance, correction workload, timetable and notices. |
| Accountant | `demo-accountant` | Open `/finance/`, then Demo School. Review the annual fee plan and Casey’s unpaid invoice. |
| Student | `demo-student` | Open `/learning/` and see the learner's active enrollment, attendance history and published classwork. |

These usernames and all names/records are synthetic. The command does not embed a password; the operator supplies one, and the command refuses to run when `DEBUG` is false. Each invocation sets that password for the known demo accounts. Reruns preserve settings and notice edits, admission decisions, attendance correction histories, assessment attempts, answers, posted invoices, payments, receipts and ledger entries. The seed creates an open assessment and one unpaid invoice, but no admission approval, assessment attempt or payment. The attendance correction fixture is dated one local calendar day ago; the configured default permits requests through day seven.

Run `seed_demo` twice to confirm there are no duplicate schools, memberships, years, sections, students, enrollments, assignments, assessment questions, fee plans, or invoices. After a student submits an attempt and an accountant records a payment, rerun it: the attempt and its answers, invoice balance, receipt, and ledger history must remain unchanged.

## Admissions and attendance corrections

1. Sign in as `demo-registrar` and open `/students/demo-school/students/admissions/`. Jordan Applicant should be pending and have no student identity yet.
2. Sign in as `demo-admin`, open the admissions queue, and approve or reject the application. Approval creates the identity and first enrollment in the decision transaction; rejection creates neither. Rerun the seed and confirm the decision remains final.
3. Sign in as `demo-teacher`, open the assigned section's attendance list, and inspect the pending request tied to Casey's one-day-old absence. The stored mark remains absent while the request is pending. The **Request correction** link on any other attendance mark opens the request form; the teacher must provide a reason.
4. As `demo-admin`, review and approve the request. Confirm Casey's current mark becomes present and the request retains its original and proposed values, requester, reviewer and timestamps. A rejected request leaves the mark unchanged. Requests older than the configured window are refused; day seven is inside the default window.
5. Sign in as `demo-student` and open `/learning/attendance/history/` to verify that the page contains only the student's own attendance history.

## Timetable, notices and settings

1. Sign in as `demo-admin` and open `/oversight/schools/demo-school/`. Confirm the seeded Monday mathematics slot and published school notice are visible.
2. Open `/oversight/schools/demo-school/settings/` and change the timezone or attendance correction window. Save and rerun `seed_demo`; the changed value and its revision history must remain intact.
3. Open `/oversight/schools/demo-school/notices/`, edit the seeded notice, and rerun the seed. Its changed text must remain. Published notices are scoped to their audience and section. School admins manage schoolwide notices; teachers may create/edit notices only for sections they actively teach, and cannot take over a schoolwide or unrelated-section notice.
4. As `demo-teacher`, use **Create notice** and choose the assigned section. Confirm a schoolwide or unassigned-section notice cannot be submitted or edited.
5. Create another timetable slot at `/oversight/schools/demo-school/timetable/new/` for an active teacher assignment. Overlapping teacher, section or room bookings should be rejected.

## Assessment browser acceptance

1. Sign in as `demo-student`, open `/assessments/`, select **Fractions mastery check**, and start an attempt. Answer the multiple-choice and true/false items and write a short explanation for the manual question; submit the attempt.
2. Sign in as `demo-teacher`, open `/assessments/` and the same assessment. Open the submitted attempt, mark the short answer with a score from 0 to 3, and save it. Objective questions are scored automatically.
3. Sign in as `demo-admin`, open that assessment, finalize the submitted attempt, then publish the finalized result. Only a school admin can finalize and publish results.
4. Sign in as `demo-student` and open `/assessments/report-card/`. Confirm the published score is visible. A student's attempt and answers remain tied to that year-specific enrollment if they are promoted later.

The seeded assessment is open on creation, so the student can begin immediately. Teacher/admin inspection pages expose private scoring keys only to authorized assessment managers; student-facing views must not reveal them.

## Finance browser acceptance

1. Sign in as `demo-accountant`, open `/finance/`, then Demo School. Verify the annual fee plan and Casey's posted invoice appear with an outstanding balance. The seed itself does not collect money.
2. Open the invoice, choose **Post payment**, and enter a partial or full amount plus a unique idempotency key. Confirm the response opens an immutable receipt at `/finance/receipts/<receipt-uuid>/` and the invoice balance is reduced.
3. Sign in as `demo-student` and open `/finance/statement/`. Confirm only Casey's own invoice and receipt are visible. The invoice detail and receipt should also be accessible to this student.
4. Sign back in as `demo-accountant`, open the invoice payment, choose **Reverse**, enter a reason and a new idempotency key, and confirm. Verify the ledger contains a compensating reversal and the outstanding balance increases by the reversed amount; the original payment and receipt remain in history.

For a separate invoice-issuance check, an accountant can create a new fee plan at `/finance/schools/demo-school/plans/new/` and issue it against an enrollment at `/finance/schools/demo-school/invoices/new/`. An invoice can be issued only once for the same enrollment and plan. Finance pages require an active accountant or school-admin membership; other roles and students cannot access school-wide finance records.

## Key acceptance checks

- A user without an active school membership cannot access a school workflow after signing in.
- A student sees their own profile/enrollment and published classwork only.
- A teacher sees classwork and assessments only for sections and subjects to which they are assigned.
- Assessment attempts enforce their scheduled window and limit, objective questions score automatically, manual short answers require teacher grading, and an admin finalizes and publishes results.
- Accountants and school admins can create fee plans and issue invoices for their school; payments create receipts and append-only ledger entries, and reversals are compensating entries.
- A registrar can verify a learner's year-specific enrollment and contextual roll number.
- Deactivated accounts lose access, including existing sessions.
- Login forms use CSRF protection; logout uses a state-changing POST.

Record actual command output and any gaps in `docs/ai-context/08_TEST_RELEASE_STATUS.md` before treating a check as passed.

## Promotion test

The demo includes a next academic year with Grade 8 / B. Sign in as demo-admin, open Casey’s student history, preview a promotion to that year/section with a new roll number, then confirm. The code and UUID stay the same; the prior-year row remains visible with its outcome. Registrar users may preview but cannot confirm. The demo seed does not reset completed enrollment history.

## Batch progression and effective policies

Open `/students/demo-school/students/promotions/batch/` as a registrar or school admin. For each displayed active enrollment, select an outcome, target year/section and roll number; supply a condition reason for conditional outcomes. Leave the target year and section blank for graduation. The form retains the source enrollment identity automatically. Preview must make no changes. Only an admin may confirm. One malformed UUID, duplicate roll, stale source or invalid target blocks the entire batch. Graduation has no target; conditional decisions require a reason. Successful confirmation retains source placement and immutable attributed decision snapshots with a common batch ID.

In school settings, test `late_submission_allowed=false` with overdue text work, `attendance_correction_days` against a record outside that school's local-date window, `student_results_visible=false` against student grades/feedback, assessment detail, transcript and dashboard, and `notice_expiry_days` against a newly published notice without explicit expiry. Authorized teachers/admins retain their permitted result access. Terminology/branding are currently rendered on oversight pages; exported branded report cards and a global theme editor are future work.

## Windows local handoff

The latest checked interpreter is Python3.12. From a checkout of `codex/production-hardening-20261015` (the default main branch is an earlier snapshot), PowerShell can run the virtual-environment interpreter directly (no activation-policy change is needed):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path ".env")) { Copy-Item ".env.example" ".env" }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py seed_demo --password 'choose-your-local-demo-password'
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Replace the sample demo password before seeding and use that same value for the five synthetic accounts listed above. Keep the development server bound to loopback. Open <http://127.0.0.1:8000/>; the school administrator portal is `/oversight/schools/demo-school/`. `demo-admin` is the school portal account; Django's separate `/admin/` maintenance interface needs a deliberately provisioned staff account.

Start with the five role journeys, then submit an assessment, grade/finalize/publish it, post/reverse a synthetic payment, approve an admission/correction, and confirm promotion while checking historical records. The console email backend allows reset-flow inspection without SMTP. Private uploads require a working scanner; missing scanner failures are deliberate, not a successful scan. MFA setup needs its encryption key configured.

For each issue, record: role, page URL, exact synthetic steps, expected result, actual result, traceback or screenshot, and whether it repeats in a fresh demo. See [LOCAL_TEST_REPORT.md](LOCAL_TEST_REPORT.md) for the latest automated findings and fixes. CI/VPS work is deferred while this local acceptance is underway.
