from datetime import date, time, timedelta
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.utils import timezone
from django.urls import reverse

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from learning.models import TeacherAssignment
from oversight.models import Notice, NoticeRevision, POLICY_DEFAULTS, SchoolSetting, SchoolSettingRevision, TimetableSlot
from oversight.services import (
    accountant_finance_only,
    create_notice,
    create_timetable_slot,
    get_school_policy,
    get_school_timezone,
    save_school_setting,
    scoped_dashboard_summary,
    teacher_assignments_for_school,
    teacher_timetable,
    update_notice,
)
from schools.models import AcademicYear, Campus, School


class OversightCoreTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north-oversight")
        self.other_school = School.objects.create(name="South School", slug="south-oversight")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.grade = SchoolClass.objects.create(school=self.school, name="Grade 5")
        self.other_grade = SchoolClass.objects.create(school=self.other_school, name="Grade 5")
        self.section = Section.objects.create(school_class=self.grade, academic_year=self.year, name="A")
        self.section_b = Section.objects.create(school_class=self.grade, academic_year=self.year, name="B")
        self.other_section = Section.objects.create(school_class=self.other_grade, academic_year=self.other_year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Math", code="MATH")
        self.subject_two = Subject.objects.create(school=self.school, name="Science", code="SCI")
        self.teacher = User.objects.create_user(username="teacher-over", email="teacher-over@example.test", password="test-password-123")
        self.admin = User.objects.create_user(username="admin-over", email="admin-over@example.test", password="test-password-123")
        self.accountant = User.objects.create_user(username="accountant-over", email="accountant-over@example.test", password="test-password-123")
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.accountant, school=self.school, role=SchoolMembership.Role.ACCOUNTANT)
        self.assignment = TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        self.assignment_b = TeacherAssignment.objects.create(user=self.teacher, section=self.section_b, subject=self.subject_two)

    def test_school_settings_validate_timezone_allowlists_and_capture_immutable_versions(self):
        setting = save_school_setting(
            self.admin, self.school,
            timezone="Pacific/Auckland",
            terminology={"students": "learners"},
            policy_values={"attendance_correction_days": 14, "student_results_visible": False},
            report_branding={"primary_color": "#245"},
            contact_email="office@example.test",
        )
        self.assertEqual(setting.version, 1)
        self.assertEqual(get_school_timezone(self.school).key, "Pacific/Auckland")
        self.assertFalse(get_school_policy(self.school, "student_results_visible", True))
        self.assertEqual(get_school_policy(self.school, "late_submission_allowed", False), POLICY_DEFAULTS["late_submission_allowed"])
        setting = save_school_setting(self.admin, self.school, contact_phone="555-0100")
        self.assertEqual(setting.version, 2)
        self.assertEqual(list(setting.revisions.values_list("version", flat=True)), [1, 2])
        with self.assertRaises(ValidationError):
            save_school_setting(self.admin, self.school, timezone="Mars/Olympus")
        with self.assertRaises(ValidationError):
            save_school_setting(self.admin, self.school, policy_values={"fee_reminder_days": 30})
        with self.assertRaises(ValidationError):
            SchoolSetting.objects.filter(pk=setting.pk).update(timezone="UTC")
        with self.assertRaises(ValidationError):
            SchoolSettingRevision.objects.filter(setting=setting).delete()

    def test_default_policies_are_effective_and_unknown_policy_is_not_exposed(self):
        self.assertEqual(get_school_policy(self.school, "late_submission_allowed", False), True)
        self.assertEqual(get_school_policy(self.school, "attendance_correction_days", 0), 7)
        self.assertEqual(get_school_policy(self.school, "notice_expiry_days", 50), 0)
        self.assertIsNone(get_school_policy(self.school, "unrecognized", None))

    def test_timetable_rejects_teacher_section_and_room_overlaps_and_allows_nonconflicting_slots(self):
        first = create_timetable_slot(
            self.admin, assignment=self.assignment, weekday=0,
            starts_at=time(9), ends_at=time(10), room="R1",
        )
        self.assertEqual(first.section, self.section)
        with self.assertRaises(ValidationError):
            create_timetable_slot(
                self.admin, assignment=self.assignment_b, weekday=0,
                starts_at=time(9, 30), ends_at=time(10, 30), room="R2",
            )
        with self.assertRaises(ValidationError):
            create_timetable_slot(
                self.admin, assignment=TeacherAssignment.objects.create(
                    user=User.objects.create_user(username="other-t", email="other-t@example.test", password="test-password-123"),
                    section=self.section, subject=self.subject_two,
                ), weekday=0, starts_at=time(9, 30), ends_at=time(10, 30), room="R2",
            )
        other_teacher = User.objects.create_user(username="other-t2", email="other-t2@example.test", password="test-password-123")
        SchoolMembership.objects.create(user=other_teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        other_assignment = TeacherAssignment.objects.create(user=other_teacher, section=self.section_b, subject=self.subject)
        with self.assertRaises(ValidationError):
            create_timetable_slot(self.admin, assignment=other_assignment, weekday=0, starts_at=time(9, 30), ends_at=time(10, 30), room="R1")
        allowed = create_timetable_slot(self.admin, assignment=self.assignment_b, weekday=0, starts_at=time(10), ends_at=time(11), room="R2")
        self.assertEqual(TimetableSlot.objects.count(), 2)
        with self.assertRaises(ValidationError):
            TimetableSlot.objects.filter(pk=allowed.pk).update(starts_at=time(9))

    def test_timetable_requires_live_assignment_membership_and_school_admin_creation(self):
        with self.assertRaises(PermissionDenied):
            create_timetable_slot(self.teacher, assignment=self.assignment, weekday=1, starts_at=time(9), ends_at=time(10))
        self.teacher.school_memberships.filter(role=SchoolMembership.Role.TEACHER).update(is_active=False)
        with self.assertRaises(ValidationError):
            TimetableSlot(
                assignment=self.assignment, weekday=1, starts_at=time(9), ends_at=time(10), created_by=self.admin,
            ).full_clean()
        inactive_assignment = TeacherAssignment.objects.create(user=self.admin, section=self.section, subject=self.subject, is_active=False)
        with self.assertRaises(ValidationError):
            TimetableSlot(assignment=inactive_assignment, weekday=1, starts_at=time(9), ends_at=time(10), created_by=self.admin).full_clean()

    def test_notices_enforce_scope_expiry_and_revision_on_published_edits(self):
        save_school_setting(self.admin, self.school, policy_values={"notice_expiry_days": 5})
        notice = create_notice(
            self.admin, school=self.school, title="Opening day", body="Term begins Monday.", publish=True,
        )
        self.assertEqual(notice.expires_at, notice.publish_at + timedelta(days=5))
        old_title = notice.title
        notice.title = "Updated opening day"
        notice.updated_by = self.admin
        notice.save()
        self.assertEqual(notice.revisions.count(), 1)
        self.assertEqual(notice.revisions.get().snapshot["title"], old_title)
        with self.assertRaises(ValidationError):
            create_notice(self.admin, school=self.school, section=self.other_section, title="Bad scope", body="No")
        with self.assertRaises(ValidationError):
            NoticeRevision.objects.filter(notice=notice).delete()
        self.assertEqual(Notice.objects.filter(school=self.school).count(), 1)

    def test_teacher_notice_access_is_limited_to_assigned_section(self):
        teacher_notice = create_notice(
            self.teacher, school=self.school, section=self.section,
            title="Class update", body="Bring your notebook.", publish=True,
        )
        self.assertEqual(teacher_notice.section, self.section)
        with self.assertRaises(PermissionDenied):
            create_notice(self.teacher, school=self.school, title="Schoolwide", body="No section", publish=True)
        without_assignment = User.objects.create_user(
            username="unassigned-teacher", email="unassigned-teacher@example.test", password="test-password-123",
        )
        SchoolMembership.objects.create(user=without_assignment, school=self.school, role=SchoolMembership.Role.TEACHER)
        with self.assertRaises(PermissionDenied):
            create_notice(without_assignment, school=self.school, section=self.section, title="Outside scope", body="No")
        with self.assertRaises(PermissionDenied):
            update_notice(self.teacher, teacher_notice, section=self.other_section)

    def test_teacher_selector_is_exact_active_school_scope_and_accountant_is_finance_only(self):
        self.assertEqual(list(teacher_assignments_for_school(self.teacher, self.school)), [self.assignment, self.assignment_b])
        self.assertEqual(teacher_timetable(self.teacher, self.school).count(), 0)
        self.assertEqual(accountant_finance_only(self.accountant, self.school), {})
        with self.assertRaises(PermissionDenied):
            accountant_finance_only(self.teacher, self.school)
        self.teacher.school_memberships.filter(role=SchoolMembership.Role.TEACHER).update(is_active=False)
        self.assertEqual(teacher_assignments_for_school(self.teacher, self.school).count(), 0)

    def test_audit_failure_rolls_back_setting_timetable_and_notice_mutations(self):
        with patch("oversight.services.record_event", side_effect=RuntimeError("audit offline")):
            with self.assertRaises(RuntimeError):
                save_school_setting(self.admin, self.school, contact_name="Office")
            with self.assertRaises(RuntimeError):
                create_timetable_slot(self.admin, assignment=self.assignment, weekday=2, starts_at=time(9), ends_at=time(10))
            with self.assertRaises(RuntimeError):
                create_notice(self.admin, school=self.school, title="Draft", body="Test", publish=True)
        self.assertFalse(SchoolSetting.objects.filter(school=self.school).exists())
        self.assertFalse(TimetableSlot.objects.exists())
        self.assertFalse(Notice.objects.exists())

        notice = create_notice(self.admin, school=self.school, title="Published", body="First", publish=True)
        with patch("oversight.services.record_event", side_effect=RuntimeError("audit offline")):
            with self.assertRaises(RuntimeError):
                update_notice(self.admin, notice, title="Edited")
        notice.refresh_from_db()
        self.assertEqual(notice.title, "Published")
        self.assertEqual(notice.revisions.count(), 0)

    def test_dashboard_summary_is_scoped_by_active_role_and_policy(self):
        registrar = User.objects.create_user(username="registrar-over", email="registrar-over@example.test", password="test-password-123")
        student_user = User.objects.create_user(username="student-over", email="student-over@example.test", password="test-password-123")
        SchoolMembership.objects.create(user=registrar, school=self.school, role=SchoolMembership.Role.REGISTRAR)
        SchoolMembership.objects.create(user=student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        self.assertEqual(scoped_dashboard_summary(self.accountant, self.school), {"role": "accountant", "balances_by_currency": {}})
        self.assertEqual(scoped_dashboard_summary(registrar, self.school)["pending_admissions"], 0)
        self.assertEqual(scoped_dashboard_summary(student_user, self.school)["published_attempts"], 0)
        with self.assertRaises(PermissionDenied):
            scoped_dashboard_summary(User.objects.create_user(username="no-role", email="no-role@example.test", password="test-password-123"), self.school)

    def test_timetable_admin_changelist_uses_relation_scope_without_cross_school_leaks(self):
        create_timetable_slot(self.admin, assignment=self.assignment, weekday=0, starts_at=time(9), ends_at=time(10))
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])
        client = Client()
        client.force_login(self.admin)
        response = client.get(reverse("admin:oversight_timetableslot_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.section))

        outsider = User.objects.create_user(
            username="other-school-admin", email="other-admin-over@example.test",
            password="test-password-123", is_staff=True,
        )
        SchoolMembership.objects.create(user=outsider, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        client.force_login(outsider)
        response = client.get(reverse("admin:oversight_timetableslot_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, str(self.section))
