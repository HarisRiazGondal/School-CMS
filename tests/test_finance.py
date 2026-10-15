from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section
from finance.models import FeePlan, Invoice, LedgerEntry, Payment, Receipt
from finance.services import (
    authorize_invoice_read, authorize_receipt_read, create_fee_plan, fee_statement,
    issue_invoice, post_payment, reverse_payment, scoped_invoices, scoped_ledger,
)
from schools.models import AcademicYear, School
from students.services import register_student


class FinanceLedgerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north-finance")
        self.other_school = School.objects.create(name="South School", slug="south-finance")
        self.admin = User.objects.create_user(username="fin-admin", email="fin-admin@test", password="long-safe-password")
        self.accountant = User.objects.create_user(username="accountant", email="accountant@test", password="long-safe-password")
        self.other_admin = User.objects.create_user(username="other-fin-admin", email="other-fin-admin@test", password="long-safe-password")
        self.teacher = User.objects.create_user(username="fin-teacher", email="fin-teacher@test", password="long-safe-password")
        self.registrar = User.objects.create_user(username="fin-registrar", email="fin-registrar@test", password="long-safe-password")
        self.student_user = User.objects.create_user(username="fee-student", email="fee-student@test", password="long-safe-password")
        for user, school, role in [
            (self.admin, self.school, SchoolMembership.Role.SCHOOL_ADMIN),
            (self.accountant, self.school, SchoolMembership.Role.ACCOUNTANT),
            (self.other_admin, self.other_school, SchoolMembership.Role.SCHOOL_ADMIN),
            (self.teacher, self.school, SchoolMembership.Role.TEACHER),
            (self.registrar, self.school, SchoolMembership.Role.REGISTRAR),
            (self.student_user, self.school, SchoolMembership.Role.STUDENT),
        ]:
            SchoolMembership.objects.create(user=user, school=school, role=role)
        self.grade = SchoolClass.objects.create(school=self.school, name="Grade 3")
        self.other_grade = SchoolClass.objects.create(school=self.other_school, name="Grade 3")
        self.year = AcademicYear.objects.create(school=self.school, name="2025-26", starts_on=date(2025, 8, 1), ends_on=date(2026, 7, 31))
        self.other_year = AcademicYear.objects.create(school=self.other_school, name="2025-26", starts_on=date(2025, 8, 1), ends_on=date(2026, 7, 31))
        self.section = Section.objects.create(school_class=self.grade, academic_year=self.year, name="A")
        self.other_section = Section.objects.create(school_class=self.other_grade, academic_year=self.other_year, name="A")
        self.student, self.enrollment = register_student(
            user=self.admin, school=self.school, first_name="Amina", academic_year=self.year,
            section=self.section, roll_number="03", student_user=self.student_user,
        )
        self.plan = create_fee_plan(user=self.accountant, school=self.school, academic_year=self.year,
                                    grade=self.grade, name="Annual fee", amount="125.50")

    def invoice(self, *, concession="0.00"):
        return issue_invoice(user=self.admin, enrollment=self.enrollment, fee_plan=self.plan, concession=concession)

    def test_decimal_concession_partial_and_full_settlement_reconcile_to_ledger(self):
        invoice = self.invoice(concession="25.50")
        self.assertEqual(invoice.balance, Decimal("100.00"))
        self.assertEqual(invoice.original_amount, Decimal("100.00"))
        first = post_payment(user=self.accountant, invoice=invoice, amount="30.15", currency="PKR", idempotency_key="cash-1")
        self.assertEqual(first.receipt.receipt_code[:2], "R-")
        self.assertEqual(invoice.balance, Decimal("69.85"))
        second = post_payment(user=self.admin, invoice=invoice, amount="69.85", currency="PKR", idempotency_key="cash-2")
        self.assertEqual(invoice.balance, Decimal("0.00"))
        self.assertEqual(invoice.entries.aggregate_total if hasattr(invoice.entries, "aggregate_total") else sum(invoice.entries.values_list("amount", flat=True)), Decimal("0.00"))
        self.assertEqual(second.receipt.payment_id, second.pk)

    def test_one_invoice_per_historical_enrollment_and_plan(self):
        self.invoice()
        with self.assertRaises(ValidationError):
            self.invoice()

    def test_payment_and_reversal_are_idempotent_and_reversal_restores_balance(self):
        invoice = self.invoice()
        payment = post_payment(user=self.accountant, invoice=invoice, amount="40.00", currency="PKR", idempotency_key="deposit-A")
        duplicate = post_payment(user=self.accountant, invoice=invoice, amount=Decimal("40.00"), currency="PKR", idempotency_key="deposit-A")
        self.assertEqual(payment.pk, duplicate.pk)
        self.assertEqual(payment.receipt.pk, duplicate.receipt.pk)
        self.assertEqual(invoice.balance, Decimal("85.50"))
        reversal = reverse_payment(user=self.admin, payment=payment, idempotency_key="undo-A", reason="Duplicate bank transfer")
        self.assertEqual(reversal.amount, Decimal("40.00"))
        self.assertEqual(reversal.reversal_of.payment_id, payment.pk)
        self.assertEqual(invoice.balance, Decimal("125.50"))
        self.assertEqual(reverse_payment(user=self.admin, payment=payment, idempotency_key="undo-A", reason="Duplicate bank transfer").pk, reversal.pk)
        with self.assertRaises(ValidationError):
            reverse_payment(user=self.admin, payment=payment, idempotency_key="undo-A", reason="Different explanation")
        with self.assertRaises(ValidationError):
            reverse_payment(user=self.admin, payment=payment, idempotency_key="undo-B", reason="Try twice")
        self.assertTrue(Receipt.objects.filter(payment=payment).exists())

    def test_reused_payment_key_with_different_parameters_is_rejected(self):
        invoice = self.invoice()
        payment = post_payment(user=self.admin, invoice=invoice, amount="10.00", currency="PKR", idempotency_key="stable")
        for kwargs in [
            {"amount": "11.00", "currency": "PKR"},
            {"amount": "10.00", "currency": "USD"},
        ]:
            with self.assertRaises(ValidationError):
                post_payment(user=self.admin, invoice=invoice, idempotency_key="stable", **kwargs)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(payment.amount, Decimal("10.00"))

    def test_rejects_invalid_amount_currency_overpayment_and_concession(self):
        invoice = self.invoice()
        for value in ["NaN", "Infinity", "1.001", "-1.00", "0.00"]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                post_payment(user=self.admin, invoice=invoice, amount=value, currency="PKR", idempotency_key=f"bad-{value}")
        for currency in ["pkr", "US", "PKR "]:
            with self.subTest(currency=currency), self.assertRaises(ValidationError):
                post_payment(user=self.admin, invoice=invoice, amount="1.00", currency=currency, idempotency_key=f"currency-{currency}")
        with self.assertRaises(ValidationError):
            post_payment(user=self.admin, invoice=invoice, amount="125.51", currency="PKR", idempotency_key="too-much")
        with self.assertRaises(ValidationError):
            issue_invoice(user=self.admin, enrollment=self.enrollment, fee_plan=self.plan, concession="125.50")

    def test_fee_plan_and_invoice_validate_amount_currency_grade_year_and_school(self):
        for amount in ["NaN", "Infinity", "12.345", "0.00", "-1.00"]:
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                create_fee_plan(user=self.admin, school=self.school, academic_year=self.year, amount=amount)
        with self.assertRaises(ValidationError):
            create_fee_plan(user=self.admin, school=self.school, academic_year=self.year, amount="1.00", currency="usd")
        other_plan = create_fee_plan(user=self.other_admin, school=self.other_school, academic_year=self.other_year,
                                     grade=self.other_grade, amount="50.00")
        with self.assertRaises(ValidationError):
            issue_invoice(user=self.admin, enrollment=self.enrollment, fee_plan=other_plan)

    def test_excessive_decimal_magnitude_is_a_validation_error_without_financial_writes(self):
        plan_count = FeePlan.objects.count()
        with self.assertRaises(ValidationError):
            create_fee_plan(user=self.admin, school=self.school, academic_year=self.year, amount="1e999999")
        self.assertEqual(FeePlan.objects.count(), plan_count)

        invoice = self.invoice()
        ledger_before = list(invoice.entries.values_list("kind", "amount", "idempotency_key"))
        with self.assertRaises(ValidationError):
            post_payment(user=self.admin, invoice=invoice, amount="1e999999", currency="PKR",
                         idempotency_key="excessive-magnitude")
        self.assertEqual(list(invoice.entries.values_list("kind", "amount", "idempotency_key")), ledger_before)
        self.assertEqual(Payment.objects.count(), 0)

    def test_role_school_and_student_scope_are_enforced(self):
        invoice = self.invoice()
        for user in (self.teacher, self.registrar, self.other_admin):
            with self.subTest(user=user.username), self.assertRaises(PermissionDenied):
                scoped_invoices(user=user, school=self.school)
            with self.subTest(user=user.username), self.assertRaises(PermissionDenied):
                post_payment(user=user, invoice=invoice, amount="1.00", currency="PKR", idempotency_key=f"denied-{user.pk}")
        self.assertEqual(list(scoped_invoices(user=self.accountant, school=self.school)), [invoice])
        self.assertEqual(scoped_ledger(user=self.admin, school=self.school).count(), 1)
        self.assertEqual(list(fee_statement(user=self.student_user, student=self.student)), [invoice])
        self.assertEqual(authorize_invoice_read(user=self.student_user, invoice=invoice).pk, invoice.pk)
        with self.assertRaises(PermissionDenied):
            fee_statement(user=self.other_admin, student=self.student)
        payment = post_payment(user=self.accountant, invoice=invoice, amount="1.00", currency="PKR", idempotency_key="own-receipt")
        self.assertEqual(authorize_receipt_read(user=self.student_user, receipt=payment.receipt).pk, payment.receipt.pk)

    def test_posted_records_reject_constructed_and_queryset_mutation(self):
        invoice = self.invoice()
        payment = post_payment(user=self.admin, invoice=invoice, amount="10.00", currency="PKR", idempotency_key="immutable")
        entry = payment.ledger_entries.get(kind=LedgerEntry.Kind.PAYMENT)
        with self.assertRaises(ValidationError):
            Invoice(school=self.school, enrollment=self.enrollment, fee_plan=self.plan, currency="PKR").save()
        with self.assertRaises(ValidationError):
            Payment(school=self.school, invoice=invoice, amount="1.00", currency="PKR", idempotency_key="forged").save()
        with self.assertRaises(ValidationError):
            Receipt(payment=payment, receipt_code="fake").save()
        with self.assertRaises(ValidationError):
            LedgerEntry(school=self.school, invoice=invoice, kind=LedgerEntry.Kind.ADJUSTMENT, amount="1.00", currency="PKR").save()
        with self.assertRaises(ValidationError):
            Payment.objects.filter(pk=payment.pk).update(amount=Decimal("9.00"))
        with self.assertRaises(ValidationError):
            Receipt.objects.filter(pk=payment.receipt.pk).delete()
        with self.assertRaises(ValidationError):
            LedgerEntry.objects.filter(pk=entry.pk).delete()
        with self.assertRaises(ValidationError):
            Invoice.objects.filter(pk=invoice.pk).update(currency="USD")
        with self.assertRaises(ValidationError):
            payment.delete()
