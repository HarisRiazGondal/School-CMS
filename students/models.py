import uuid

from django.core.exceptions import ValidationError
from django.db import models


STUDENT_REGISTRATION_TOKEN = object()
ENROLLMENT_OUTCOME_TOKEN = object()
STUDENT_ACCOUNT_LINK_TOKEN = object()
ADMISSION_DECISION_TOKEN = object()
ADMISSION_INTAKE_TOKEN = object()
PROMOTION_DECISION_TOKEN = object()


class StudentQuerySet(models.QuerySet):
    protected_fields = {"id", "pk", "school", "school_id", "student_code", "user", "user_id"}

    def update(self, **kwargs):
        if self.protected_fields.intersection(kwargs):
            raise ValidationError("Student identity fields cannot be changed through queryset updates.")
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError("Registered student identities cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Register student identities through the registration service.")

    def bulk_update(self, objs, fields, **kwargs):
        if self.protected_fields.intersection(fields):
            raise ValidationError("Student identity fields cannot be changed through bulk updates.")
        return super().bulk_update(objs, fields, **kwargs)


class EnrollmentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Enrollment history changes must use lifecycle services.")

    def delete(self):
        raise ValidationError("Enrollment history cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Create enrollments through lifecycle services.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Enrollment history changes must use lifecycle services.")


