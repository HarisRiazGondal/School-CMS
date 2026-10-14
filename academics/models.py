from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class SchoolClass(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="classes")
    name = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="uniq_class_school_name")
        ]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.school} / {self.name}"

class Section(models.Model):
    campus = models.ForeignKey("schools.Campus", on_delete=models.PROTECT, null=True, blank=True, related_name="sections")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="sections")
    academic_year = models.ForeignKey(
        "schools.AcademicYear", on_delete=models.PROTECT, related_name="sections"
    )
    name = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "academic_year", "name"],
                condition=Q(campus__isnull=True),
                name="uniq_schoolwide_class_year_section",
            ),
            models.UniqueConstraint(fields=["school_class", "academic_year", "campus", "name"], condition=Q(campus__isnull=False), name="uniq_campus_class_year_section")
        ]

    def clean(self):
        if (
            self.school_class_id
            and self.academic_year_id
            and self.school_class.school_id != self.academic_year.school_id
        ):
            raise ValidationError("Class and academic year must belong to the same school.")
        if self.campus_id and self.school_class_id and self.campus.school_id != self.school_class.school_id:
            raise ValidationError("Campus must belong to the section school.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.school_class} / {self.academic_year.name} / {self.name}"

class Subject(models.Model):
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="subjects")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="uniq_subject_school_code")
        ]

    def __str__(self):
        return f"{self.school} / {self.code}"


class Term(models.Model):
    academic_year = models.ForeignKey("schools.AcademicYear", on_delete=models.PROTECT, related_name="terms")
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20)
    starts_on = models.DateField()
    ends_on = models.DateField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "code"], name="uniq_term_year_code"),
            models.CheckConstraint(condition=Q(ends_on__gte=models.F("starts_on")), name="term_dates_valid"),
        ]
        ordering = ["sort_order", "starts_on"]

    def clean(self):
        if self.academic_year_id and self.starts_on and self.ends_on:
            if not (self.academic_year.starts_on <= self.starts_on <= self.ends_on <= self.academic_year.ends_on):
                raise ValidationError("Term dates must fall inside its academic year.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.academic_year} / {self.name}"
