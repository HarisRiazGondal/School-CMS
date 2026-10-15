from datetime import date, datetime, timezone as datetime_timezone

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from learning.models import TeacherAssignment
from oversight.models import Notice, SchoolSetting, TimetableSlot
from oversight.services import create_timetable_slot
from schools.models import AcademicYear, School
from students.services import register_student


class OversightHTTPTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north")
        self.other_school = School.objects.create(name="South School", slug="south")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1),
            ends_on=date(2027, 7, 31), is_active=True,
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026-27", starts_on=date(2026, 8, 1),
            ends_on=date(2027, 7, 31), is_active=True,
        )
        self.grade = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.other_grade = SchoolClass.objects.create(school=self.school, name="Class 5")
        self.other_school_grade = SchoolClass.objects.create(school=self.other_school, name="Class 4")
        self.section = Section.objects.create(school_class=self.grade, academic_year=self.year, name="A")
        self.other_section = Section.objects.create(school_class=self.other_grade, academic_year=self.year, name="B")
        self.foreign_section = Section.objects.create(school_class=self.other_school_grade, academic_year=self.other_year, name="A")
        self.math = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        self.history = Subject.objects.create(school=self.school, name="History", code="HIST")
        self.foreign_subject = Subject.objects.create(school=self.other_school, name="Foreign Studies", code="FOREIGN")
        self.admin = User.objects.create_user(username="admin", email="admin@example.com", password="secret-test-pass")
        self.teacher = User.objects.create_user(username="teacher", email="teacher@example.com", password="secret-test-pass")
        self.other_teacher = User.objects.create_user(username="otherteacher", email="otherteacher@example.com", password="secret-test-pass")
        self.accountant = User.objects.create_user(username="accountant", email="accountant@example.com", password="secret-test-pass")
        self.student_user = User.objects.create_user(username="student", email="student@example.com", password="secret-test-pass")
        self.other_admin = User.objects.create_user(username="otheradmin", email="otheradmin@example.com", password="secret-test-pass")
        for user, school, role in [
            (self.admin, self.school, SchoolMembership.Role.SCHOOL_ADMIN),
            (self.teacher, self.school, SchoolMembership.Role.TEACHER),
            (self.other_teacher, self.school, SchoolMembership.Role.TEACHER),
            (self.accountant, self.school, SchoolMembership.Role.ACCOUNTANT),
            (self.student_user, self.school, SchoolMembership.Role.STUDENT),
            (self.other_admin, self.other_school, SchoolMembership.Role.SCHOOL_ADMIN),
        ]:
            SchoolMembership.objects.create(user=user, school=school, role=role)
        self.assignment = TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.math)
        self.other_assignment = TeacherAssignment.objects.create(user=self.other_teacher, section=self.other_section, subject=self.history)
        self.same_section_other_subject = TeacherAssignment.objects.create(user=self.other_teacher, section=self.section, subject=self.history)
        self.student, self.enrollment = register_student(
            user=self.admin, school=self.school, first_name="Ada", last_name="Learner",
            academic_year=self.year, section=self.section, roll_number="4A-01", student_user=self.student_user,
        )
        self.client.force_login(self.admin)
        self.dashboard = reverse("oversight:dashboard", args=[self.school.slug])

    def test_admin_dashboard_renders_branding_terms_metrics_and_scoped_links(self):
        SchoolSetting.objects.create(
            school=self.school,
            terminology={"student": "Pupil", "section": "Form"},
            report_branding={"school_name": "North Learning House", "footer": "Learn together"},
            policy_values={"student_results_visible": False},
        )
        response = self.client.get(self.dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North Learning House")
        self.assertContains(response, "pupils")
        self.assertContains(response, "Active pupils: 1")
        self.assertContains(response, "Applications awaiting decision: 0")
        self.assertContains(response, "Attendance corrections awaiting review: 0")
        self.assertContains(response, "Admissions")

    def test_admin_can_revision_save_settings_and_student_result_policy_hides_dashboard_result_link(self):
        url = reverse("oversight:settings", args=[self.school.slug])
        response = self.client.post(url, {
            "contact_name": "Office", "contact_email": "office@example.com", "contact_phone": "555-0100",
            "contact_address": "North Street", "timezone": "Asia/Karachi",
            "terminology_json": '{"student":"Pupil","section":"Form"}',
            "report_branding_json": '{"school_name":"North Learning House","footer":"Learn together"}',
            "policy_values_json": '{"student_results_visible":false}',
        })
        self.assertRedirects(response, self.dashboard)
        setting = SchoolSetting.objects.get(school=self.school)
        self.assertEqual(setting.version, 1)
        self.assertEqual(setting.revisions.get().changed_by, self.admin)
        self.client.force_login(self.student_user)
        response = self.client.get(self.dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published results are currently hidden by school policy.")
        self.assertNotContains(response, reverse("assessment:report-card"))
        self.assertNotContains(response, "Published result distribution")

    def test_notice_datetime_is_parsed_in_school_timezone_and_edits_are_school_scoped(self):
        url = reverse("oversight:notice-create", args=[self.school.slug])
        response = self.client.post(url, {
            "section": self.section.pk, "title": "Parent evening", "body": "Meet at the hall.",
            "audience": Notice.Audience.ALL, "publish_at": "2026-10-15T09:00",
            "expires_at": "", "is_published": "on",
        })
        self.assertRedirects(response, reverse("oversight:notices", args=[self.school.slug]))
        notice = Notice.objects.get(school=self.school)
        self.assertEqual(notice.publish_at, datetime(2026, 10, 15, 4, tzinfo=datetime_timezone.utc))
        self.assertEqual(notice.section, self.section)
        self.assertEqual(notice.revisions.count(), 0)
        edit_url = reverse("oversight:notice-edit", args=[self.other_school.slug, notice.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 404)
        response = self.client.post(reverse("oversight:notice-edit", args=[self.school.slug, notice.pk]), {
            "section": self.section.pk, "title": "Updated parent evening", "body": "New details.",
            "audience": Notice.Audience.ALL, "publish_at": "2026-10-15T10:00",
            "expires_at": "", "is_published": "on",
        })
        self.assertRedirects(response, reverse("oversight:notices", args=[self.school.slug]))
        notice.refresh_from_db()
        self.assertEqual(notice.title, "Updated parent evening")
        self.assertEqual(notice.revisions.count(), 1)

    def test_timetable_create_is_admin_only_and_teacher_dashboard_matches_assigned_teacher(self):
        create_timetable_slot(self.admin, assignment=self.assignment, weekday=0, starts_at="09:00", ends_at="10:00", room="A1")
        create_timetable_slot(self.admin, assignment=self.other_assignment, weekday=0, starts_at="09:00", ends_at="10:00", room="B1")
        create_timetable_slot(self.admin, assignment=self.same_section_other_subject, weekday=1, starts_at="11:00", ends_at="12:00", room="A1")
        self.client.force_login(self.teacher)
        response = self.client.get(self.dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mathematics")
        self.assertNotContains(response, "History")
        self.assertNotContains(response, "Add timetable slot")
        self.assertEqual(self.client.get(reverse("oversight:timetable-create", args=[self.school.slug])).status_code, 403)

    def test_teacher_can_create_and_edit_only_assigned_section_notices(self):
        self.client.force_login(self.teacher)
        url = reverse("oversight:notice-create", args=[self.school.slug])
        self.assertEqual(self.client.get(url).status_code, 200)
        publish_at = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")
        payload = {
            "section": self.section.pk, "title": "Math materials", "body": "Bring your notebook.",
            "audience": Notice.Audience.TEACHERS, "publish_at": publish_at,
            "expires_at": "", "is_published": "on",
        }
        response = self.client.post(url, payload)
        self.assertRedirects(response, reverse("oversight:notices", args=[self.school.slug]))
        notice = Notice.objects.get(school=self.school)
        self.assertEqual(notice.section, self.section)

        edit_url = reverse("oversight:notice-edit", args=[self.school.slug, notice.pk])
        payload.update({"title": "Updated math materials", "section": self.other_section.pk})
        response = self.client.post(edit_url, payload)
        self.assertEqual(response.status_code, 200)
        notice.refresh_from_db()
        self.assertEqual(notice.title, "Math materials")
        payload.update({"title": "Updated math materials", "section": self.section.pk})
        response = self.client.post(edit_url, payload)
        self.assertRedirects(response, reverse("oversight:notices", args=[self.school.slug]))
        notice.refresh_from_db()
        self.assertEqual(notice.title, "Updated math materials")

        schoolwide = Notice.objects.create(
            school=self.school, title="Schoolwide", body="Admin notice", created_by=self.admin,
            is_published=True,
        )
        self.assertEqual(self.client.get(reverse("oversight:notice-edit", args=[self.school.slug, schoolwide.pk])).status_code, 403)
        response = self.client.post(url, {**payload, "section": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())

    def test_accountant_dashboard_is_financial_only_and_cannot_open_settings(self):
        create_timetable_slot(self.admin, assignment=self.assignment, weekday=0, starts_at="09:00", ends_at="10:00", room="A1")
        self.client.force_login(self.accountant)
        response = self.client.get(self.dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Receivables summary")
        self.assertNotContains(response, "Timetable")
        self.assertNotContains(response, "Active enrollments")
        self.assertEqual(self.client.get(reverse("oversight:settings", args=[self.school.slug])).status_code, 403)

    def test_cross_school_member_cannot_open_school_dashboard(self):
        self.client.force_login(self.other_admin)
        self.assertEqual(self.client.get(self.dashboard).status_code, 403)

