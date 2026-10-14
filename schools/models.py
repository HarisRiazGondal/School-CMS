import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class School(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Campus(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="campuses")
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=40)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="uniq_campus_school_code")
        ]

    def __str__(self):
        return f"{self.school} / {self.name}"

class AcademicYear(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="academic_years")
    name = models.CharField(max_length=40)
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="uniq_year_school_name"),
            models.CheckConstraint(
                condition=Q(ends_on__gte=models.F("starts_on")),
                name="academic_year_dates_valid",
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=Q(is_active=True),
                name="one_active_year_per_school",
            ),
        ]

    def clean(self):
        if self.ends_on < self.starts_on:
            raise ValidationError("Academic year must end on or after its start date.")
        if self.is_active and AcademicYear.objects.filter(
            school=self.school, is_active=True
        ).exclude(pk=self.pk).exists():
            raise ValidationError("Only one academic year may be active for a school.")

    def __str__(self):
        return f"{self.school} / {self.name}"
