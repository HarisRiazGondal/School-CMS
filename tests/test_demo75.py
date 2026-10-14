from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from academics.models import SchoolClass, Section, Subject, Term
from accounts.models import SchoolMembership, User
from assessment.models import Answer, Assessment, Attempt, Question
from assessment.services import begin_attempt, save_answer, submit_attempt
from finance.models import FeePlan, Invoice, Payment, Receipt
from finance.services import post_payment
from learning.models import Assignment, TeacherAssignment
from schools.models import AcademicYear, Campus, School
from students.models import Enrollment, Student


@override_settings(DEBUG=True)
class DemoSeedCommandTests(TestCase):
    password = "synthetic-demo-password"

    def seed(self):
        call_command("seed_demo", password=self.password, verbosity=0)

    def test_repeat_seed_preserves_attempt_and_paid_invoice_history(self):
        self.seed()

        school = School.objects.get(slug="demo-school")
        student_user = User.objects.get(username="demo-student")
        accountant = User.objects.get(username="demo-accountant")
        self.assertTrue(SchoolMembership.objects.filter(
            user=accountant, school=school, role=SchoolMembership.Role.ACCOUNTANT, is_active=True,
        ).exists())

        assessment = Assessment.objects.get(school=school, title="Fractions mastery check")
        self.assertEqual(assessment.status, Assessment.Status.OPEN)
        self.assertEqual(assessment.questions.count(), 3)
        self.assertSetEqual(
            set(assessment.questions.values_list("kind", flat=True)),
            {Question.Kind.MCQ, Question.Kind.TRUE_FALSE, Question.Kind.MANUAL},
        )
        self.assertFalse(assessment.attempts.exists())

        invoice = Invoice.objects.get(school=school, fee_plan__name="Demo annual fee")
        self.assertEqual(invoice.balance, invoice.fee_plan.amount)
        self.assertFalse(invoice.payments.exists())
        def fixture_counts():
            return (
                School.objects.filter(pk=school.pk).count(),
                Campus.objects.filter(school=school).count(),
                AcademicYear.objects.filter(school=school).count(),
                Term.objects.filter(academic_year__school=school).count(),
                SchoolClass.objects.filter(school=school).count(),
                Section.objects.filter(school_class__school=school).count(),
                Subject.objects.filter(school=school).count(),
                SchoolMembership.objects.filter(school=school).count(),
                Student.objects.filter(school=school).count(),
                Enrollment.objects.filter(student__school=school).count(),
                TeacherAssignment.objects.filter(section__school_class__school=school).count(),
                Assignment.objects.filter(section__school_class__school=school).count(),
                Assessment.objects.filter(school=school).count(),
                assessment.questions.count(),
                FeePlan.objects.filter(school=school).count(),
                Invoice.objects.filter(school=school).count(),
            )

        original_counts = fixture_counts()

        # A normal rerun keeps the open assessment and unpaid posted invoice as-is.
        self.seed()
        self.assertEqual(fixture_counts(), original_counts)

        enrollment = Enrollment.objects.get(student__user=student_user, academic_year=assessment.academic_year)
        attempt = begin_attempt(assessment, enrollment, student_user)
        manual_question = assessment.questions.get(kind=Question.Kind.MANUAL)
        save_answer(attempt, manual_question, "Use a common denominator.", student_user)
        attempt = submit_attempt(attempt, student_user)
        payment = post_payment(
            user=accountant, invoice=invoice, amount=invoice.balance, currency=invoice.currency,
            idempotency_key="demo-acceptance-payment",
        )
        original_answer = Answer.objects.get(attempt=attempt, question=manual_question)
        history_snapshot = {
            "attempt_id": attempt.pk,
            "attempt_status": attempt.status,
            "response": original_answer.response,
            "payment_id": payment.pk,
            "receipt_id": payment.receipt.pk,
            "receipt_code": payment.receipt.receipt_code,
            "balance": invoice.balance,
            "counts": (
                Attempt.objects.filter(assessment=assessment).count(),
                Answer.objects.filter(attempt__assessment=assessment).count(),
                Payment.objects.filter(invoice=invoice).count(),
                Receipt.objects.filter(payment__invoice=invoice).count(),
            ),
        }

        self.seed()
        self.assertEqual(fixture_counts(), original_counts)
        attempt.refresh_from_db()
        invoice.refresh_from_db()
        answer = Answer.objects.get(attempt=attempt, question=manual_question)
        self.assertEqual(attempt.pk, history_snapshot["attempt_id"])
        self.assertEqual(attempt.status, history_snapshot["attempt_status"])
        self.assertEqual(answer.response, history_snapshot["response"])
        self.assertEqual(invoice.balance, history_snapshot["balance"])
        self.assertEqual(invoice.payments.get().pk, history_snapshot["payment_id"])
        self.assertEqual(invoice.payments.get().receipt.pk, history_snapshot["receipt_id"])
        self.assertEqual(invoice.payments.get().receipt.receipt_code, history_snapshot["receipt_code"])
        self.assertEqual(history_snapshot["counts"], (
            Attempt.objects.filter(assessment=assessment).count(),
            Answer.objects.filter(attempt__assessment=assessment).count(),
            Payment.objects.filter(invoice=invoice).count(),
            Receipt.objects.filter(payment__invoice=invoice).count(),
        ))

    @override_settings(DEBUG=False)
    def test_seed_refuses_non_debug_settings(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", password=self.password, verbosity=0)
