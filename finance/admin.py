from django.contrib import admin

from accounts.models import SchoolMembership
from .models import FeePlan, Invoice, LedgerEntry, Payment, Receipt


class FinanceReadOnlyAdmin(admin.ModelAdmin):
    """Read-only finance maintenance scoped to explicit accountant/admin memberships."""
    def school_ids(self, request):
        if not request.user.is_authenticated or not request.user.is_active:
            return []
        return SchoolMembership.objects.filter(
            user=request.user, is_active=True, school__is_active=True,
            role__in=[SchoolMembership.Role.ACCOUNTANT, SchoolMembership.Role.SCHOOL_ADMIN],
        ).values_list("school_id", flat=True)

    def has_module_permission(self, request):
        return bool(self.school_ids(request))

    def has_view_permission(self, request, obj=None):
        if obj is not None:
            return self.school_id(obj) in self.school_ids(request)
        return bool(self.school_ids(request))

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def school_id(self, obj):
        if hasattr(obj, "school_id"):
            return obj.school_id
        if hasattr(obj, "payment_id"):
            return obj.payment.school_id
        if hasattr(obj, "invoice_id"):
            return obj.invoice.school_id
        return None

    def get_queryset(self, request):
        return super().get_queryset(request).filter(school_id__in=self.school_ids(request))

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(FeePlan)
class FeePlanAdmin(FinanceReadOnlyAdmin):
    list_display = ("name", "school", "academic_year", "grade", "amount", "currency")
    list_filter = ("school", "academic_year", "currency")


@admin.register(Invoice)
class InvoiceAdmin(FinanceReadOnlyAdmin):
    list_display = ("id", "school", "enrollment", "fee_plan", "issue_date", "currency", "balance")
    list_filter = ("school", "currency", "issue_date")


@admin.register(Payment)
class PaymentAdmin(FinanceReadOnlyAdmin):
    list_display = ("id", "school", "invoice", "amount", "currency", "posted_at")
    list_filter = ("school", "currency", "posted_at")


@admin.register(Receipt)
class ReceiptAdmin(FinanceReadOnlyAdmin):
    list_display = ("receipt_code", "payment", "issued_at")

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request).filter(payment__school_id__in=self.school_ids(request))


@admin.register(LedgerEntry)
class LedgerEntryAdmin(FinanceReadOnlyAdmin):
    list_display = ("created_at", "school", "invoice", "kind", "amount", "currency", "payment")
    list_filter = ("school", "kind", "currency", "created_at")

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request).filter(school_id__in=self.school_ids(request))
