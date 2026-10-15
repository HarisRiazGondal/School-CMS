"""Cross-module synthetic-school lifecycle acceptance (HTTP/service level).

These checks exercise the domain services against Django's test database. They
are not browser acceptance tests and do not claim visual/UI coverage.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from assessment.models import Assessment, Attempt, Question
from assessment.services import (
    attach_question, begin_attempt, create_assessment, create_question,
    finalize_attempt, grade_answer, open_assessment, publish_attempt,
    published_transcript, save_answer, submit_attempt,
)
from finance.models import Invoice, LedgerEntry, Payment
from finance.services import (
    create_fee_plan, fee_statement, issue_invoice, post_payment, reverse_payment,
)
from learning.models import AttendanceRecord, TeacherAssignment
from learning.services import (
    create_assignment, create_attendance, grade_submission,
    request_attendance_correction, review_attendance_correction,
    submit_assignment,
)
from oversight.models import TimetableSlot
from oversight.services import create_timetable_slot
from schools.models import AcademicYear, School
from students.models import AdmissionApplication, Enrollment, Student
from students.services import (
    commit_promotion, decide_admission_application, link_student_account,
    preview_promotion, register_student, submit_admission_application,
)


class SyntheticSchoolLifecycleAcceptanceTests(TestCase):
    """Prove the linked school lifecycle with isolated, synthetic records."""

    def setUp(self):
        self.school = School.objects.create(name="Scenario North School", slug="scenario-north")
        self.other_school = School.objects.create(name="Scenario South School", slug="scenario-south")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.next_year = AcademicYear.objects.create(
            school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31),
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other_school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31),
        )
        self.grade7 = SchoolClass.objects.create(school=self.school, name="Class 7")
        self.grade8 = SchoolClass.objects.create(school=self.school, name="Class 8")
        other_grade = SchoolClass.objects.create(school=self.other_school, name="Class 8")
        self.section7 = Section.objects.create(school_class=self.grade7, academic_year=self.year, name="A")
        self.section7_b = Section.objects.create(school_class=self.grade7, academic_year=self.year, name="B")
        self.section8 = Section.objects.create(school_class=self.grade8, academic_year=self.next_year, name="A")
        self.other_section = Section.objects.create(
            school_class=other_grade, academic_year=self.other_year, name="A",
        )
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        self.other_subject = Subject.objects.create(school=self.other_school, name="Mathematics", code="MATH")

        self.admin = self._user("scenario-admin", SchoolMembership.Role.SCHOOL_ADMIN)
        self.registrar = self._user("scenario-registrar", SchoolMembership.Role.REGISTRAR)
        self.teacher = self._user("scenario-teacher", SchoolMembership.Role.TEACHER)
        self.accountant = self._user("scenario-accountant", SchoolMembership.Role.ACCOUNTANT)
        self.student_user = self._user("scenario-student", SchoolMembership.Role.STUDENT)
        self.outsider = self._user("scenario-outsider", SchoolMembership.Role.TEACHER, school=self.other_school)
        self.assignment = TeacherAssignment.objects.create(
            user=self.teacher, section=self.section7, subject=self.subject,
        )
        self.other_section_assignment = TeacherAssignment.objects.create(
            user=self.teacher, section=self.section7_b, subject=self.subject,
        )

    def _user(self, username, role, *, school=None):
        user = User.objects.create_user(username=username, email=f"{username}@example.invalid", password="unused-test-password")
        SchoolMembership.objects.create(user=user, school=school or self.school, role=role)
        return user

    def test_full_admission_learning_assessment_finance_and_promotion_cycle(self):
        # Intake remains pending until an administrator approves it. Rejection
        # creates no permanent student identity.
        approved_application = submit_admission_application(
            user=self.registrar, school=self.school, first_name="Amina", last_name="Learner",
            academic_year=self.year, section=self.section7, roll_number="7A-01",
            guardian_name="Synthetic Guardian", guardian_phone="000-000-0000",
        )
        rejected_application = submit_admission_application(
            user=self.registrar, school=self.school, first_name="Rejected", last_name="Applicant",
            academic_year=self.year, section=self.section7, roll_number="7A-99",
        )
        self.assertEqual(approved_application.status, AdmissionApplication.Status.PENDING)
        self.assertFalse(Student.objects.filter(first_name="Amina").exists())
        _, student, enrollment = decide_admission_application(
            user=self.admin, application=approved_application,
            decision=AdmissionApplication.Status.APPROVED, note="Documents checked.",
        )
        _, rejected_student, rejected_enrollment = decide_admission_application(
            user=self.admin, application=rejected_application,
            decision=AdmissionApplication.Status.REJECTED, note="Synthetic rejection check.",
        )
        self.assertIsNone(rejected_student)
        self.assertIsNone(rejected_enrollment)
        self.assertFalse(Student.objects.filter(first_name="Rejected").exists())
        link_student_account(user=self.admin, student=student, account=self.student_user)
        student.refresh_from_db()
        original_student_id, original_student_code = student.pk, student.student_code

        # A valid timetable entry is accepted, while an overlapping teacher
        # booking is blocked before it can be written.
        slot = create_timetable_slot(
            self.admin, assignment=self.assignment, weekday=TimetableSlot.Weekday.MONDAY,
            starts_at=time(9, 0), ends_at=time(9, 45), room="Room 7A",
        )
        self.assertEqual(slot.section.pk, self.section7.pk)
        with self.assertRaises(ValidationError):
            create_timetable_slot(
                self.admin, assignment=self.other_section_assignment, weekday=TimetableSlot.Weekday.MONDAY,
                starts_at=time(9, 30), ends_at=time(10, 15), room="Room 7B",
            )
        self.assertEqual(TimetableSlot.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            create_timetable_slot(
                self.teacher, assignment=self.assignment, weekday=TimetableSlot.Weekday.TUESDAY,
                starts_at=time(9, 0), ends_at=time(9, 45),
            )

        # Attendance uses a proposal/review workflow; classwork links the same
        # permanent identity to a submitted and graded piece of work.
        session = create_attendance(
            self.teacher, self.section7, timezone.localdate() - timedelta(days=1),
            {str(enrollment.pk): AttendanceRecord.Status.PRESENT},
        )
        attendance_record = session.records.get(enrollment=enrollment)
        correction = request_attendance_correction(
            self.teacher, attendance_record, new_status=AttendanceRecord.Status.LATE,
            reason="Corrected against the signed register.", new_note="Arrived after roll call.",
        )
        self.assertEqual(attendance_record.status, AttendanceRecord.Status.PRESENT)
        review_attendance_correction(self.admin, correction, approve=True, review_note="Register verified.")
        attendance_record.refresh_from_db()
        self.assertEqual(attendance_record.status, AttendanceRecord.Status.LATE)
        with self.assertRaises(PermissionDenied):
            request_attendance_correction(
                self.outsider, attendance_record, new_status=AttendanceRecord.Status.ABSENT,
                reason="Cross-school attempt.",
            )

        assignment = create_assignment(
            self.teacher, self.section7, self.subject,
            title="Ratios practice", instructions="Show each step.", publish=True,
        )
        submission = submit_assignment(self.student_user, assignment, "2:3 simplifies to 2/3.")
        grade_submission(self.teacher, submission, grade=Decimal("88.00"), feedback="Clear working.")
        submission.refresh_from_db()
        self.assertEqual(submission.grade, Decimal("88.00"))

        # Mixed objective/manual assessment preserves automatic marks, requires
        # teacher grading and administrator finalization/publication.
        now = timezone.now()
        assessment = create_assessment(
            self.teacher, section=self.section7, subject=self.subject, title="Fractions check",
            opens_at=now - timedelta(minutes=1), closes_at=now + timedelta(days=1),
            attempt_limit=1, pass_percent=Decimal("50.00"),
        )
        mcq = create_question(
            self.teacher, subject=self.subject, kind=Question.Kind.MCQ,
            prompt="What is 1/2 + 1/2?", max_points="2.00",
            choices=["1", "2"], correct_answer="1",
        )
        manual = create_question(
            self.teacher, subject=self.subject, kind=Question.Kind.MANUAL,
            prompt="Explain equivalent fractions.", max_points="3.00",
        )
        mcq = attach_question(self.teacher, assessment, mcq)
        manual = attach_question(self.teacher, assessment, manual)
        open_assessment(self.teacher, assessment)
        attempt = begin_attempt(assessment, enrollment, self.student_user)
        save_answer(attempt, mcq, "1", self.student_user)
        save_answer(attempt, manual, "Multiply numerator and denominator by the same number.", self.student_user)
        submit_attempt(attempt, self.student_user)
        attempt.refresh_from_db()
        self.assertEqual(attempt.answers.get(question=mcq).awarded_points, Decimal("2.00"))
        self.assertIsNone(attempt.answers.get(question=manual).awarded_points)
        with self.assertRaises(PermissionDenied):
            finalize_attempt(attempt, self.teacher)
        with self.assertRaises(ValidationError):
            finalize_attempt(attempt, self.admin)
        grade_answer(attempt.answers.get(question=manual), Decimal("2.50"), self.teacher, "Correct explanation.")
        finalized = finalize_attempt(attempt, self.admin)
        self.assertEqual(finalized.raw_score, Decimal("4.50"))
        publish_attempt(finalized, self.admin)

        # Finance is deliberately issued by staff as an explicit workflow. This
        # scenario does not assert automatic invoice generation at promotion.
        fee_plan7 = create_fee_plan(
            user=self.accountant, school=self.school, academic_year=self.year,
            amount=Decimal("10000.00"), currency="PKR", grade=self.grade7, name="Class 7 annual fee",
        )
        self.assertFalse(Invoice.objects.filter(enrollment=enrollment).exists())
        invoice7 = issue_invoice(user=self.accountant, enrollment=enrollment, fee_plan=fee_plan7, concession="1000.00")
        self.assertEqual(invoice7.balance, Decimal("9000.00"))
        with self.assertRaises(ValidationError):
            issue_invoice(user=self.accountant, enrollment=enrollment, fee_plan=fee_plan7)
        payment = post_payment(
            user=self.accountant, invoice=invoice7, amount=Decimal("3000.00"), currency="PKR",
            idempotency_key="scenario-class7-partial-1",
        )
        retried_payment = post_payment(
            user=self.accountant, invoice=invoice7, amount=Decimal("3000.00"), currency="PKR",
            idempotency_key="scenario-class7-partial-1",
        )
        self.assertEqual(retried_payment.pk, payment.pk)
        with self.assertRaises(ValidationError):
            post_payment(
                user=self.accountant, invoice=invoice7, amount=Decimal("2500.00"), currency="PKR",
                idempotency_key="scenario-class7-partial-1",
            )
        receipt_code = payment.receipt.receipt_code
        self.assertEqual(invoice7.balance, Decimal("6000.00"))
        reversal = reverse_payment(
            user=self.admin, payment=payment, idempotency_key="scenario-class7-reversal-1",
            reason="Synthetic cashier correction.",
        )
        retried_reversal = reverse_payment(
            user=self.admin, payment=payment, idempotency_key="scenario-class7-reversal-1",
            reason="Synthetic cashier correction.",
        )
        self.assertEqual(retried_reversal.pk, reversal.pk)
        self.assertEqual(reversal.kind, LedgerEntry.Kind.REVERSAL)
        self.assertEqual(invoice7.balance, Decimal("9000.00"))
        payment.refresh_from_db()
        self.assertEqual(payment.receipt.receipt_code, receipt_code)
        self.assertEqual(Payment.objects.filter(pk=payment.pk).count(), 1)
        with self.assertRaises(ValidationError):
            reverse_payment(
                user=self.admin, payment=payment, idempotency_key="scenario-class7-reversal-2",
                reason="A second reversal must be rejected.",
            )
        with self.assertRaises(PermissionDenied):
            issue_invoice(user=self.teacher, enrollment=enrollment, fee_plan=fee_plan7)
        with self.assertRaises(PermissionDenied):
            issue_invoice(user=self.outsider, enrollment=enrollment, fee_plan=fee_plan7)

        # Promotion retains the source enrollment, assessment result, and fee
        # history; duplicate roll numbers are rejected before valid promotion.
        reserve_student, _ = register_student(
            user=self.admin, school=self.school, first_name="Reserved", academic_year=self.next_year,
            section=self.section8, roll_number="8A-99",
        )
        blocked = preview_promotion(
            user=self.admin, source=enrollment, outcome=Enrollment.Status.PROMOTED,
            target_year=self.next_year, target_section=self.section8, target_roll_number="8A-99",
        )
        self.assertFalse(blocked.can_commit)
        with self.assertRaises(ValidationError):
            commit_promotion(
                user=self.admin, source=enrollment, outcome=Enrollment.Status.PROMOTED,
                target_year=self.next_year, target_section=self.section8, roll_number="8A-99",
            )
        with self.assertRaises(PermissionDenied):
            commit_promotion(
                user=self.registrar, source=enrollment, outcome=Enrollment.Status.PROMOTED,
                target_year=self.next_year, target_section=self.section8, roll_number="8A-01",
            )
        with self.assertRaises(ValidationError):
            preview_promotion(
                user=self.admin, source=enrollment, outcome=Enrollment.Status.PROMOTED,
                target_year=self.other_year, target_section=self.other_section, target_roll_number="X-01",
            )

        source, next_enrollment = commit_promotion(
            user=self.admin, source=enrollment, outcome=Enrollment.Status.PROMOTED,
            target_year=self.next_year, target_section=self.section8, roll_number="8A-01",
        )
        self.assertEqual(source.status, Enrollment.Status.PROMOTED)
        self.assertEqual(next_enrollment.previous_enrollment_id, enrollment.pk)
        self.assertEqual(Student.objects.get(pk=original_student_id).student_code, original_student_code)
        self.assertEqual(Student.objects.get(pk=original_student_id).enrollments.count(), 2)
        with self.assertRaises(ValidationError):
            commit_promotion(
                user=self.admin, source=enrollment, outcome=Enrollment.Status.PROMOTED,
                target_year=self.next_year, target_section=self.section8, roll_number="8A-02",
            )

        fee_plan8 = create_fee_plan(
            user=self.accountant, school=self.school, academic_year=self.next_year,
            amount=Decimal("12000.00"), currency="PKR", grade=self.grade8, name="Class 8 annual fee",
        )
        self.assertFalse(Invoice.objects.filter(enrollment=next_enrollment).exists())
        invoice8 = issue_invoice(user=self.accountant, enrollment=next_enrollment, fee_plan=fee_plan8)
        self.assertEqual(invoice8.balance, Decimal("12000.00"))
        self.assertEqual(invoice7.enrollment.academic_year.name, "2026-27")
        statement = list(fee_statement(user=self.student_user, student=student))
        self.assertEqual({item.fee_plan.amount for item in statement}, {Decimal("10000.00"), Decimal("12000.00")})
        self.assertEqual({item.enrollment.academic_year.name for item in statement}, {"2026-27", "2027-28"})
        self.assertEqual(Invoice.objects.filter(enrollment__student=student).count(), 2)

        transcript = published_transcript(student, self.student_user)
        self.assertIn(self.year, transcript)
        self.assertEqual(transcript[self.year][0]["attempt"].pk, attempt.pk)
        with self.assertRaises(PermissionDenied):
            published_transcript(student, self.outsider)
