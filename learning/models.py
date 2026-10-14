from django.core.exceptions import ValidationError
from django.db import models


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

    class Meta:
        constraints = [models.UniqueConstraint(fields=["section", "date"], name="uniq_attendance_section_date")]
        ordering = ["-date"]

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

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "enrollment"], name="uniq_attendance_session_enrollment")]
        ordering = ["enrollment__roll_number"]

    def clean(self):
        enrollment = self.enrollment
        if self.session_id and enrollment and enrollment.section_id != self.session.section_id:
            raise ValidationError("Attendance must be recorded for an enrollment in the session section.")
        if self.session_id and enrollment and enrollment.academic_year_id != self.session.section.academic_year_id:
            raise ValidationError("Attendance session and enrollment must belong to the same academic year.")

    def __str__(self):
        return f"{self.enrollment} / {self.session.date} / {self.get_status_display()}"


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
