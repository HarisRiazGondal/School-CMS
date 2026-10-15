from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

ASSESSMENT_LIFECYCLE_TOKEN = object()
QUESTION_LIFECYCLE_TOKEN = object()
ATTEMPT_LIFECYCLE_TOKEN = object()
ANSWER_LIFECYCLE_TOKEN = object()


class GuardedQuerySet(models.QuerySet):
    """Application-level lifecycle guards; privileged raw SQL remains outside this boundary."""

    def update(self, **kwargs):
        raise ValidationError("Assessment records must be changed through lifecycle services.")

    def delete(self):
        raise ValidationError("Assessment records and their history cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Assessment records must be created through lifecycle services.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Assessment records must be changed through lifecycle services.")


class Assessment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        FINALIZED = "finalized", "Finalized"
        PUBLISHED = "published", "Published"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="assessments")
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.PROTECT, related_name="assessments")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="assessments")
    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="assessments")
    term = models.ForeignKey("academics.Term", null=True, blank=True, on_delete=models.PROTECT, related_name="assessments")
    title = models.CharField(max_length=180)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    attempt_limit = models.PositiveSmallIntegerField(default=1)
    pass_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("50.00"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="assessments_created")
    created_at = models.DateTimeField(auto_now_add=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        ordering = ["-opens_at", "title"]
        constraints = [
            models.CheckConstraint(condition=Q(attempt_limit__gte=1), name="assessment_attempt_limit_positive"),
            models.CheckConstraint(condition=Q(pass_percent__gte=0, pass_percent__lte=100), name="assessment_pass_pct_range"),
            models.CheckConstraint(condition=Q(closes_at__gt=models.F("opens_at")), name="assessment_window_valid"),
        ]

    def clean(self):
        errors = {}
        if self.section_id and self.academic_year_id and self.section.academic_year_id != self.academic_year_id:
            errors["academic_year"] = "Assessment year must match its section year."
        if self.section_id and self.school_id and self.section.school_class.school_id != self.school_id:
            errors["school"] = "Assessment and section must belong to the same school."
        if self.subject_id and self.school_id and self.subject.school_id != self.school_id:
            errors["subject"] = "Assessment and subject must belong to the same school."
        if self.term_id and self.academic_year_id and self.term.academic_year_id != self.academic_year_id:
            errors["term"] = "Assessment term must belong to its academic year."
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            errors["closes_at"] = "The closing time must be after the opening time."
        if self.pass_percent is not None and not Decimal("0") <= self.pass_percent <= Decimal("100"):
            errors["pass_percent"] = "Pass percent must be between 0 and 100."  # nosec B105  # public grading threshold, not a credential.
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        lifecycle = kwargs.pop("_assessment_lifecycle_token", None)
        if lifecycle is not ASSESSMENT_LIFECYCLE_TOKEN:
            raise ValidationError("Create and change assessments through lifecycle services.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Assessment history cannot be deleted.")

    def __str__(self):
        return self.title


class Question(models.Model):
    class Kind(models.TextChoices):
        MCQ = "mcq", "Multiple choice"
        TRUE_FALSE = "true_false", "True / False"
        SHORT_ANSWER = "short_answer", "Short answer"
        MANUAL = "manual", "Manual review"

    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="assessment_questions")
    subject = models.ForeignKey("academics.Subject", on_delete=models.PROTECT, related_name="assessment_questions")
    assessment = models.ForeignKey(Assessment, null=True, blank=True, on_delete=models.PROTECT, related_name="questions")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    prompt = models.TextField()
    choices = models.JSONField(default=list, blank=True)
    max_points = models.DecimalField(max_digits=7, decimal_places=2)
    correct_answer = models.TextField(blank=True, help_text="Private scoring key; never expose in student views.")
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.CheckConstraint(condition=Q(max_points__gt=0), name="assessment_question_points_positive"),
            models.UniqueConstraint(fields=["assessment", "position"], condition=Q(assessment__isnull=False), name="uniq_assessment_question_position"),
        ]

    def clean(self):
        errors = {}
        if self.subject_id and self.school_id and self.subject.school_id != self.school_id:
            errors["subject"] = "Question school and subject must match."
        if self.assessment_id:
            if self.assessment.school_id != self.school_id or self.assessment.subject_id != self.subject_id:
                errors["assessment"] = "Assessment question must match the assessment school and subject."
            if self.assessment.status != Assessment.Status.DRAFT:
                errors["assessment"] = "Questions cannot be changed after an attempt begins."
        if self.kind == self.Kind.MCQ:
            if not isinstance(self.choices, list) or len(self.choices) < 2 or not self.correct_answer:
                errors["choices"] = "Multiple choice questions need at least two choices and a correct answer key."
            elif self.correct_answer not in self.choices:
                errors["correct_answer"] = "The correct answer must match one of the choices."
        elif self.kind == self.Kind.TRUE_FALSE:
            if self.correct_answer.lower() not in {"true", "false"}:
                errors["correct_answer"] = "True/false questions need a true or false answer key."
        elif self.kind in {self.Kind.SHORT_ANSWER, self.Kind.MANUAL} and not self.correct_answer and self.kind == self.Kind.SHORT_ANSWER:
            errors["correct_answer"] = "Short-answer questions need an expected answer for automatic comparison."
        if self.max_points is not None and self.max_points <= 0:
            errors["max_points"] = "Question points must be greater than zero."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        lifecycle = kwargs.pop("_question_lifecycle_token", None)
        if lifecycle is not QUESTION_LIFECYCLE_TOKEN:
            raise ValidationError("Create and change questions through lifecycle services.")
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("assessment_id").first()
            if old and old["assessment_id"] and old["assessment_id"] != self.assessment_id:
                raise ValidationError("A question attached to an assessment cannot be detached or moved.")
            if old and old["assessment_id"] and Assessment.objects.filter(pk=old["assessment_id"]).exclude(status=Assessment.Status.DRAFT).exists():
                raise ValidationError("Assessment questions are frozen after attempts begin.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Question records cannot be deleted.")

    def __str__(self):
        return self.prompt[:90]


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        FINALIZED = "finalized", "Finalized"
        PUBLISHED = "published", "Published"

    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="attempts")
    enrollment = models.ForeignKey("students.Enrollment", on_delete=models.PROTECT, related_name="assessment_attempts")
    number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    raw_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    total_points = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    grade_label = models.CharField(max_length=12, blank=True)
    grading_policy_version = models.CharField(max_length=40, blank=True)
    pass_percent_snapshot = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        ordering = ["enrollment__roll_number", "number"]
        constraints = [
            models.UniqueConstraint(fields=["assessment", "enrollment", "number"], name="uniq_assessment_enrollment_attempt_no"),
            models.CheckConstraint(condition=Q(number__gte=1), name="assessment_attempt_number_positive"),
        ]

    def clean(self):
        if self.assessment_id and self.enrollment_id:
            if self.assessment.school_id != self.enrollment.student.school_id:
                raise ValidationError({"enrollment": "Assessment and enrollment must belong to the same school."})
            if self.assessment.section_id != self.enrollment.section_id or self.assessment.academic_year_id != self.enrollment.academic_year_id:
                raise ValidationError({"enrollment": "Attempt enrollment must match the assessment section and year."})

    def save(self, *args, **kwargs):
        lifecycle = kwargs.pop("_attempt_lifecycle_token", None)
        if lifecycle is not ATTEMPT_LIFECYCLE_TOKEN:
            raise ValidationError("Create and change attempts through lifecycle services.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Attempt history cannot be deleted.")

    def __str__(self):
        return f"{self.assessment} / {self.enrollment} / attempt {self.number}"


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    response = models.TextField(blank=True)
    awarded_points = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    answered_at = models.DateTimeField(auto_now=True)
    objects = GuardedQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="uniq_answer_attempt_question")]
        ordering = ["question__position", "pk"]

    def clean(self):
        errors = {}
        if self.attempt_id and self.question_id:
            if self.question.assessment_id != self.attempt.assessment_id:
                errors["question"] = "Answer question must belong to its attempt assessment."
            if self.attempt.status != Attempt.Status.IN_PROGRESS and not getattr(self, "_allow_post_submit_grade", False):
                errors["attempt"] = "Answers cannot be changed after submission."
        if self.awarded_points is not None and self.question_id:
            if self.awarded_points < 0 or self.awarded_points > self.question.max_points:
                errors["awarded_points"] = "Awarded points must be between zero and question maximum."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        lifecycle = kwargs.pop("_answer_lifecycle_token", None)
        if lifecycle is not ANSWER_LIFECYCLE_TOKEN:
            raise ValidationError("Create and change answers through lifecycle services.")
        self._allow_post_submit_grade = lifecycle is ANSWER_LIFECYCLE_TOKEN
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("attempt_id").first()
            if old and Attempt.objects.filter(pk=old["attempt_id"]).exclude(status=Attempt.Status.IN_PROGRESS).exists() and not self._allow_post_submit_grade:
                raise ValidationError("Submitted attempt answers are frozen.")
        self.full_clean()
        try:
            return super().save(*args, **kwargs)
        finally:
            self._allow_post_submit_grade = False

    def delete(self, *args, **kwargs):
        raise ValidationError("Assessment answers cannot be deleted.")

    def __str__(self):
        return f"Answer {self.pk}"
