from contextvars import ContextVar

from django.core.exceptions import ValidationError
from django.db import models


_attendance_write_authorized = ContextVar("attendance_write_authorized", default=False)
_correction_write_authorized = ContextVar("correction_write_authorized", default=False)


class AttendanceRecordQuerySet(models.QuerySet):
    def _require_service(self):
        if not _attendance_write_authorized.get():
            raise ValidationError("Attendance records may only be changed through attendance services.")

    def update(self, **kwargs):
        self._require_service()
        return super().update(**kwargs)

    def delete(self):
        self._require_service()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        self._require_service()
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        self._require_service()
        return super().bulk_update(objs, fields, **kwargs)


class AttendanceRecordManager(models.Manager.from_queryset(AttendanceRecordQuerySet)):
    pass


class AttendanceSessionManager(models.Manager.from_queryset(AttendanceRecordQuerySet)):
    pass


class AttendanceCorrectionQuerySet(models.QuerySet):
    def _require_service(self):
        if not _correction_write_authorized.get():
            raise ValidationError("Attendance correction requests may only be changed through attendance services.")

    def update(self, **kwargs):
        self._require_service()
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError("Attendance correction requests are retained for audit and cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        self._require_service()
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        self._require_service()
        return super().bulk_update(objs, fields, **kwargs)


class AttendanceCorrectionManager(models.Manager.from_queryset(AttendanceCorrectionQuerySet)):
    pass


class TeacherAssignment(models.Model):
    """A teacher's explicit authority over one subject in one section/year."""

    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="teaching_assignments")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="teacher_assignments")
    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="teacher_assignments")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "section", "subject"], name="uniq_teacher_section_subject")]
        ordering = ["section__school_class__name", "section__name", "subject__name"]

    def clean(self):
        if self.section_id and self.subject_id and self.section.school_class.school_id != self.subject.school_id:
            raise ValidationError("Teacher assignment subject and section must belong to the same school.")

    def __str__(self):
        return f"{self.user} / {self.section} / {self.subject}"