class Student(models.Model):
    """A permanent school-scoped identity, independent of yearly placement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="students")
    user = models.OneToOneField(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="student_profile",
    )
    student_code = models.CharField(max_length=48, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = StudentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "student_code"], name="uniq_student_code_school"),
        ]
        ordering = ["first_name", "last_name", "student_code"]

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_identity_id = instance.pk
        return instance

    def save(self, *args, **kwargs):
        registration_token = kwargs.pop("_registration_token", None)
        loaded_id = getattr(self, "_loaded_identity_id", None)
        if loaded_id is not None and self.pk != loaded_id:
            raise ValidationError("Student identity UUID is immutable.")
        previous = type(self).objects.filter(pk=self.pk).values("school_id", "student_code", "user_id").first()
        if previous:
            if str(previous["school_id"]) != str(self.school_id) or previous["student_code"] != self.student_code:
                raise ValidationError("Student school and student code are immutable.")
            if previous["user_id"] != self.user_id and kwargs.pop("_account_link_token", None) is not STUDENT_ACCOUNT_LINK_TOKEN:
                raise ValidationError("Student portal accounts can only be linked through the account-link service.")
        elif registration_token is not STUDENT_REGISTRATION_TOKEN:
            raise ValidationError("Create permanent student identities through the registration service.")
        super().save(*args, **kwargs)
        self._loaded_identity_id = self.pk

    def delete(self, *args, **kwargs):
        raise ValidationError("Registered student identities cannot be deleted.")

    def __str__(self):
        return f"{self.student_code} — {self.first_name} {self.last_name}".strip()


class Guardian(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="guardians")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)

    def __str__(self):
        return self.name


class GuardianStudentRelation(models.Model):
    guardian = models.ForeignKey(Guardian, on_delete=models.PROTECT, related_name="student_relations")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="guardian_relations")
    relationship = models.CharField(max_length=40, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["guardian", "student"], name="uniq_guardian_student_relation"),
        ]

    def clean(self):
        if self.guardian_id and self.student_id and self.guardian.school_id != self.student.school_id:
            raise ValidationError("Guardian and student must belong to the same school.")


class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PROMOTED = "promoted", "Promoted"
        REPEATED = "repeated", "Repeated"
        GRADUATED = "graduated", "Graduated"
        WITHDRAWN = "withdrawn", "Withdrawn"
        TRANSFERRED = "transferred", "Transferred"
        CONDITIONAL = "conditional", "Conditional"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="enrollments")
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.PROTECT, related_name="enrollments")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="enrollments")
    roll_number = models.CharField(max_length=40)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    previous_enrollment = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="next_enrollments"
    )
    enrolled_at = models.DateField(auto_now_add=True)

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "academic_year"], name="uniq_student_enrollment_year"),
            models.UniqueConstraint(fields=["section", "roll_number"], name="uniq_section_roll_number"),
        ]
        ordering = ["academic_year__starts_on", "roll_number"]

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_enrollment_id = instance.pk
        instance._loaded_placement = (instance.student_id, instance.academic_year_id, instance.section_id, instance.roll_number)
        instance._loaded_status = instance.status
        return instance

    def save(self, *args, **kwargs):
        outcome_token = kwargs.pop("_outcome_transition_token", None)
        loaded_id = getattr(self, "_loaded_enrollment_id", None)
        if loaded_id is not None and self.pk != loaded_id:
            raise ValidationError("Enrollment identity UUID is immutable.")
        previous = type(self).objects.filter(pk=self.pk).values(
            "student_id", "academic_year_id", "section_id", "roll_number", "status"
        ).first()
        if previous:
            placement = (self.student_id, self.academic_year_id, self.section_id, self.roll_number)
            persisted = (previous["student_id"], previous["academic_year_id"], previous["section_id"], previous["roll_number"])
            if placement != persisted:
                raise ValidationError("Enrollment placement and roll number are immutable; create a new enrollment.")
            if self.status != previous["status"] and (
                outcome_token is not ENROLLMENT_OUTCOME_TOKEN or previous["status"] != self.Status.ACTIVE
            ):
                raise ValidationError("Enrollment outcomes can only be set once through the promotion service.")
        super().save(*args, **kwargs)
        self._loaded_enrollment_id = self.pk
        self._loaded_placement = (self.student_id, self.academic_year_id, self.section_id, self.roll_number)
        self._loaded_status = self.status

    def delete(self, *args, **kwargs):
        raise ValidationError("Enrollment history cannot be deleted.")

    def clean(self):
        errors = {}
        if self.student_id and self.academic_year_id and self.student.school_id != self.academic_year.school_id:
            errors["student"] = "Student and academic year must belong to the same school."
        if self.section_id and self.academic_year_id and self.section.academic_year_id != self.academic_year_id:
            errors["academic_year"] = "Enrollment year must match the section's academic year."
        if self.student_id and self.section_id and self.student.school_id != self.section.school_class.school_id:
            errors["section"] = "Student and section must belong to the same school."
        if self.previous_enrollment_id and self.student_id:
            if self.previous_enrollment.student_id != self.student_id:
                errors["previous_enrollment"] = "Promotion lineage must belong to the same student."
            elif self.academic_year_id and self.previous_enrollment.academic_year.starts_on >= self.academic_year.starts_on:
                errors["previous_enrollment"] = "A linked enrollment must be from an earlier academic year."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.student.student_code} / {self.academic_year.name} / {self.roll_number}"


class AdmissionApplicationQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Admission applications must be changed through decision services.")

    def delete(self):
        raise ValidationError("Admission application history cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Create applications through the intake service.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Admission applications must be changed through decision services.")


class AdmissionApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="admission_applications")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.PROTECT, related_name="admission_applications")
    section = models.ForeignKey("academics.Section", on_delete=models.PROTECT, related_name="admission_applications")
    roll_number = models.CharField(max_length=40)
    guardian_name = models.CharField(max_length=200, blank=True)
    guardian_phone = models.CharField(max_length=40, blank=True)
    guardian_email = models.EmailField(blank=True)
    guardian_relationship = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    decision_note = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="admission_decisions")
    decided_at = models.DateTimeField(null=True, blank=True)
    student = models.OneToOneField(Student, null=True, blank=True, on_delete=models.PROTECT, related_name="admission_application")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AdmissionApplicationQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]

    def save(self, *args, **kwargs):
        token = kwargs.pop("_decision_token", None)
        intake_token = kwargs.pop("_intake_token", None)
        previous = type(self).objects.filter(pk=self.pk).values("status").first()
        if previous is None and intake_token is not ADMISSION_INTAKE_TOKEN:
            raise ValidationError("Create admission applications through the intake service.")
        if previous is not None:
            immutable_values = type(self).objects.filter(pk=self.pk).values(
                "school_id", "first_name", "last_name", "date_of_birth", "academic_year_id", "section_id",
                "roll_number", "guardian_name", "guardian_phone", "guardian_email", "guardian_relationship",
            ).get()
            current_values = {
                "school_id": self.school_id, "first_name": self.first_name, "last_name": self.last_name,
                "date_of_birth": self.date_of_birth, "academic_year_id": self.academic_year_id,
                "section_id": self.section_id, "roll_number": self.roll_number,
                "guardian_name": self.guardian_name, "guardian_phone": self.guardian_phone,
                "guardian_email": self.guardian_email, "guardian_relationship": self.guardian_relationship,
            }
            if immutable_values != current_values:
                raise ValidationError("Admission intake details are immutable after submission.")
            decision_values = type(self).objects.filter(pk=self.pk).values(
                "status", "decision_note", "decided_by_id", "decided_at", "student_id"
            ).get()
            current_decision_values = {
                "status": self.status, "decision_note": self.decision_note,
                "decided_by_id": self.decided_by_id, "decided_at": self.decided_at, "student_id": self.student_id,
            }
            if decision_values != current_decision_values and token is not ADMISSION_DECISION_TOKEN:
                raise ValidationError("Admission decisions must use the decision service.")
        if previous and previous["status"] != self.Status.PENDING and token is not ADMISSION_DECISION_TOKEN:
            raise ValidationError("Final admission decisions are immutable.")
        if previous and previous["status"] != self.status and token is not ADMISSION_DECISION_TOKEN:
            raise ValidationError("Admission decisions must use the decision service.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Admission application history cannot be deleted.")


class PromotionDecisionQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Promotion decisions are immutable.")

    def delete(self):
        raise ValidationError("Promotion decision history cannot be deleted.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Create promotion decisions through lifecycle services.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Promotion decisions are immutable.")


class PromotionDecision(models.Model):
    """Immutable, attributed snapshot of a finalized yearly student outcome."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_enrollment = models.OneToOneField(Enrollment, on_delete=models.PROTECT, related_name="promotion_decision")
    target_enrollment = models.ForeignKey(Enrollment, null=True, blank=True, on_delete=models.PROTECT, related_name="prior_decisions")
    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="promotion_decisions")
    outcome = models.CharField(max_length=16, choices=Enrollment.Status.choices)
    source_year = models.CharField(max_length=80)
    source_section = models.CharField(max_length=160)
    source_roll_number = models.CharField(max_length=40)
    target_year = models.CharField(max_length=80, blank=True)
    target_section = models.CharField(max_length=160, blank=True)
    target_roll_number = models.CharField(max_length=40, blank=True)
    condition_reason = models.CharField(max_length=500, blank=True)
    batch_id = models.UUIDField(null=True, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    objects = PromotionDecisionQuerySet.as_manager()

    def save(self, *args, **kwargs):
        token = kwargs.pop("_decision_token", None)
        if not self._state.adding or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Promotion decisions are immutable.")
        if token is not PROMOTION_DECISION_TOKEN:
            raise ValidationError("Create promotion decisions through lifecycle services.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Promotion decision history cannot be deleted.")
