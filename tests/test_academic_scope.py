from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from academics.models import SchoolClass, Section, Term
from schools.models import School, Campus, AcademicYear

class AcademicScopeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Academy', slug='academy')
        self.other = School.objects.create(name='Other', slug='other')
        self.grade = SchoolClass.objects.create(school=self.school, name='Class 1')
        self.year = AcademicYear.objects.create(school=self.school, name='2026-27', starts_on=date(2026,8,1), ends_on=date(2027,7,31))
    def test_ordinary_create_rejects_cross_school(self):
        other_year = AcademicYear.objects.create(school=self.other, name='2026-27', starts_on=date(2026,8,1), ends_on=date(2027,7,31))
        with self.assertRaises(ValidationError):
            Section.objects.create(school_class=self.grade, academic_year=other_year, name='A')
    def test_campus_scope_and_separate_campus_sections(self):
        a = Campus.objects.create(school=self.school, name='North', code='N')
        b = Campus.objects.create(school=self.school, name='South', code='S')
        for campus in (a,b):
            Section.objects.create(school_class=self.grade, academic_year=self.year, campus=campus, name='A')
        with self.assertRaises(ValidationError):
            Section.objects.create(school_class=self.grade, academic_year=self.year, campus=a, name='A')
        wrong = Campus.objects.create(school=self.other, name='Other', code='O')
        with self.assertRaises(ValidationError):
            Section.objects.create(school_class=self.grade, academic_year=self.year, campus=wrong, name='B')
    def test_term_dates_are_bounded_by_year(self):
        Term.objects.create(academic_year=self.year, name='First', code='T1', starts_on=date(2026,8,1), ends_on=date(2026,12,1))
        with self.assertRaises(ValidationError):
            Term.objects.create(academic_year=self.year, name='Invalid', code='T2', starts_on=date(2025,8,1), ends_on=date(2026,12,1))
    def test_active_year_database_constraint(self):
        self.year.is_active=True
        self.year.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AcademicYear.objects.create(school=self.school, name='2027-28', starts_on=date(2027,8,1), ends_on=date(2028,7,31), is_active=True)
