from django.contrib import admin
from accounts.models import SchoolMembership
from audit.services import record_event
from .models import Enrollment, Guardian, GuardianStudentRelation, Student


class SchoolScopedAdmin(admin.ModelAdmin):
    """Admin is school-scoped too; platform superuser status does not bypass this boundary."""
    def school_ids(self, request):
        if not request.user.is_authenticated or not request.user.is_active:
            return []
        return SchoolMembership.objects.filter(
            user=request.user, is_active=True, school__is_active=True,
            role__in=[SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.REGISTRAR],
        ).values_list("school_id", flat=True)

    def has_module_permission(self, request):
        return bool(self.school_ids(request))

    def has_view_permission(self, request, obj=None):
        if obj is not None:
            return obj.school_id in self.school_ids(request)
        return bool(self.school_ids(request))

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _audit_admin_read(self, request, response, *, object_type, object_id=None):
        if response.status_code != 200 or not request.user.is_superuser:
            return response
        if getattr(request, "_student_admin_read_audited", False):
            return response
        request._student_admin_read_audited = True
        school_ids = [object_id] if object_id else list(self.school_ids(request))
        for school_id in school_ids:
            from schools.models import School
            school = School.objects.filter(pk=school_id, is_active=True).first()
            if school:
                record_event(school=school, actor=request.user, action="student.admin_records_viewed",
                             object_type=object_type, object_id=str(school.pk),
                             details={"view": "record" if object_id else "list"})
        return response

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        return self._audit_admin_read(request, response, object_type=self.model._meta.model_name)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        school_id = None
        if response.status_code == 200:
            obj = self.get_queryset(request).filter(pk=object_id).first()
            if obj:
                school_id = getattr(obj, "school_id", None) or obj.student.school_id
        return self._audit_admin_read(request, response, object_type=self.model._meta.model_name, object_id=school_id)


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    can_delete = False
    show_change_link = False
    readonly_fields = ("academic_year", "section", "roll_number", "status", "previous_enrollment", "enrolled_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Student)
class StudentAdmin(SchoolScopedAdmin):
    list_display = ("student_code", "first_name", "last_name", "school")
    list_filter = ("school",)
    search_fields = ("student_code", "first_name", "last_name")
    readonly_fields = ("student_code", "school", "user", "first_name", "last_name", "date_of_birth", "created_at")
    inlines = (EnrollmentInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(school_id__in=self.school_ids(request))

    def has_view_permission(self, request, obj=None):
        if obj is not None:
            return obj.school_id in self.school_ids(request)
        return bool(self.school_ids(request))


@admin.register(Enrollment)
class EnrollmentAdmin(SchoolScopedAdmin):
    list_display = ("student", "academic_year", "section", "roll_number", "status")
    list_filter = ("academic_year", "status")
    search_fields = ("student__student_code", "student__first_name", "roll_number")
    readonly_fields = ("student", "academic_year", "section", "roll_number", "status", "previous_enrollment", "enrolled_at")
    fields = readonly_fields

    def get_queryset(self, request):
        return super().get_queryset(request).filter(student__school_id__in=self.school_ids(request))

    def has_view_permission(self, request, obj=None):
        if obj is not None:
            return obj.student.school_id in self.school_ids(request)
        return bool(self.school_ids(request))


@admin.register(Guardian)
class GuardianAdmin(SchoolScopedAdmin):
    list_display = ("name", "school", "phone", "email")
    readonly_fields = ("school", "name", "phone", "email")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(school_id__in=self.school_ids(request))


@admin.register(GuardianStudentRelation)
class GuardianStudentRelationAdmin(SchoolScopedAdmin):
    list_display = ("guardian", "student", "relationship", "is_primary")
    readonly_fields = ("guardian", "student", "relationship", "is_primary")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(guardian__school_id__in=self.school_ids(request))

    def has_view_permission(self, request, obj=None):
        if obj is not None:
            return obj.guardian.school_id in self.school_ids(request)
        return bool(self.school_ids(request))
