from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import SchoolMembership, active_school_memberships, has_school_role
from audit.services import record_event
from schools.models import School
from .forms import FeePlanForm, InvoiceIssueForm, PaymentForm, ReversalForm
from .models import FeePlan, Invoice, LedgerEntry, Payment, Receipt
from .services import create_fee_plan, fee_statement, issue_invoice, post_payment, reverse_payment

STAFF_ROLES = (SchoolMembership.Role.ACCOUNTANT, SchoolMembership.Role.SCHOOL_ADMIN)


def _school_for_staff(user, slug):
    school = get_object_or_404(School, slug=slug, is_active=True)
    if not has_school_role(user, school, *STAFF_ROLES):
        raise PermissionDenied
    return school


def _record_view(school, user, action, object_type, object_id, details=None):
    record_event(school=school, actor=user, action=action, object_type=object_type,
                 object_id=str(object_id), details=details or {})


@login_required
@require_http_methods(["GET"])
def finance_home(request):
    if hasattr(request.user, "student_profile"):
        memberships = SchoolMembership.objects.filter(
            user=request.user, school=request.user.student_profile.school,
            role=SchoolMembership.Role.STUDENT, is_active=True, school__is_active=True,
        )
        if not memberships.exists():
            raise PermissionDenied
        return redirect("finance:student-statement")
    memberships = active_school_memberships(request.user).filter(role__in=STAFF_ROLES)
    if not memberships.exists():
        raise PermissionDenied
    return render(request, "finance/home.html", {"memberships": memberships})


@login_required
@require_http_methods(["GET"])
def school_home(request, school_slug):
    school = _school_for_staff(request.user, school_slug)
    invoices = Invoice.objects.filter(school=school).select_related(
        "enrollment__student", "enrollment__academic_year", "fee_plan"
    )[:50]
    plans = FeePlan.objects.filter(school=school).select_related("academic_year", "grade")
    totals = defaultdict(Decimal)
    for currency, amount in LedgerEntry.objects.filter(school=school).values_list("currency", "amount"):
        totals[currency] += amount
    balances = [{"currency": currency, "balance": totals[currency]} for currency in sorted(totals)]
    _record_view(school, request.user, "finance.dashboard_viewed", "finance_dashboard", school.slug,
                 {"invoice_count": Invoice.objects.filter(school=school).count()})
    return render(request, "finance/school_home.html", {
        "school": school, "invoices": invoices, "plans": plans, "balances": balances,
    })


@login_required
@require_http_methods(["GET", "POST"])
def fee_plan_create(request, school_slug):
    school = _school_for_staff(request.user, school_slug)
    form = FeePlanForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        try:
            plan = create_fee_plan(user=request.user, school=school, **form.cleaned_data)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Fee plan created.")
            return redirect("finance:school-home", school_slug=school.slug)
    return render(request, "finance/fee_plan_form.html", {"school": school, "form": form})


