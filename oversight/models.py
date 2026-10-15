import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


TERMINOLOGY_KEYS = {"student", "students", "teacher", "teachers", "section", "sections", "class", "classes", "school"}
POLICY_DEFAULTS = {
    "late_submission_allowed": True,
    "attendance_correction_days": 7,
    "student_results_visible": True,
    "notice_expiry_days": 0,
}


class GuardedWriteQuerySet(models.QuerySet):
    """Prevent queryset write shortcuts that bypass model validation and history."""

    error_message = "Use validated model/service writes; queryset mutation is disabled."

    def update(self, **kwargs):
        raise ValidationError(self.error_message)

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(self.error_message)

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError(self.error_message)


class ImmutableHistoryQuerySet(GuardedWriteQuerySet):
    error_message = "Historical revisions are immutable."

    def delete(self):
        raise ValidationError(self.error_message)


def validate_json_object(value, *, max_bytes, field_label):
    if not isinstance(value, dict):
        raise ValidationError(f"{field_label} must be a JSON object.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_label} must contain JSON-compatible values.") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValidationError(f"{field_label} must be no larger than {max_bytes} bytes.")


def validate_timezone_name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Enter a valid IANA timezone name.")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValidationError("Enter a valid IANA timezone name.") from exc


def validate_terminology(value):
    validate_json_object(value, max_bytes=2048, field_label="Terminology")
    unknown = set(value) - TERMINOLOGY_KEYS
    if unknown:
        raise ValidationError(f"Unsupported terminology keys: {', '.join(sorted(unknown))}.")
    for key, term in value.items():
        if not isinstance(term, str) or not term.strip() or len(term) > 40:
            raise ValidationError(f"{key} must be a non-empty term of at most 40 characters.")


def validate_policy_values(value):
    validate_json_object(value, max_bytes=4096, field_label="Policy values")
    unknown = set(value) - set(POLICY_DEFAULTS)
    if unknown:
        raise ValidationError(f"Unsupported policy keys: {', '.join(sorted(unknown))}.")
    for key, setting in value.items():
        if key in {"late_submission_allowed", "student_results_visible"} and not isinstance(setting, bool):
            raise ValidationError(f"{key} must be true or false.")
        if key == "attendance_correction_days" and (type(setting) is not int or not 0 <= setting <= 365):
            raise ValidationError("attendance_correction_days must be an integer from 0 to 365.")
        if key == "notice_expiry_days" and (type(setting) is not int or not 0 <= setting <= 3650):
            raise ValidationError("notice_expiry_days must be an integer from 0 to 3650.")


def validate_report_branding(value):
    validate_json_object(value, max_bytes=4096, field_label="Report branding")
    if set(value) - {"school_name", "logo_url", "primary_color", "secondary_color", "footer"}:
        raise ValidationError("Report branding contains an unsupported key.")
    for key, item in value.items():
        if not isinstance(item, str) or len(item) > 500:
            raise ValidationError(f"{key} must be text of at most 500 characters.")


