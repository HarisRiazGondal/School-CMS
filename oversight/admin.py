from django.contrib import admin

from accounts.models import SchoolMembership
from .models import Notice, NoticeRevision, SchoolSetting, SchoolSettingRevision, TimetableSlot


class SchoolScopedReadOnlyAdmin(admin.ModelAdmin):
    """Read-only admin mirrors portal school scoping; superuser status grants no data access."""

    def school_ids(self, request):
        if not request.user.is_authenticated or not request.user.is_active:
            return []
        return SchoolMembership.objects.filter(
            user=request.user, user__is_active=True, is_active=True,
            school__is_active=True, role=SchoolMembership.Role.SCHOOL_ADMIN,
        ).values_list("school_id", flat=True)

    def has_module_permission(self, request):
        return bool(self.school_ids(request))

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return bool(self.school_ids(request))
        return self.school_id(obj) in self.school_ids(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def school_id(self, obj):
        if hasattr(obj, "school_id"):
            return obj.school_id
        if hasattr(obj, "setting_id"):
            return obj.setting.school_id
        if hasattr(obj, "notice_id"):
            return obj.notice.school_id
        if hasattr(obj, "assignment_id"):
            return obj.assignment.section.school_class.school_id
        return None

    def get_queryset(self, request):
        queryset = admin.ModelAdmin.get_queryset(self, request)
        if any(field.name == "school" for field in self.model._meta.fields):
            return queryset.filter(school_id__in=self.school_ids(request))
        if any(field.name == "assignment" for field in self.model._meta.fields):
            return queryset.filter(assignment__section__school_class__school_id__in=self.school_ids(request))
        return queryset.none()

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


class SchoolSettingRevisionInline(admin.TabularInline):
    model = SchoolSettingRevision
    extra = 0
    can_delete = False
    readonly_fields = ["version", "snapshot", "changed_by", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SchoolSetting)
class SchoolSettingAdmin(SchoolScopedReadOnlyAdmin):
    list_display = ["school", "timezone", "version", "updated_by", "updated_at"]
    inlines = [SchoolSettingRevisionInline]


class NoticeRevisionInline(admin.TabularInline):
    model = NoticeRevision
    extra = 0
    can_delete = False
    readonly_fields = ["snapshot", "changed_by", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Notice)
class NoticeAdmin(SchoolScopedReadOnlyAdmin):
    list_display = ["title", "school", "audience", "section", "is_published", "publish_at", "expires_at"]
    list_filter = ["school", "audience", "is_published"]
    inlines = [NoticeRevisionInline]


@admin.register(TimetableSlot)
class TimetableSlotAdmin(SchoolScopedReadOnlyAdmin):
    list_display = ["assignment", "weekday", "starts_at", "ends_at", "room", "is_active"]
    list_filter = ["weekday", "is_active", "assignment__section__school_class__school"]

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request).filter(
            assignment__section__school_class__school_id__in=self.school_ids(request)
        )
