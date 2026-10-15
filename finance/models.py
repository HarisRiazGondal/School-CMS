import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


FINANCE_WRITE_TOKEN = object()
MONEY_ZERO = Decimal("0.00")


def validate_currency(value):
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha() or value.upper() != value:
        raise ValidationError("Currency must be a three-letter uppercase code (for example, PKR).")


def validate_amount(value, *, allow_zero=False):
    try:
        amount = Decimal(value)
    except Exception as exc:
        raise ValidationError("Enter a valid finite amount.") from exc
    if not amount.is_finite():
        raise ValidationError("Amount must be finite.")
    if amount.as_tuple().exponent < -2:
        raise ValidationError("Amount may have at most two decimal places.")
    if amount < 0 or (not allow_zero and amount == 0):
        raise ValidationError("Amount must be positive." if not allow_zero else "Amount cannot be negative.")
    try:
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValidationError("Amount is outside the supported precision.") from exc


class ImmutableFinanceQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Posted financial records are immutable; use a compensating transaction.")

    def delete(self):
        raise ValidationError("Posted financial records cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Create posted financial records through finance services.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Posted financial records cannot be bulk-updated.")


class FeePlan(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="fee_plans")
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.PROTECT, related_name="fee_plans")
    grade = models.ForeignKey("academics.SchoolClass", null=True, blank=True, on_delete=models.PROTECT, related_name="fee_plans")
    name = models.CharField(max_length=120, default="School fee")
    currency = models.CharField(max_length=3, default="PKR", validators=[validate_currency])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["academic_year__starts_on", "name"]

    def clean(self):
        super().clean()
        validate_currency(self.currency)
        validate_amount(self.amount)
        errors = {}
        if self.school_id and self.academic_year_id and self.school_id != self.academic_year.school_id:
            errors["academic_year"] = "Fee plan year must belong to the same school."
        if self.grade_id and self.school_id and self.grade.school_id != self.school_id:
            errors["grade"] = "Fee plan grade must belong to the same school."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} / {self.academic_year} / {self.amount} {self.currency}"