def snapshot_model(instance, fields):
    result = {}
    for name in fields:
        value = getattr(instance, name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        result[name] = value
    return result


class SchoolSetting(models.Model):
    school = models.OneToOneField("schools.School", on_delete=models.PROTECT, related_name="oversight_settings")
    terminology = models.JSONField(default=dict, blank=True, validators=[validate_terminology])
    contact_name = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_address = models.CharField(max_length=240, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Karachi", validators=[validate_timezone_name])
    report_branding = models.JSONField(default=dict, blank=True, validators=[validate_report_branding])
    policy_values = models.JSONField(default=dict, blank=True, validators=[validate_policy_values])
    version = models.PositiveIntegerField(default=1, editable=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="school_settings_updated")
    updated_at = models.DateTimeField(auto_now=True)
    objects = GuardedWriteQuerySet.as_manager()

    class Meta:
        verbose_name = "school setting"
        verbose_name_plural = "school settings"

    def clean(self):
        super().clean()
        validate_terminology(self.terminology or {})
        validate_timezone_name(self.timezone)
        validate_report_branding(self.report_branding or {})
        validate_policy_values(self.policy_values or {})

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = type(self).objects.select_for_update().filter(pk=self.pk).first()
            self.version = (previous.version + 1) if previous else 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"version", "updated_at"}
            super().save(*args, **kwargs)
            SchoolSettingRevision.objects.create(
                setting=self, version=self.version, snapshot=self.as_snapshot(), changed_by=self.updated_by,
            )

    def as_snapshot(self):
        return {
            "terminology": self.terminology,
            "contact": {"name": self.contact_name, "email": self.contact_email, "phone": self.contact_phone, "address": self.contact_address},
            "timezone": self.timezone,
            "report_branding": self.report_branding,
            "policy_values": self.policy_values,
        }

    def __str__(self):
        return f"Settings for {self.school} (v{self.version})"


class SchoolSettingRevision(models.Model):
    setting = models.ForeignKey(SchoolSetting, on_delete=models.PROTECT, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="school_setting_revisions")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableHistoryQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["setting", "version"], name="uniq_setting_revision_version")]
        ordering = ["version"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Settings revisions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Settings revisions are immutable.")


class TimetableSlot(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    assignment = models.ForeignKey("learning.TeacherAssignment", on_delete=models.PROTECT, related_name="timetable_slots")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    room = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="timetable_slots_created")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = GuardedWriteQuerySet.as_manager()

    class Meta:
        ordering = ["weekday", "starts_at", "assignment__section__name"]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="timetable_end_after_start"),
            models.UniqueConstraint(fields=["assignment", "weekday", "starts_at"], name="uniq_timetable_assignment_time"),
        ]
        indexes = [models.Index(fields=["weekday", "starts_at", "ends_at"], name="timetable_time_idx")]

    @property
    def section(self):
        return self.assignment.section

    @property
    def subject(self):
        return self.assignment.subject

    @property
    def teacher(self):
        return self.assignment.user

    @property
    def school(self):
        return self.assignment.section.school_class.school

    def clean(self):
        super().clean()
        if not self.assignment_id:
            return
        section = self.assignment.section
        if not self.assignment.is_active:
            raise ValidationError({"assignment": "Timetable slots require an active teacher assignment."})
        try:
            self.assignment.full_clean()
            section.full_clean()
        except ValidationError as exc:
            raise ValidationError({"assignment": exc.messages}) from exc
        if self.assignment.user_id and not self.assignment.user.is_active:
            raise ValidationError({"assignment": "The assigned teacher must be active."})
        from accounts.models import SchoolMembership
        if not SchoolMembership.objects.filter(
            user=self.assignment.user, school=section.school_class.school,
            role=SchoolMembership.Role.TEACHER, is_active=True,
            user__is_active=True, school__is_active=True,
        ).exists():
            raise ValidationError({"assignment": "The teacher must have an active teacher membership at this school."})
        if section.school_class.school_id != section.academic_year.school_id:
            raise ValidationError("Section class and academic year must belong to the same school.")
        if section.campus_id and section.campus.school_id != section.school_class.school_id:
            raise ValidationError("Section campus must belong to the section school.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End time must be after start time."})

    def save(self, *args, **kwargs):
        self.full_clean()
        from .services import save_timetable_slot
        return save_timetable_slot(self, *args, **kwargs)

    def __str__(self):
        return f"{self.section} / {self.get_weekday_display()} {self.starts_at}-{self.ends_at}"


class Notice(models.Model):
    class Audience(models.TextChoices):
        ALL = "all", "Everyone"
        TEACHERS = "teachers", "Teachers"
        STUDENTS = "students", "Students"
        STAFF = "staff", "Staff"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="notices")
    section = models.ForeignKey("academics.Section", null=True, blank=True, on_delete=models.PROTECT, related_name="notices")
    title = models.CharField(max_length=180)
    body = models.TextField(max_length=6000)
    audience = models.CharField(max_length=16, choices=Audience.choices, default=Audience.ALL)
    publish_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notices_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="notices_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = GuardedWriteQuerySet.as_manager()

    class Meta:
        ordering = ["-publish_at", "-created_at"]

    def clean(self):
        super().clean()
        if self.section_id and self.school_id and self.section.school_class.school_id != self.school_id:
            raise ValidationError({"section": "Notice section must belong to the notice school."})
        if self.publish_at and self.expires_at and self.expires_at <= self.publish_at:
            raise ValidationError({"expires_at": "Notice expiry must be later than its publish time."})

    def save(self, *args, **kwargs):
        self.full_clean()
        from .services import save_notice
        return save_notice(self, *args, **kwargs)

    def __str__(self):
        return self.title


class NoticeRevision(models.Model):
    notice = models.ForeignKey(Notice, on_delete=models.PROTECT, related_name="revisions")
    snapshot = models.JSONField()
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="notice_revisions")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableHistoryQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Notice revisions are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Notice revisions are immutable.")