@login_required
@require_http_methods(["GET", "POST"])
def invoice_issue(request, school_slug):
    school = _school_for_staff(request.user, school_slug)
    form = InvoiceIssueForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        try:
            invoice = issue_invoice(
                user=request.user, enrollment=form.cleaned_data["enrollment"],
                fee_plan=form.cleaned_data["fee_plan"],
                concession=form.cleaned_data.get("concession") or Decimal("0.00"),
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Invoice issued.")
            return redirect("finance:invoice-detail", invoice_id=invoice.pk)
    return render(request, "finance/invoice_issue_form.html", {"school": school, "form": form})


def _invoice_for_staff(user, invoice_id):
    invoice = get_object_or_404(Invoice.objects.select_related(
        "school", "enrollment__student", "enrollment__academic_year", "enrollment__section__school_class", "fee_plan"
    ), pk=invoice_id)
    if not has_school_role(user, invoice.school, *STAFF_ROLES):
        raise PermissionDenied
    return invoice


def _invoice_for_student(user, invoice_id):
    student = getattr(user, "student_profile", None)
    if not student:
        raise PermissionDenied
    invoice = get_object_or_404(Invoice.objects.select_related("school", "enrollment__student", "enrollment__academic_year", "fee_plan"), pk=invoice_id)
    if invoice.enrollment.student_id != student.pk or not SchoolMembership.objects.filter(
        user=user, school=invoice.school, role=SchoolMembership.Role.STUDENT, is_active=True, school__is_active=True
    ).exists():
        raise PermissionDenied
    return invoice


@login_required
@require_http_methods(["GET"])
def invoice_detail(request, invoice_id):
    student = getattr(request.user, "student_profile", None)
    invoice = _invoice_for_student(request.user, invoice_id) if student else _invoice_for_staff(request.user, invoice_id)
    entries = invoice.entries.select_related("payment", "reversal_of").order_by("created_at", "id")
    payments = list(invoice.payments.select_related("receipt").order_by("posted_at"))
    for payment in payments:
        payment.is_reversed = payment.ledger_entries.filter(kind=LedgerEntry.Kind.PAYMENT, reversal_entry__isnull=False).exists()
    _record_view(invoice.school, request.user, "finance.invoice_viewed", "invoice", invoice.pk)
    return render(request, "finance/invoice_detail.html", {
        "invoice": invoice, "entries": entries, "payments": payments,
        "can_manage": has_school_role(request.user, invoice.school, *STAFF_ROLES),
    })


@login_required
@require_http_methods(["GET", "POST"])
def payment_post(request, invoice_id):
    invoice = _invoice_for_staff(request.user, invoice_id)
    form = PaymentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            payment = post_payment(user=request.user, invoice=invoice, **form.cleaned_data, currency=invoice.currency)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Payment posted and receipt issued.")
            return redirect("finance:receipt-detail", receipt_id=payment.receipt.pk)
    return render(request, "finance/payment_form.html", {"invoice": invoice, "form": form})


@login_required
@require_http_methods(["GET", "POST"])
def payment_reverse(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("school", "invoice__enrollment__student", "invoice__fee_plan", "receipt"), pk=payment_id)
    if not has_school_role(request.user, payment.school, *STAFF_ROLES):
        raise PermissionDenied
    form = ReversalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            reverse_payment(user=request.user, payment=payment,
                            idempotency_key=form.cleaned_data["idempotency_key"],
                            reason=form.cleaned_data["reason"])
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Payment reversal posted to the ledger.")
            return redirect("finance:invoice-detail", invoice_id=payment.invoice_id)
    return render(request, "finance/reversal_form.html", {"payment": payment, "form": form})


@login_required
@require_http_methods(["GET"])
def student_statement(request):
    student = getattr(request.user, "student_profile", None)
    if student is None or not SchoolMembership.objects.filter(
        user=request.user, school=student.school, role=SchoolMembership.Role.STUDENT,
        is_active=True, school__is_active=True,
    ).exists():
        raise PermissionDenied
    invoices = fee_statement(user=request.user, student=student)
    _record_view(student.school, request.user, "finance.statement_viewed", "student_finance_statement", student.student_code,
                 {"invoice_count": invoices.count()})
    return render(request, "finance/student_statement.html", {"student": student, "invoices": invoices})


@login_required
@require_http_methods(["GET"])
def receipt_detail(request, receipt_id):
    receipt = get_object_or_404(Receipt.objects.select_related(
        "payment__invoice__school", "payment__invoice__enrollment__student", "payment__invoice__enrollment__academic_year",
        "payment__invoice__fee_plan",
    ), pk=receipt_id)
    invoice = receipt.payment.invoice
    student = getattr(request.user, "student_profile", None)
    staff_access = has_school_role(request.user, invoice.school, *STAFF_ROLES)
    student_access = bool(student and student.pk == invoice.enrollment.student_id and SchoolMembership.objects.filter(
        user=request.user, school=invoice.school, role=SchoolMembership.Role.STUDENT, is_active=True, school__is_active=True
    ).exists())
    if not (staff_access or student_access):
        raise PermissionDenied
    _record_view(invoice.school, request.user, "finance.receipt_viewed", "receipt", receipt.receipt_code)
    return render(request, "finance/receipt_detail.html", {"receipt": receipt, "payment": receipt.payment, "invoice": invoice})
