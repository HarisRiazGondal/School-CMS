from django.core.exceptions import ValidationError
from django.db import models

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
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="sections")
    academic_year = models.ForeignKey(
        "schools.AcademicYear", on_delete=models.PROTECT, related_name="sections"
    )
    name = models.CharField(max_length=40)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "academic_year", "name"],
                name="uniq_class_year_section",
            )
        ]

    def clean(self):
        if (
            self.school_class_id
            and self.academic_year_id
            and self.school_class.school_id != self.academic_year.school_id
        ):
            raise ValidationError("Class and academic year must belong to the same school.")

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
