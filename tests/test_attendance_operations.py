from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from audit.models import AuditEvent
from learning.models import (
    Assignment, AttendanceCorrectionRequest, AttendanceRecord, AttendanceSession,
    TeacherAssignment,
)
from learning.services import (
    auto_reject_stale_attendance_corrections, create_attendance, create_assignment,
    grade_submission, request_attendance_correction, review_attendance_correction,
    submit_assignment,
)
from schools.models import AcademicYear, School
from students.services import register_student
from oversight.services import save_school_setting


class AttendanceOperationsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north-ops")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        school_class = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.section = Section.objects.create(school_class=school_class, academic_year=self.year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        self.teacher = User.objects.create_user(username="ops-teacher", email="ops-teacher@example.com", password="safe-test-pass")
        self.admin = User.objects.create_user(username="ops-admin", email="ops-admin@example.com", password="safe-test-pass")
        self.student_user = User.objects.create_user(username="ops-student", email="ops-student@example.com", password="safe-test-pass")
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.REGISTRAR)
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        self.student, self.enrollment = register_student(
            user=self.teacher, school=self.school, first_name="Ada", last_name="Learner",
            academic_year=self.year, section=self.section, roll_number="4A-01", student_user=self.student_user,
        )
        self.session = create_attendance(
            self.teacher, self.section, date(2026, 10, 14), {str(self.enrollment.pk): "present"},
        )
        self.record = self.session.records.get(enrollment=self.enrollment)
        self.client = Client()

    def test_attendance_records_reject_model_queryset_bulk_and_forged_pk_mutations(self):
        with self.assertRaises(ValidationError):
            AttendanceRecord(session=self.session, enrollment=self.enrollment, status="absent").save()
        with self.assertRaises(ValidationError):
            AttendanceRecord(pk=self.record.pk, session=self.session, enrollment=self.enrollment, status="absent").save()
        with self.assertRaises(ValidationError):
            self.record.save()
        with self.assertRaises(ValidationError):
            AttendanceRecord.objects.filter(pk=self.record.pk).update(status="absent")
        with self.assertRaises(ValidationError):
            AttendanceRecord.objects.bulk_create([AttendanceRecord(session=self.session, enrollment=self.enrollment, status="absent")])
        self.record.status = "absent"
        with self.assertRaises(ValidationError):
            AttendanceRecord.objects.bulk_update([self.record], ["status"])
        with self.assertRaises(ValidationError):
            AttendanceRecord.objects.filter(pk=self.record.pk).delete()
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, AttendanceRecord.Status.PRESENT)

    def test_attendance_sessions_cannot_be_recontextualized_after_creation(self):
        with self.assertRaises(ValidationError):
            AttendanceSession(pk=self.session.pk, section=self.section, date=date(2026, 10, 15), created_by=self.teacher).save()
        self.session.date = date(2026, 10, 15)
        with self.assertRaises(ValidationError):
            self.session.save()
        with self.assertRaises(ValidationError):
            AttendanceSession.objects.filter(pk=self.session.pk).update(date=date(2026, 10, 15))
        with self.assertRaises(ValidationError):
            AttendanceSession.objects.filter(pk=self.session.pk).delete()
        self.session.refresh_from_db()
        self.assertEqual(self.session.date, date(2026, 10, 14))

    def test_request_and_approval_snapshot_old_new_reason_and_reviewer_attribution(self):
        correction = request_attendance_correction(
            self.teacher, self.record, new_status=AttendanceRecord.Status.LATE,
            new_note="Arrived after roll call", reason="Teacher marked the wrong row.",
        )
        self.assertEqual((correction.old_status, correction.old_note), ("present", ""))
        self.assertEqual((correction.new_status, correction.new_note), ("late", "Arrived after roll call"))
        self.assertEqual(correction.requested_by, self.teacher)
        with self.assertRaises(ValidationError):
            request_attendance_correction(self.teacher, self.record, new_status="absent", reason="Duplicate pending request")
        with self.assertRaises(ValidationError):
            AttendanceCorrectionRequest.objects.filter(pk=correction.pk).update(status="approved")
        forged = AttendanceCorrectionRequest.objects.get(pk=correction.pk)
        forged.status = AttendanceCorrectionRequest.Status.APPROVED
        with self.assertRaises(ValidationError):
            forged.save()
        correction = review_attendance_correction(self.admin, correction, approve=True, review_note="Verified against register.")
        self.record.refresh_from_db()
        correction.refresh_from_db()
        self.assertEqual((self.record.status, self.record.note), ("late", "Arrived after roll call"))
        self.assertEqual(correction.status, AttendanceCorrectionRequest.Status.APPROVED)
        self.assertEqual(correction.reviewed_by, self.admin)
        self.assertIsNotNone(correction.reviewed_at)
        self.assertEqual(correction.review_note, "Verified against register.")
        self.assertEqual(correction.reason, "Teacher marked the wrong row.")
        self.assertTrue(AuditEvent.objects.filter(action="learning.attendance_correction_requested", actor=self.teacher).exists())
        self.assertTrue(AuditEvent.objects.filter(action="learning.attendance_correction_approved", actor=self.admin).exists())
        with self.assertRaises(ValidationError):
            correction.delete()

    def test_rejection_leaves_record_unchanged_and_unassigned_reviewer_is_denied(self):
        correction = request_attendance_correction(self.teacher, self.record, new_status="absent", reason="Wrong roll mark")
        with self.assertRaises(PermissionDenied):
            review_attendance_correction(self.teacher, correction, approve=True)
        review_attendance_correction(self.admin, correction, approve=False, review_note="Register confirms present.")
        self.record.refresh_from_db()
        correction.refresh_from_db()
        self.assertEqual(self.record.status, AttendanceRecord.Status.PRESENT)
        self.assertEqual(correction.status, AttendanceCorrectionRequest.Status.REJECTED)
        self.assertEqual(correction.reviewed_by, self.admin)

    def test_stale_requests_are_auto_rejected_using_school_timezone_and_window(self):
        save_school_setting(self.admin, self.school, timezone="UTC", policy_values={"attendance_correction_days": 7})
        session = create_attendance(self.teacher, self.section, date(2026, 10, 7), {str(self.enrollment.pk): "present"})
        old_record = session.records.get()
        with patch("learning.services.school_local_date", return_value=date(2026, 10, 15)):
            with self.assertRaises(ValidationError):
                request_attendance_correction(self.teacher, old_record, new_status="absent", reason="Too old")
        allowed_session = create_attendance(self.teacher, self.section, date(2026, 10, 8), {str(self.enrollment.pk): "present"})
        allowed = request_attendance_correction(self.teacher, allowed_session.records.get(), new_status="absent", reason="Within seven days")
        with patch("learning.services.school_local_date", return_value=date(2026, 10, 16)):
            self.assertEqual(auto_reject_stale_attendance_corrections(self.school), [allowed.pk])
        allowed.refresh_from_db()
        self.assertEqual(allowed.status, AttendanceCorrectionRequest.Status.AUTO_REJECTED)
        self.assertIsNone(allowed.reviewed_by)
        self.assertIsNotNone(allowed.reviewed_at)

    def test_local_date_uses_configured_school_timezone(self):
        save_school_setting(self.admin, self.school, timezone="Pacific/Kiritimati")
        instant = datetime(2026, 10, 14, 12, 30, tzinfo=dt_timezone.utc)
        with patch("learning.services.timezone.now", return_value=instant):
            from learning.services import school_local_date
            self.assertEqual(school_local_date(self.school), date(2026, 10, 15))

    def test_database_activation_state_overrides_cached_user_and_school_objects(self):
        stale_user = User.objects.get(pk=self.teacher.pk)
        stale_school = School.objects.get(pk=self.school.pk)
        User.objects.filter(pk=stale_user.pk).update(is_active=False)
        School.objects.filter(pk=stale_school.pk).update(is_active=False)
        from learning.services import can_manage_section
        self.assertFalse(can_manage_section(stale_user, self.section))

    def test_student_history_and_policy_protected_submission_results_and_workload(self):
        today = timezone.now()
        future = today + timedelta(days=2)
        past = today - timedelta(days=2)
        assignment = create_assignment(
            self.teacher, self.section, self.subject, title="Upcoming work", due_at=future, publish=True,
        )
        late = create_assignment(
            self.teacher, self.section, self.subject, title="Past due work", due_at=past, publish=True,
        )
        default_late = create_assignment(
            self.teacher, self.section, self.subject, title="Default late work", due_at=past, publish=True,
        )
        submit_assignment(self.student_user, default_late, "default permits late work")
        save_school_setting(self.admin, self.school, policy_values={
            "late_submission_allowed": False, "student_results_visible": False,
        })
        with self.assertRaises(ValidationError):
            submit_assignment(self.student_user, late, "late answer")
        saved = submit_assignment(self.student_user, assignment, "finished answer")
        grade_submission(self.teacher, saved, grade=Decimal("91.00"), feedback="Good work")

        self.client.force_login(self.student_user)
        history = self.client.get(reverse("learning:student-attendance-history"))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Oct. 14, 2026")
        detail = self.client.get(reverse("learning:assignment-detail", args=[assignment.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "91.00")
        self.assertNotContains(detail, "Good work")
        home = self.client.get(reverse("learning:home"))
        self.assertContains(home, "Past due work")
        self.assertContains(home, "Upcoming work")

    def test_correction_views_are_school_scoped_and_admin_decision_is_reviewable(self):
        correction = request_attendance_correction(self.teacher, self.record, new_status="absent", reason="Misread tick")
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("learning:attendance-correction-queue")).status_code, 403)
        self.client.force_login(self.admin)
        queue = self.client.get(reverse("learning:attendance-correction-queue"))
        self.assertEqual(queue.status_code, 200)
        self.assertContains(queue, "Misread tick")
        response = self.client.post(reverse("learning:attendance-correction-review", args=[correction.pk]), {
            "decision": "approve", "review_note": "Checked register",
        })
        self.assertEqual(response.status_code, 302)
        correction.refresh_from_db()
        self.assertEqual(correction.status, AttendanceCorrectionRequest.Status.APPROVED)
