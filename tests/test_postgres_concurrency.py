"""Real row-lock/concurrency regressions; deliberately skipped on SQLite."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time, timedelta
from threading import Barrier
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from assessment.services import attach_question, begin_attempt, create_assessment, create_question, open_assessment
from finance.models import Invoice, LedgerEntry, Payment
from finance.services import create_fee_plan, issue_invoice, post_payment, reverse_payment
from learning.models import AttendanceRecord, TeacherAssignment
from learning.services import request_attendance_correction, review_attendance_correction
from oversight.models import TimetableSlot
from oversight.services import create_timetable_slot
from schools.models import AcademicYear, School
from students.models import AdmissionApplication, Enrollment, PromotionDecision, Student
from students.services import (
    commit_batch_promotion, decide_admission_application, register_student,
    submit_admission_application,
)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock behavior is not exercised on SQLite.")
class PostgresConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.school = School.objects.create(name="Concurrency School", slug="concurrency-school")
        self.school_b = School.objects.create(name="Concurrency Annex", slug="concurrency-annex")
        self.admin = self.make_user("concurrency-admin", self.school, SchoolMembership.Role.SCHOOL_ADMIN)
        self.admin_b = self.make_user("concurrency-admin-b", self.school_b, SchoolMembership.Role.SCHOOL_ADMIN)
        self.accountant = self.make_user("concurrency-accountant", self.school, SchoolMembership.Role.ACCOUNTANT)
        self.teacher = User.objects.create_user(
            username="concurrency-teacher", email="concurrency-teacher@example.test", password="safe-long-password"
        )
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.teacher, school=self.school_b, role=SchoolMembership.Role.TEACHER)
        self.student_user = self.make_user("concurrency-student", self.school, SchoolMembership.Role.STUDENT)
        self.year = self.make_year(self.school, "2026-27", 2026)
        self.next_year = self.make_year(self.school, "2027-28", 2027)
        self.year_b = self.make_year(self.school_b, "2026-27", 2026)
        self.grade = SchoolClass.objects.create(school=self.school, name="Grade 4")
        self.grade_next = SchoolClass.objects.create(school=self.school, name="Grade 5")
        self.grade_b = SchoolClass.objects.create(school=self.school_b, name="Grade 4")
        self.section = Section.objects.create(school_class=self.grade, academic_year=self.year, name="A")
        self.target = Section.objects.create(school_class=self.grade_next, academic_year=self.next_year, name="A")
        self.section_b = Section.objects.create(school_class=self.grade_b, academic_year=self.year_b, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Math", code="MATH")
        self.subject_b = Subject.objects.create(school=self.school_b, name="Math", code="MATH")
        self.assignment = TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        self.assignment_b = TeacherAssignment.objects.create(user=self.teacher, section=self.section_b, subject=self.subject_b)

    def make_user(self, username, school, role):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="safe-long-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    @staticmethod
    def make_year(school, name, start):
        return AcademicYear.objects.create(
            school=school, name=name, starts_on=date(start, 8, 1), ends_on=date(start + 1, 7, 31)
        )

    def run_together(self, *calls):
        barrier = Barrier(len(calls))

        def run(call):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return call()
                except Exception as exc:
                    return exc
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = [pool.submit(run, call) for call in calls]
            return [future.result(timeout=20) for future in futures]

    def student_enrollment(self, name="Amina", roll="01", student_user=None):
        return register_student(
            user=self.admin, school=self.school, first_name=name, academic_year=self.year,
            section=self.section, roll_number=roll, student_user=student_user,
        )

    def test_simultaneous_payment_retry_and_reversal_are_idempotent(self):
        _, enrollment = self.student_enrollment()
        plan = create_fee_plan(user=self.accountant, school=self.school, academic_year=self.year,
                               grade=self.grade, amount="100.00")
        invoice = issue_invoice(user=self.admin, enrollment=enrollment, fee_plan=plan)
        payments = self.run_together(*[
            lambda: post_payment(user=self.accountant, invoice=invoice.pk, amount="30.00", currency="PKR", idempotency_key="same-payment")
            for _ in range(2)
        ])
        self.assertEqual(payments[0].pk, payments[1].pk)
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)
        reversals = self.run_together(*[
            lambda: reverse_payment(user=self.admin, payment=payments[0].pk,
                                     idempotency_key="same-reversal", reason="Duplicate entry")
            for _ in range(2)
        ])
        self.assertEqual(reversals[0].pk, reversals[1].pk)
        self.assertEqual(LedgerEntry.objects.filter(payment=payments[0], kind=LedgerEntry.Kind.REVERSAL).count(), 1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance, invoice.original_amount)

    def test_simultaneous_invoice_issue_creates_one_invoice_and_charge(self):
        _, enrollment = self.student_enrollment()
        plan = create_fee_plan(user=self.accountant, school=self.school, academic_year=self.year,
                               grade=self.grade, amount="100.00")
        results = self.run_together(*[
            lambda: issue_invoice(user=self.admin, enrollment=enrollment.pk, fee_plan=plan.pk)
            for _ in range(2)
        ])
        successes = [result for result in results if isinstance(result, Invoice)]
        errors = [result for result in results if isinstance(result, ValidationError)]
        self.assertEqual((len(successes), len(errors)), (1, 1))
        self.assertEqual(Invoice.objects.filter(enrollment=enrollment, fee_plan=plan).count(), 1)
        self.assertEqual(LedgerEntry.objects.filter(invoice=successes[0], kind=LedgerEntry.Kind.CHARGE).count(), 1)

    def test_simultaneous_admission_approval_returns_one_identity(self):
        application = submit_admission_application(
            user=self.admin, school=self.school, first_name="Nora", academic_year=self.year,
            section=self.section, roll_number="12",
        )
        results = self.run_together(*[
            lambda: decide_admission_application(user=self.admin, application=application.pk,
                                                 decision=AdmissionApplication.Status.APPROVED)
            for _ in range(2)
        ])
        self.assertEqual(results[0][1].pk, results[1][1].pk)
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionApplication.Status.APPROVED)
        self.assertEqual(Student.objects.filter(admission_application=application).count(), 1)
        self.assertEqual(Enrollment.objects.filter(student=results[0][1], academic_year=self.year).count(), 1)

    def test_simultaneous_batch_promotion_writes_one_decision_and_successor(self):
        _, source = self.student_enrollment()
        rows = [{"source_id": str(source.pk), "outcome": Enrollment.Status.PROMOTED,
                 "target_year": self.next_year.pk, "target_section": self.target.pk, "roll_number": "01"}]
        results = self.run_together(*[
            lambda: commit_batch_promotion(user=self.admin, school=self.school, rows=rows)
            for _ in range(2)
        ])
        self.assertEqual(len(results), 2)
        self.assertEqual(PromotionDecision.objects.filter(source_enrollment=source).count(), 1)
        self.assertEqual(Enrollment.objects.filter(student=source.student, academic_year=self.next_year).count(), 1)

    def test_simultaneous_attendance_correction_requests_leave_one_pending_proposal(self):
        _, enrollment = self.student_enrollment()
        from learning.services import create_attendance
        session = create_attendance(self.admin, self.section, timezone.localdate(), {str(enrollment.pk): AttendanceRecord.Status.PRESENT})
        record = session.records.get(enrollment=enrollment)
        results = self.run_together(*[
            lambda: request_attendance_correction(self.admin, record.pk, new_status=AttendanceRecord.Status.ABSENT,
                                                  reason="Recorded incorrectly")
            for _ in range(2)
        ])
        self.assertEqual(sum(not isinstance(result, Exception) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ValidationError) for result in results), 1)
        self.assertEqual(record.correction_requests.filter(status="pending").count(), 1)

    def test_correction_review_and_new_request_use_one_lock_order(self):
        _, enrollment = self.student_enrollment()
        from learning.services import create_attendance
        session = create_attendance(self.admin, self.section, timezone.localdate(), {str(enrollment.pk): AttendanceRecord.Status.PRESENT})
        record = session.records.get(enrollment=enrollment)
        pending = request_attendance_correction(
            self.admin, record.pk, new_status=AttendanceRecord.Status.ABSENT, reason="First correction"
        )
        results = self.run_together(
            lambda: review_attendance_correction(self.admin, pending.pk, approve=True),
            lambda: request_attendance_correction(self.admin, record.pk, new_status=AttendanceRecord.Status.LATE,
                                                  reason="Second correction"),
        )
        self.assertTrue(all(not isinstance(result, Exception) for result in results), results)
        self.assertEqual(record.correction_requests.filter(status="approved").count(), 1)
        self.assertEqual(record.correction_requests.filter(status="pending").count(), 1)

    def test_shared_teacher_cannot_be_booked_simultaneously_across_schools(self):
        results = self.run_together(
            lambda: create_timetable_slot(self.admin, assignment=self.assignment, weekday=1,
                                          starts_at=time(9), ends_at=time(10)),
            lambda: create_timetable_slot(self.admin_b, assignment=self.assignment_b, weekday=1,
                                          starts_at=time(9), ends_at=time(10)),
        )
        self.assertEqual(sum(isinstance(result, TimetableSlot) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ValidationError) for result in results), 1)
        self.assertEqual(TimetableSlot.objects.filter(assignment__user=self.teacher).count(), 1)

    def test_simultaneous_attempt_start_respects_assessment_attempt_limit(self):
        assessment = create_assessment(
            self.admin, section=self.section, subject=self.subject, title="Concurrency exam",
            opens_at=timezone.now() - timedelta(minutes=1), closes_at=timezone.now() + timedelta(hours=1),
            attempt_limit=1,
        )
        question = create_question(self.admin, subject=self.subject, kind="mcq", prompt="2+2?",
                                   max_points="1.00", choices=["4"], correct_answer="4")
        attach_question(self.admin, assessment, question)
        open_assessment(self.admin, assessment)
        _, enrollment = self.student_enrollment(student_user=self.student_user)
        results = self.run_together(*[
            lambda: begin_attempt(assessment, enrollment, self.student_user)
            for _ in range(2)
        ])
        self.assertEqual(sum(not isinstance(result, Exception) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ValidationError) for result in results), 1)
        self.assertEqual(assessment.attempts.filter(enrollment=enrollment).count(), 1)
