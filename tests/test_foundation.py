from datetime import date
from django.core.exceptions import ValidationError
from django.test import TestCase

from academics.models import SchoolClass, Section
from schools.models import AcademicYear, School

class FoundationModelTests(TestCase):
    def test_section_rejects_cross_school_class_and_year(self):
        first = School.objects.create(name="First School", slug="first-school")
        second = School.objects.create(name="Second School", slug="second-school")
        school_class = SchoolClass.objects.create(school=first, name="Class 1")
        year = AcademicYear.objects.create(
            school=second,
            name="2026-27",
            starts_on=date(2026, 8, 1),
            ends_on=date(2027, 7, 31),
        )
        section = Section(school_class=school_class, academic_year=year, name="A")
        with self.assertRaises(ValidationError):
            section.full_clean()
