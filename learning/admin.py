from django.contrib import admin

from accounts.models import SchoolMembership
from .models import Assignment, AttendanceSession, TeacherAssignment


class SchoolScopedReadOnlyAdmin(admin.ModelAdmin):
    """Admin lists are limited to active school-admin memberships, including superusers."""

    def school_ids(self, request):
        return SchoolMembership.objects.filter(
            user=request.user, user__is_active=True, is_active=True,
            role=SchoolMembership.Role.SCHOOL_ADMIN, school__is_active=True,
        ).values_list("school_id", flat=True)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(self.school_filter(self.school_ids(request)))

    def school_filter(self, ids):
        raise NotImplementedError

    def has_module_permission(self, request):
        return self.school_ids(request).exists()

    def has_view_permission(self, request, obj=None):
        if not self.school_ids(request).exists():
            return False
        return obj is None or self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(SchoolScopedReadOnlyAdmin):
    list_display = ("user", "section", "subject", "is_active")
    list_filter = ("is_active", "section__academic_year")
    search_fields = ("user__username", "user__email", "section__name", "subject__name")

    def school_filter(self, ids):
        return {"section__school_class__school_id__in": ids}


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(SchoolScopedReadOnlyAdmin):
    list_display = ("section", "date", "created_by", "created_at")
    list_filter = ("date", "section__academic_year")

    def school_filter(self, ids):
        return {"section__school_class__school_id__in": ids}


@admin.register(Assignment)
class AssignmentAdmin(SchoolScopedReadOnlyAdmin):
    list_display = ("title", "section", "subject", "teacher", "due_at", "is_published")
    list_filter = ("is_published", "section__academic_year", "subject")
    search_fields = ("title", "instructions")

    def school_filter(self, ids):
        return {"section__school_class__school_id__in": ids}