class AttendanceSession(models.Model):
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="attendance_sessions")
    date = models.DateField()
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="attendance_sessions_created")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AttendanceSessionManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["section", "date"], name="uniq_attendance_section_date")]
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        persisted = self.pk is not None and type(self).objects.filter(pk=self.pk).exists()
        if persisted:
            raise ValidationError("Attendance session details are immutable after creation.")
        if not _attendance_write_authorized.get():
            raise ValidationError("Attendance sessions may only be created or changed through attendance services.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _attendance_write_authorized.get():
            raise ValidationError("Attendance sessions cannot be deleted outside attendance services.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.section} / {self.date}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        LATE = "late", "Late"
        EXCUSED = "excused", "Excused"

    session = models.ForeignKey(AttendanceSession, on_delete=models.PROTECT, related_name="records")
    enrollment = models.ForeignKey("students.Enrollment", on_delete=models.PROTECT, related_name="attendance_records")
    status = models.CharField(max_length=12, choices=Status.choices)
    note = models.CharField(max_length=240, blank=True)

    objects = AttendanceRecordManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "enrollment"], name="uniq_attendance_session_enrollment")]
        ordering = ["enrollment__roll_number"]

    def clean(self):
        enrollment = self.enrollment
        if self.session_id and enrollment and enrollment.section_id != self.session.section_id:
            raise ValidationError("Attendance must be recorded for an enrollment in the session section.")
        if self.session_id and enrollment and enrollment.academic_year_id != self.session.section.academic_year_id:
            raise ValidationError("Attendance session and enrollment must belong to the same academic year.")

    def save(self, *args, **kwargs):
        # Check the database as well as Django's _state: callers can pass an existing
        # primary key to a newly constructed instance, where _state.adding is True.
        persisted = self.pk is not None and type(self).objects.filter(pk=self.pk).exists()
        if persisted and not _attendance_write_authorized.get():
            raise ValidationError("Attendance records are immutable outside attendance services.")
        if not persisted and not _attendance_write_authorized.get():
            raise ValidationError("Attendance records may only be created through attendance services.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _attendance_write_authorized.get():
            raise ValidationError("Attendance records cannot be deleted outside attendance services.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.enrollment} / {self.session.date} / {self.get_status_display()}"


class AttendanceCorrectionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        AUTO_REJECTED = "auto_rejected", "Auto-rejected"

    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.PROTECT, related_name="correction_requests")
    old_status = models.CharField(max_length=12, choices=AttendanceRecord.Status.choices)
    old_note = models.CharField(max_length=240, blank=True)
    new_status = models.CharField(max_length=12, choices=AttendanceRecord.Status.choices)
    new_note = models.CharField(max_length=240, blank=True)
    reason = models.CharField(max_length=500)
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="attendance_corrections_requested")
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="attendance_corrections_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)

    objects = AttendanceCorrectionManager()

    class Meta:
        ordering = ["-requested_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["attendance_record"], condition=models.Q(status="pending"), name="uniq_pending_attendance_correction",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | models.Q(status="auto_rejected", reviewed_by__isnull=True, reviewed_at__isnull=False)
                    | models.Q(status__in=["approved", "rejected"], reviewed_by__isnull=False, reviewed_at__isnull=False)
                ), name="attendance_correction_review_attribution_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        persisted = self.pk is not None and type(self).objects.filter(pk=self.pk).exists()
        if not _correction_write_authorized.get():
            raise ValidationError("Attendance correction requests may only be written through attendance services.")
        if persisted:
            prior = type(self).objects.get(pk=self.pk)
            immutable = ("attendance_record_id", "old_status", "old_note", "new_status", "new_note", "reason", "requested_by_id", "requested_at")
            if any(getattr(prior, field) != getattr(self, field) for field in immutable):
                raise ValidationError("Attendance correction request details are immutable.")
            allowed = {
                AttendanceCorrectionRequest.Status.PENDING: {AttendanceCorrectionRequest.Status.APPROVED,
                    AttendanceCorrectionRequest.Status.REJECTED, AttendanceCorrectionRequest.Status.AUTO_REJECTED},
                AttendanceCorrectionRequest.Status.APPROVED: set(),
                AttendanceCorrectionRequest.Status.REJECTED: set(),
                AttendanceCorrectionRequest.Status.AUTO_REJECTED: set(),
            }
            if self.status != prior.status and self.status not in allowed[prior.status]:
                raise ValidationError("Invalid attendance correction state transition.")
        elif self.status != self.Status.PENDING or self.reviewed_by_id or self.reviewed_at:
            raise ValidationError("New attendance correction requests must begin pending review.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attendance correction requests are retained for audit and cannot be deleted.")

    def __str__(self):
        return f"Correction for attendance {self.attendance_record_id} ({self.get_status_display()})"


class Assignment(models.Model):
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="learning_assignments")
    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="learning_assignments")
    teacher = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="learning_assignments")
    title = models.CharField(max_length=180)
    instructions = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at", "-created_at"]

    def clean(self):
        if self.section_id and self.subject_id and self.section.school_class.school_id != self.subject.school_id:
            raise ValidationError("Assignment subject and section must belong to the same school.")
        if self.teacher_id and self.section_id and self.subject_id:
            if not TeacherAssignment.objects.filter(user=self.teacher, section=self.section, subject=self.subject, is_active=True).exists():
                raise ValidationError("The teacher must be actively assigned to this section and subject.")

    def __str__(self):
        return self.title


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name="submissions")
    enrollment = models.ForeignKey("students.Enrollment", on_delete=models.PROTECT, related_name="submissions")
    response = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    feedback = models.TextField(blank=True)
    grade = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="submissions_graded")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assignment", "enrollment"], name="uniq_assignment_enrollment_submission")]
        ordering = ["-submitted_at"]

    def clean(self):
        if self.assignment_id and self.enrollment_id:
            if self.assignment.section_id != self.enrollment.section_id or self.assignment.section.academic_year_id != self.enrollment.academic_year_id:
                raise ValidationError("Submission enrollment must match the assignment section and year.")

    def __str__(self):
        return f"{self.assignment} / {self.enrollment}"


class SubmissionRevision(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="revisions")
    response = models.TextField()
    submitted_at = models.DateTimeField()
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_at", "pk"]

    def __str__(self):
        return f"{self.submission} revision {self.pk}"


class GradeRevision(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="grade_revisions")
    grade = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="grade_revisions_created")
    graded_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_at", "pk"]

    def __str__(self):
        return f"{self.submission} grade revision {self.pk}"
