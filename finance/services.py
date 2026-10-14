from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from accounts.models import SchoolMembership, has_school_role
from audit.services import record_event
from schools.models import AcademicYear, School
from students.models import Enrollment, Student
from .models import (
    FINANCE_WRITE_TOKEN, FeePlan, Invoice, LedgerEntry, Payment, Receipt,
    validate_amount, validate_currency,
)


FINANCE_ROLES = (SchoolMembership.Role.ACCOUNTANT, SchoolMembership.Role.SCHOOL_ADMIN)


def _require_staff(user, school):
    if not has_school_role(user, school, *FINANCE_ROLES):
        raise PermissionDenied("An active accountant or school admin membership is required for this school's finance records.")


def _get_invoice(invoice):
    return Invoice.objects.select_related("school", "enrollment__student", "fee_plan").get(pk=getattr(invoice, "pk", invoice))


def _get_payment(payment):
    return Payment.objects.select_related("school", "invoice__enrollment__student").get(pk=getattr(payment, "pk", payment))


def _require_invoice_read(user, invoice):
    if has_school_role(user, invoice.school, *FINANCE_ROLES):
        return
    student = invoice.enrollment.student
    if (user.is_authenticated and user.is_active and student.user_id == user.pk
            and SchoolMembership.objects.filter(user=user, school=invoice.school, role=SchoolMembership.Role.STUDENT,
                                                 is_active=True, school__is_active=True).exists()):
        return
    raise PermissionDenied("You do not have access to this invoice.")


@transaction.atomic
def create_fee_plan(*, user, school, academic_year, amount, currency="PKR", grade=None, name="School fee"):
    school = School.objects.get(pk=getattr(school, "pk", school), is_active=True)
    _require_staff(user, school)
    year = AcademicYear.objects.get(pk=getattr(academic_year, "pk", academic_year))
    if year.school_id != school.pk:
        raise ValidationError("Academic year must belong to the selected school.")
    grade_obj = None
    if grade not in (None, ""):
        from academics.models import SchoolClass
        grade_obj = SchoolClass.objects.get(pk=getattr(grade, "pk", grade))
        if grade_obj.school_id != school.pk:
            raise ValidationError("Grade must belong to the selected school.")
    amount = validate_amount(amount)
    validate_currency(currency)
    plan = FeePlan(school=school, academic_year=year, grade=grade_obj, name=name.strip(), amount=amount, currency=currency)
    plan.save()
    record_event(school=school, actor=user, action="finance.fee_plan_created", object_type="fee_plan",
                 object_id=str(plan.pk), details={"academic_year": year.name, "currency": currency})
    return plan


@transaction.atomic
def issue_invoice(*, user, enrollment, fee_plan, concession="0.00"):
    enrollment = Enrollment.objects.select_related("student__school", "academic_year", "section__school_class").get(
        pk=getattr(enrollment, "pk", enrollment))
    school = School.objects.get(pk=enrollment.student.school_id, is_active=True)
    _require_staff(user, school)
    plan = FeePlan.objects.select_related("academic_year", "grade").get(pk=getattr(fee_plan, "pk", fee_plan))
    if plan.school_id != school.pk or plan.academic_year_id != enrollment.academic_year_id:
        raise ValidationError("Fee plan must belong to the enrollment's school and academic year.")
    if plan.grade_id and plan.grade_id != enrollment.section.school_class_id:
        raise ValidationError("Fee plan grade must match the enrollment grade.")
    credit = validate_amount(concession, allow_zero=True)
    if credit >= plan.amount:
        raise ValidationError("Concession must be less than the fee plan amount.")
    if Invoice.objects.filter(enrollment=enrollment, fee_plan=plan).exists():
        raise ValidationError("An invoice has already been issued for this enrollment and fee plan.")
    try:
        with transaction.atomic():
            invoice = Invoice(school=school, enrollment=enrollment, fee_plan=plan, currency=plan.currency)
            invoice.save(_finance_token=FINANCE_WRITE_TOKEN)
            LedgerEntry(school=school, invoice=invoice, kind=LedgerEntry.Kind.CHARGE, amount=plan.amount,
                        currency=plan.currency, idempotency_key=f"invoice:{invoice.pk}:charge").save(_finance_token=FINANCE_WRITE_TOKEN)
            if credit:
                LedgerEntry(school=school, invoice=invoice, kind=LedgerEntry.Kind.CONCESSION, amount=-credit,
                            currency=plan.currency, idempotency_key=f"invoice:{invoice.pk}:concession").save(_finance_token=FINANCE_WRITE_TOKEN)
    except IntegrityError as exc:
        raise ValidationError("An invoice has already been issued for this enrollment and fee plan.") from exc
    record_event(school=school, actor=user, action="finance.invoice_issued", object_type="invoice",
                 object_id=str(invoice.pk), details={"student_code": enrollment.student.student_code,
                 "academic_year": enrollment.academic_year.name, "currency": plan.currency})
    return invoice