class Invoice(models.Model):
    """Immutable posted invoice header; its balance is derived from LedgerEntry rows."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="invoices")
    enrollment = models.ForeignKey("students.Enrollment", on_delete=models.PROTECT, related_name="invoices")
    fee_plan = models.ForeignKey(FeePlan, on_delete=models.PROTECT, related_name="invoices")
    currency = models.CharField(max_length=3, validators=[validate_currency])
    issue_date = models.DateField(auto_now_add=True)
    objects = ImmutableFinanceQuerySet.as_manager()

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["enrollment", "fee_plan"], name="uniq_invoice_enrollment_fee_plan")]

    @property
    def balance(self):
        # SQLite stores DecimalField values as NUMERIC and SUM may pass through binary floats.
        # Sum the individually converted Decimals in Python to keep statements exact locally too.
        return sum(self.entries.values_list("amount", flat=True), MONEY_ZERO)

    @property
    def original_amount(self):
        return sum(
            self.entries.filter(kind__in=[LedgerEntry.Kind.CHARGE, LedgerEntry.Kind.CONCESSION, LedgerEntry.Kind.ADJUSTMENT]).values_list("amount", flat=True),
            MONEY_ZERO,
        )

    def clean(self):
        if self.enrollment_id and self.school_id and self.enrollment.student.school_id != self.school_id:
            raise ValidationError("Invoice enrollment must belong to the invoice school.")
        if self.fee_plan_id and self.school_id and self.fee_plan.school_id != self.school_id:
            raise ValidationError("Invoice plan must belong to the invoice school.")
        if self.enrollment_id and self.fee_plan_id:
            if self.enrollment.academic_year_id != self.fee_plan.academic_year_id:
                raise ValidationError("Fee plan year must match the historical enrollment year.")
            if self.fee_plan.grade_id and self.enrollment.section.school_class_id != self.fee_plan.grade_id:
                raise ValidationError("Fee plan grade must match the enrollment grade.")
        validate_currency(self.currency)

    def save(self, *args, **kwargs):
        token = kwargs.pop("_finance_token", None)
        if token is not FINANCE_WRITE_TOKEN or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Invoices are posted once through finance services and are immutable.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Posted invoices cannot be deleted.")


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="payments")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, validators=[validate_currency])
    idempotency_key = models.CharField(max_length=100)
    posted_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableFinanceQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["school", "idempotency_key"], name="uniq_payment_idempotency_school")]
        ordering = ["-posted_at", "-id"]

    def clean(self):
        super().clean()
        validate_amount(self.amount)
        validate_currency(self.currency)
        if self.invoice_id and self.school_id != self.invoice.school_id:
            raise ValidationError("Payment and invoice must belong to the same school.")
        if self.invoice_id and self.currency != self.invoice.currency:
            raise ValidationError("Payment currency must match the invoice currency.")

    def save(self, *args, **kwargs):
        token = kwargs.pop("_finance_token", None)
        if token is not FINANCE_WRITE_TOKEN or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Payments are immutable and must be posted through finance services.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Payments and their receipts cannot be deleted.")


class Receipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="receipt")
    receipt_code = models.CharField(max_length=40, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableFinanceQuerySet.as_manager()

    def save(self, *args, **kwargs):
        token = kwargs.pop("_finance_token", None)
        if token is not FINANCE_WRITE_TOKEN or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Receipts are issued once by the payment service and are immutable.")
        if not self.receipt_code:
            self.receipt_code = f"R-{uuid.uuid4().hex.upper()}"
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Receipts cannot be deleted.")


class LedgerEntry(models.Model):
    class Kind(models.TextChoices):
        CHARGE = "charge", "Charge"
        PAYMENT = "payment", "Payment"
        CONCESSION = "concession", "Concession"
        ADJUSTMENT = "adjustment", "Adjustment"
        REVERSAL = "reversal", "Payment reversal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="ledger_entries")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Signed amount: charges positive, credits negative.")
    currency = models.CharField(max_length=3, validators=[validate_currency])
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal_entry")
    idempotency_key = models.CharField(max_length=100, blank=True)
    reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableFinanceQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["school", "idempotency_key"], condition=~Q(idempotency_key=""), name="uniq_ledger_key_school"),
            models.CheckConstraint(condition=~Q(amount=0), name="ledger_amount_nonzero"),
        ]

    def clean(self):
        super().clean()
        if self.amount == 0:
            raise ValidationError("Ledger entry must have a nonzero amount.")
        validate_currency(self.currency)
        if self.invoice_id and self.school_id != self.invoice.school_id:
            raise ValidationError("Ledger entry and invoice must belong to the same school.")
        if self.invoice_id and self.currency != self.invoice.currency:
            raise ValidationError("Ledger entry currency must match the invoice currency.")
        if self.payment_id and self.invoice_id:
            if self.payment.invoice_id != self.invoice_id or self.payment.school_id != self.school_id:
                raise ValidationError("Ledger payment must belong to this invoice and school.")
            if self.payment.currency != self.currency:
                raise ValidationError("Ledger payment currency must match its payment.")
        if self.kind in {self.Kind.PAYMENT, self.Kind.REVERSAL} and not self.payment_id:
            raise ValidationError("Payment and reversal ledger entries must reference a payment.")
        if self.kind == self.Kind.REVERSAL and not self.reversal_of_id:
            raise ValidationError("A reversal must link to its original payment ledger entry.")
        if self.reversal_of_id:
            if self.kind != self.Kind.REVERSAL or self.reversal_of.kind != self.Kind.PAYMENT or self.reversal_of.payment_id != self.payment_id:
                raise ValidationError("Reversal must compensate the linked payment ledger entry.")
            if self.reversal_of.invoice_id != self.invoice_id:
                raise ValidationError("Reversal and original payment must belong to the same invoice.")
        if self.kind in {self.Kind.PAYMENT, self.Kind.CONCESSION} and self.amount >= 0:
            raise ValidationError("Payment and concession entries must be negative credits.")
        if self.kind in {self.Kind.CHARGE, self.Kind.REVERSAL} and self.amount <= 0:
            raise ValidationError("Charge and reversal entries must be positive debits.")

    def save(self, *args, **kwargs):
        token = kwargs.pop("_finance_token", None)
        if token is not FINANCE_WRITE_TOKEN or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Ledger entries are append-only and must be created through finance services.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Ledger entries are append-only and cannot be deleted.")
