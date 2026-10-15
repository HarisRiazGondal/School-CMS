from datetime import date
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section
from schools.models import AcademicYear, School
from students.services import register_student


class AccessibilityMarkupParser(HTMLParser):
    """Collect the small set of relationships covered by server-rendered acceptance."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.label_for = []
        self.controls = []
        self.tables = []
        self.current_table = None
        self.main_landmarks = []
        self.skip_links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "label" and attrs.get("for"):
            self.label_for.append(attrs["for"])
        if tag in {"input", "select", "textarea"} and attrs.get("type") != "hidden":
            self.controls.append(attrs)
        if tag == "main":
            self.main_landmarks.append(attrs)
        if tag == "a" and attrs.get("href") == "#main-content":
            self.skip_links.append(attrs)
        if tag == "table":
            self.current_table = []
            self.tables.append(self.current_table)
        if tag == "th" and self.current_table is not None:
            self.current_table.append(attrs)

    def handle_endtag(self, tag):
        if tag == "table":
            self.current_table = None


class AccessibilityHTTPTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="access-north")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31)
        )
        self.grade = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.section = Section.objects.create(school_class=self.grade, academic_year=self.year, name="A")
        self.admin = User.objects.create_user(username="access-admin", password="safe-test-password")
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.student, _ = register_student(
            user=self.admin, school=self.school, first_name="Amina", last_name="Khan",
            academic_year=self.year, section=self.section, roll_number="04-01",
        )
        self.client.force_login(self.admin)

    def parse(self, response):
        parser = AccessibilityMarkupParser()
        parser.feed(response.content.decode())
        return parser

    def assert_page_shell(self, response):
        parser = self.parse(response)
        self.assertEqual(len(parser.main_landmarks), 1)
        self.assertEqual(parser.main_landmarks[0].get("id"), "main-content")
        self.assertIn("tabindex", parser.main_landmarks[0])
        self.assertEqual(len(parser.skip_links), 1)
        for control in parser.controls:
            has_programmatic_label = (
                control.get("aria-label")
                or control.get("aria-labelledby")
                or control.get("id") in parser.label_for
            )
            self.assertTrue(has_programmatic_label, f"Unlabelled control: {control}")

    def test_student_pages_expose_skip_target_labeled_controls_and_scoped_table_headers(self):
        for url in (
            reverse("students:register", kwargs={"school_slug": self.school.slug}),
            reverse("students:list", kwargs={"school_slug": self.school.slug}),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assert_page_shell(response)

        parser = self.parse(self.client.get(reverse("students:list", kwargs={"school_slug": self.school.slug})))
        self.assertTrue(parser.tables)
        self.assertTrue(parser.tables[0])
        self.assertTrue(all(header.get("scope") == "col" for header in parser.tables[0]))

    def test_invalid_registration_has_an_announced_summary_linking_to_the_field(self):
        response = self.client.post(
            reverse("students:register", kwargs={"school_slug": self.school.slug}),
            {"first_name": "", "last_name": "Khan", "academic_year": self.year.pk,
             "section": self.section.pk, "roll_number": "04-02"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="error-summary" role="alert"')
        self.assertContains(response, 'href="#id_first_name"')
        self.assertContains(response, 'id="id_first_name"')

    def test_batch_promotion_controls_are_named_for_the_student_row(self):
        response = self.client.get(reverse("students:batch-promotion", kwargs={"school_slug": self.school.slug}))
        self.assertEqual(response.status_code, 200)
        self.assert_page_shell(response)
        self.assertContains(response, "Outcome for STU-000001")
        self.assertContains(response, "Conditional reason for STU-000001")

    def test_oversight_finance_and_attendance_forms_render_labeled_controls(self):
        urls = (
            reverse("oversight:settings", args=[self.school.slug]),
            reverse("finance:plan-create", args=[self.school.slug]),
            reverse("learning:attendance-entry", args=[self.section.pk]),
        )
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assert_page_shell(response)