@transaction.atomic
def post_payment(*, user, invoice, amount, currency, idempotency_key):
    invoice = Invoice.objects.select_for_update().select_related("school", "enrollment__student").get(pk=getattr(invoice, "pk", invoice))
    _require_staff(user, invoice.school)
    amount = validate_amount(amount)
    validate_currency(currency)
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 100:
        raise ValidationError("An idempotency key between 1 and 100 characters is required.")
    if currency != invoice.currency:
        raise ValidationError("Payment currency must match the invoice currency.")
    existing = Payment.objects.filter(school=invoice.school, idempotency_key=key).select_related("invoice").first()
    if existing:
        if existing.invoice_id != invoice.pk or existing.amount != amount or existing.currency != currency:
            raise ValidationError("This idempotency key was already used with different payment parameters.")
        return existing
    if amount > invoice.balance:
        raise ValidationError("Payment exceeds the invoice's outstanding balance.")
    try:
        with transaction.atomic():
            payment = Payment(school=invoice.school, invoice=invoice, amount=amount, currency=currency, idempotency_key=key)
            payment.save(_finance_token=FINANCE_WRITE_TOKEN)
            Receipt(payment=payment, receipt_code="").save(_finance_token=FINANCE_WRITE_TOKEN)
            LedgerEntry(school=invoice.school, invoice=invoice, kind=LedgerEntry.Kind.PAYMENT, amount=-amount,
                        currency=currency, payment=payment, idempotency_key=key).save(_finance_token=FINANCE_WRITE_TOKEN)
    except IntegrityError:
        # A concurrent retry can win the unique key after our initial lookup.
        existing = Payment.objects.filter(school=invoice.school, idempotency_key=key).first()
        if existing and existing.invoice_id == invoice.pk and existing.amount == amount and existing.currency == currency:
            return existing
        raise ValidationError("This idempotency key conflicts with another payment.")
    record_event(school=invoice.school, actor=user, action="finance.payment_posted", object_type="payment",
                 object_id=str(payment.pk), details={"invoice": str(invoice.pk), "amount": format(amount, ".2f"),
                 "currency": currency, "receipt_code": payment.receipt.receipt_code})
    return payment


@transaction.atomic
def reverse_payment(*, user, payment, idempotency_key, reason):
    payment = Payment.objects.select_for_update().select_related("school", "invoice__enrollment__student").get(pk=getattr(payment, "pk", payment))
    _require_staff(user, payment.school)
    key = str(idempotency_key or "").strip()
    if not key or len(key) > 100:
        raise ValidationError("An idempotency key between 1 and 100 characters is required.")
    reason = str(reason or "").strip()
    if not reason or len(reason) > 240:
        raise ValidationError("A reversal reason between 1 and 240 characters is required.")
    previous = LedgerEntry.objects.filter(school=payment.school, kind=LedgerEntry.Kind.REVERSAL, idempotency_key=key).first()
    if previous:
        if previous.payment_id == payment.pk:
            if previous.reason != reason:
                raise ValidationError("This reversal key was already used with a different reason.")
            return previous
        raise ValidationError("This reversal key was already used for another transaction.")
    payment_entry = LedgerEntry.objects.select_for_update().filter(payment=payment, kind=LedgerEntry.Kind.PAYMENT).first()
    if not payment_entry:
        raise ValidationError("The payment has no posted ledger entry to reverse.")
    if LedgerEntry.objects.filter(reversal_of=payment_entry).exists():
        raise ValidationError("This payment has already been reversed.")
    reversal = LedgerEntry(school=payment.school, invoice=payment.invoice, kind=LedgerEntry.Kind.REVERSAL,
                           amount=-payment_entry.amount, currency=payment.currency, payment=payment,
                           reversal_of=payment_entry, idempotency_key=key, reason=reason)
    try:
        with transaction.atomic():
            reversal.save(_finance_token=FINANCE_WRITE_TOKEN)
    except IntegrityError as exc:
        raise ValidationError("This payment has already been reversed or the key is in use.") from exc
    record_event(school=payment.school, actor=user, action="finance.payment_reversed", object_type="payment",
                 object_id=str(payment.pk), details={"invoice": str(payment.invoice_id), "currency": payment.currency,
                 "receipt_code": payment.receipt.receipt_code})
    return reversal


def fee_statement(*, user, student, academic_year=None):
    student = Student.objects.select_related("school", "user").get(pk=getattr(student, "pk", student))
    if has_school_role(user, student.school, *FINANCE_ROLES):
        pass
    elif (user.is_authenticated and user.is_active and student.user_id == user.pk
          and SchoolMembership.objects.filter(user=user, school=student.school, role=SchoolMembership.Role.STUDENT,
                                               is_active=True, school__is_active=True).exists()):
        pass
    else:
        raise PermissionDenied("You may only view your own statement or finance records for your school.")
    invoices = Invoice.objects.filter(enrollment__student=student).select_related("enrollment__academic_year", "fee_plan").prefetch_related("entries", "payments__receipt")
    if academic_year is not None:
        invoices = invoices.filter(enrollment__academic_year_id=getattr(academic_year, "pk", academic_year))
    return invoices.order_by("enrollment__academic_year__starts_on", "issue_date", "id")


def scoped_invoices(*, user, school):
    school = School.objects.get(pk=getattr(school, "pk", school), is_active=True)
    _require_staff(user, school)
    return Invoice.objects.filter(school=school).select_related("enrollment__student", "enrollment__academic_year", "fee_plan")


def scoped_payments(*, user, school):
    school = School.objects.get(pk=getattr(school, "pk", school), is_active=True)
    _require_staff(user, school)
    return Payment.objects.filter(school=school).select_related("invoice", "receipt")


def scoped_ledger(*, user, school, academic_year=None):
    school = School.objects.get(pk=getattr(school, "pk", school), is_active=True)
    _require_staff(user, school)
    entries = LedgerEntry.objects.filter(school=school).select_related("invoice", "payment")
    if academic_year is not None:
        entries = entries.filter(invoice__enrollment__academic_year_id=getattr(academic_year, "pk", academic_year))
    return entries


def authorize_invoice_read(*, user, invoice):
    invoice = _get_invoice(invoice)
    _require_invoice_read(user, invoice)
    return invoice


def authorize_receipt_read(*, user, receipt):
    receipt = Receipt.objects.select_related("payment__school", "payment__invoice__enrollment__student").get(pk=getattr(receipt, "pk", receipt))
    _require_invoice_read(user, receipt.payment.invoice)
    return receipt
