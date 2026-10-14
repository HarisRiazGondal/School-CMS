# MVP test and browser acceptance guide

## Automated checks

Run these from the repository root with the project environment active:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
```

`makemigrations --check --dry-run` must report no model changes pending. The test suite covers account and school workflows, identity/enrollment lifecycle, learning, assessment and finance workflows, and authorization boundaries. `tests/test_demo75.py` verifies that repeat seeding stays idempotent after a student submits an assessment attempt and the accountant posts a payment. Run it against a fresh local database when validating a clean checkout.

## Synthetic browser demo

Create or refresh the demo data in a development environment:

```sh
python manage.py seed_demo --password 'choose-a-local-demo-password'
python manage.py runserver
```

Visit <http://127.0.0.1:8000/> and use the password supplied to the command with one of these usernames. The dashboard is at `/`; student records are at `/students/demo-school/students/`; the role-scoped learning portal is at `/learning/`.

| Role | Username | Acceptance path |
| --- | --- | --- |
| School admin | `demo-admin` | Sign in, then open student records and the learning portal. |
| Registrar | `demo-registrar` | Open `/students/demo-school/students/` and verify the current-year enrollment. |
| Teacher | `demo-teacher` | Open `/learning/` and see the assigned class section. |
| Accountant | `demo-accountant` | Open `/finance/`, then Demo School. Review the annual fee plan and Casey’s unpaid invoice. |
| Student | `demo-student` | Open `/learning/` and see the learner's active enrollment and published classwork. |

These usernames and all names/records are synthetic. The command does not embed a password; the operator supplies one, and the command refuses to run when `DEBUG` is false. Each invocation sets that password for the known demo accounts. Reruns do not reset assessment attempts, answers, posted invoices, payments, receipts, or ledger entries. The seeded assessment is open and has one MCQ, one true/false question, and one manually marked short-answer question. It creates no attempt and posts no payment automatically; the fee invoice starts unpaid.

Run `seed_demo` twice to confirm there are no duplicate schools, memberships, years, sections, students, enrollments, assignments, assessment questions, fee plans, or invoices. After a student submits an attempt and an accountant records a payment, rerun it: the attempt and its answers, invoice balance, receipt, and ledger history must remain unchanged.

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
