from datetime import date
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section
from finance.models import FeePlan, Invoice, LedgerEntry, Payment, Receipt
from finance.services import create_fee_plan, issue_invoice, post_payment
from schools.models import AcademicYear, School
from students.services import commit_promotion, register_student


class FinanceHTTPWorkflowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north")
        self.other_school = School.objects.create(name="South School", slug="south")
        self.year = AcademicYear.objects.create(school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31), is_active=True)
        self.other_year = AcademicYear.objects.create(school=self.other_school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31), is_active=True)
        self.grade = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.other_grade = SchoolClass.objects.create(school=self.other_school, name="Class 4")
        self.section = Section.objects.create(school_class=self.grade, academic_year=self.year, name="A")
        self.other_section = Section.objects.create(school_class=self.other_grade, academic_year=self.other_year, name="A")
        self.accountant = User.objects.create_user(username="accountant", email="accountant@example.com", password="secret-test-pass")
        self.admin = User.objects.create_user(username="admin", email="admin@example.com", password="secret-test-pass")
        self.other_accountant = User.objects.create_user(username="otheraccountant", email="otheraccountant@example.com", password="secret-test-pass")
        self.other_admin = User.objects.create_user(username="otheradmin", email="otheradmin@example.com", password="secret-test-pass")
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="secret-test-pass")
        self.student_user = User.objects.create_user(username="student", email="student@example.com", password="secret-test-pass")
        self.other_student_user = User.objects.create_user(username="otherstudent", email="otherstudent@example.com", password="secret-test-pass")
        SchoolMembership.objects.create(user=self.accountant, school=self.school, role=SchoolMembership.Role.ACCOUNTANT)
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.other_accountant, school=self.other_school, role=SchoolMembership.Role.ACCOUNTANT)
        SchoolMembership.objects.create(user=self.other_admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        SchoolMembership.objects.create(user=self.other_student_user, school=self.other_school, role=SchoolMembership.Role.STUDENT)
        self.student, self.enrollment = register_student(
            user=self.admin, school=self.school, first_name="Ada", last_name="Learner",
            academic_year=self.year, section=self.section, roll_number="4A-01", student_user=self.student_user,
        )
        self.other_student, self.other_enrollment = register_student(
            user=self.other_admin, school=self.other_school, first_name="Sam", last_name="Elsewhere",
            academic_year=self.other_year, section=self.other_section, roll_number="4A-01", student_user=self.other_student_user,
        )
        self.plan = create_fee_plan(user=self.accountant, school=self.school, academic_year=self.year,
                                    grade=self.grade, name="Tuition", amount=Decimal("100.00"), currency="PKR")
        self.invoice = issue_invoice(user=self.accountant, enrollment=self.enrollment, fee_plan=self.plan,
                                     concession=Decimal("10.00"))
        self.other_plan = create_fee_plan(user=self.other_accountant, school=self.other_school, academic_year=self.other_year,
                                          grade=self.other_grade, name="Other fee", amount=Decimal("50.00"), currency="PKR")
        self.other_invoice = issue_invoice(user=self.other_accountant, enrollment=self.other_enrollment, fee_plan=self.other_plan)
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)

    def test_fee_plan_invoice_partial_full_payment_receipt_reversal_and_reconciliation(self):
        self._login(self.accountant)
        url = reverse("finance:school-home", args=[self.school.slug])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(url), "Tuition")

        plan_form = reverse("finance:plan-create", args=[self.school.slug])
        self.assertEqual(self.client.get(plan_form).status_code, 200)
        response = self.client.post(plan_form, {
            "academic_year": self.year.pk, "grade": self.grade.pk, "name": "Lab fee",
            "amount": "25.00", "currency": "PKR",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(FeePlan.objects.filter(school=self.school, name="Lab fee", amount=Decimal("25.00")).exists())

        issue_url = reverse("finance:invoice-issue", args=[self.school.slug])
        response = self.client.post(issue_url, {
            "enrollment": self.enrollment.pk, "fee_plan": FeePlan.objects.get(school=self.school, name="Lab fee").pk, "concession": "10.00",
        })
        self.assertEqual(response.status_code, 302)
        workflow_plan = FeePlan.objects.get(school=self.school, name="Lab fee")
        workflow_invoice = Invoice.objects.get(enrollment=self.enrollment, fee_plan=workflow_plan)
        self.assertEqual(workflow_invoice.balance, Decimal("15.00"))

        payment_url = reverse("finance:payment-post", args=[workflow_invoice.pk])
        self.assertEqual(self.client.get(payment_url).status_code, 200)
        response = self.client.post(payment_url, {"amount": "5.00", "idempotency_key": "partial-1"})
        self.assertEqual(response.status_code, 302)
        partial = Payment.objects.get(invoice=workflow_invoice, amount=Decimal("5.00"))
        self.assertTrue(Receipt.objects.filter(payment=partial).exists())
        self.assertEqual(workflow_invoice.balance, Decimal("10.00"))
        response = self.client.post(payment_url, {"amount": "10.00", "idempotency_key": "full-1"})
        self.assertEqual(response.status_code, 302)
        full = Payment.objects.get(invoice=workflow_invoice, amount=Decimal("10.00"))
        workflow_invoice.refresh_from_db()
        self.assertEqual(workflow_invoice.balance, Decimal("0.00"))
        self.assertEqual(response.url, reverse("finance:receipt-detail", args=[full.receipt.pk]))
        receipt_page = self.client.get(response.url)
        self.assertEqual(receipt_page.status_code, 200)
        self.assertContains(receipt_page, full.receipt.receipt_code)
        self.assertContains(receipt_page, self.student.student_code)
        self.assertNotContains(receipt_page, "Sam")

        reverse_url = reverse("finance:payment-reverse", args=[full.pk])
        self.assertEqual(self.client.get(reverse_url).status_code, 200)
        response = self.client.post(reverse_url, {
            "reason": "Duplicate full payment entry", "confirm": "on", "idempotency_key": "reverse-full-1",
        })
        self.assertEqual(response.status_code, 302)
        workflow_invoice.refresh_from_db()
        self.assertEqual(workflow_invoice.balance, Decimal("10.00"))
        reversal = LedgerEntry.objects.get(payment=full, kind=LedgerEntry.Kind.REVERSAL)
        self.assertEqual(reversal.reason, "Duplicate full payment entry")
        # The school summary is a ledger reconciliation and therefore includes the reversal.
        dashboard = self.client.get(url)
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "100.00 PKR")
        self.assertEqual(sum(LedgerEntry.objects.filter(school=self.school).values_list("amount", flat=True), Decimal("0.00")), Decimal("100.00"))

    def test_student_statement_and_receipt_are_own_only_and_historical_records_are_listed(self):
        payment = post_payment(user=self.accountant, invoice=self.invoice, amount="20.00", currency="PKR", idempotency_key="own-receipt")
        next_year = AcademicYear.objects.create(school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31))
        next_section = Section.objects.create(school_class=self.grade, academic_year=next_year, name="A")
        _, next_enrollment = commit_promotion(user=self.admin, source=self.enrollment, outcome="promoted",
                                              target_section=next_section, target_year=next_year, roll_number="5A-01")
        next_plan = create_fee_plan(user=self.accountant, school=self.school, academic_year=next_year,
                                    grade=self.grade, name="Next year fee", amount="80.00", currency="PKR")
        next_invoice = issue_invoice(user=self.accountant, enrollment=next_enrollment, fee_plan=next_plan)
        statement_url = reverse("finance:student-statement")
        self._login(self.student_user)
        response = self.client.get(statement_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.invoice.fee_plan.name)
        self.assertContains(response, payment.receipt.receipt_code)
        self.assertContains(response, "Next year fee")
        self.assertContains(response, "2027-28")
        self.assertContains(response, self.student.student_code)
        self.assertNotContains(response, "Sam")
        self.assertEqual(self.client.get(reverse("finance:invoice-detail", args=[self.invoice.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("finance:invoice-detail", args=[next_invoice.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("finance:receipt-detail", args=[payment.receipt.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("finance:invoice-detail", args=[self.other_invoice.pk])).status_code, 403)
        other_payment = post_payment(user=self.other_accountant, invoice=self.other_invoice, amount="5.00", currency="PKR", idempotency_key="other-school-receipt")
        self.assertEqual(self.client.get(reverse("finance:receipt-detail", args=[other_payment.receipt.pk])).status_code, 403)
        self._login(self.other_student_user)
        self.assertEqual(self.client.get(reverse("finance:receipt-detail", args=[other_payment.receipt.pk])).status_code, 200)

    def test_teacher_and_cross_school_staff_cannot_read_or_mutate_finance(self):
        self._login(self.teacher)
        for name, args in [
            ("finance:school-home", [self.school.slug]),
            ("finance:plan-create", [self.school.slug]),
            ("finance:invoice-issue", [self.school.slug]),
            ("finance:invoice-detail", [self.invoice.pk]),
            ("finance:payment-post", [self.invoice.pk]),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)
        self._login(self.accountant)
        self.assertEqual(self.client.get(reverse("finance:school-home", args=[self.other_school.slug])).status_code, 403)
        self.assertEqual(self.client.get(reverse("finance:invoice-detail", args=[self.other_invoice.pk])).status_code, 403)
        other_payment = post_payment(user=self.other_accountant, invoice=self.other_invoice, amount="5.00", currency="PKR", idempotency_key="other-school-receipt")
        self.assertEqual(self.client.get(reverse("finance:receipt-detail", args=[other_payment.receipt.pk])).status_code, 403)
        self._login(self.other_student_user)
        self.assertEqual(self.client.get(reverse("finance:receipt-detail", args=[other_payment.receipt.pk])).status_code, 200)

    def test_student_cannot_select_someone_else_or_post_financial_changes(self):
        self._login(self.student_user)
        self.assertEqual(self.client.get(reverse("finance:home")).status_code, 302)
        self.assertEqual(self.client.get(reverse("finance:school-home", args=[self.school.slug])).status_code, 403)
        self.assertEqual(self.client.post(reverse("finance:payment-post", args=[self.invoice.pk]), {
            "amount": "1.00", "idempotency_key": "student-attempt",
        }).status_code, 403)
        outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="secret-test-pass")
        self._login(outsider)
        self.assertEqual(self.client.get(reverse("finance:student-statement")).status_code, 403)
        self.assertEqual(self.client.get(reverse("finance:invoice-detail", args=[self.invoice.pk])).status_code, 403)

    def test_finance_mutations_require_post_and_csrf_and_form_choices_are_school_scoped(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.accountant)
        payment_url = reverse("finance:payment-post", args=[self.invoice.pk])
        before = Payment.objects.count()
        self.assertEqual(client.get(payment_url).status_code, 200)
        self.assertEqual(Payment.objects.count(), before)
        self.assertEqual(client.post(payment_url, {"amount": "1.00", "idempotency_key": "no-csrf"}).status_code, 403)
        self.assertEqual(Payment.objects.count(), before)
        token = client.cookies["csrftoken"].value
        response = client.post(payment_url, {
            "amount": "1.00", "idempotency_key": "csrf-payment", "csrfmiddlewaretoken": token,
        })
        self.assertEqual(response.status_code, 302)
        issue_url = reverse("finance:invoice-issue", args=[self.school.slug])
        response = client.post(issue_url, {
            "enrollment": self.other_enrollment.pk, "fee_plan": self.other_plan.pk,
            "concession": "0.00", "csrfmiddlewaretoken": token,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.filter(school=self.other_school).count(), 1)

