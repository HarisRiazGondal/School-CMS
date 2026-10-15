from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from learning.models import AttendanceCorrectionRequest, AttendanceRecord
from learning.services import review_attendance_correction
from oversight.models import Notice, SchoolSetting, TimetableSlot
from schools.models import School
from students.models import AdmissionApplication
from students.services import decide_admission_application


@override_settings(DEBUG=True)
class DemoSeed87Tests(TestCase):
    password = "synthetic-demo-password"

    def seed(self):
        call_command("seed_demo", password=self.password, verbosity=0)

    def test_seed_has_idempotent_admissions_attendance_and_oversight_fixtures(self):
        self.seed()
        school = School.objects.get(slug="demo-school")
        admin = User.objects.get(username="demo-admin")

        application = AdmissionApplication.objects.get(
            school=school, first_name="Jordan", last_name="Applicant",
        )
        self.assertEqual(application.status, AdmissionApplication.Status.PENDING)
        self.assertIsNone(application.student_id)

        record = AttendanceRecord.objects.get(
            enrollment__student__user__username="demo-student",
            session__section__school_class__school=school,
        )
        self.assertEqual(record.status, AttendanceRecord.Status.ABSENT)
        self.assertEqual(record.session.date, timezone.localdate() - timedelta(days=1))
        correction = record.correction_requests.get()
        self.assertEqual(correction.status, AttendanceCorrectionRequest.Status.PENDING)
        self.assertEqual(correction.new_status, AttendanceRecord.Status.PRESENT)

        setting = SchoolSetting.objects.get(school=school)
        self.assertEqual(setting.timezone, "Asia/Karachi")
        self.assertEqual(setting.policy_values["attendance_correction_days"], 7)
        slot = TimetableSlot.objects.get(assignment__section__school_class__school=school)
        notice = Notice.objects.get(school=school, title="Welcome to the new school year")
        self.assertTrue(notice.is_published)

        self.seed()
        self.assertEqual(AdmissionApplication.objects.filter(school=school).count(), 1)
        self.assertEqual(AttendanceRecord.objects.filter(session__section__school_class__school=school).count(), 1)
        self.assertEqual(record.correction_requests.count(), 1)
        self.assertEqual(SchoolSetting.objects.get(school=school).revisions.count(), 1)
        self.assertEqual(TimetableSlot.objects.filter(assignment__section__school_class__school=school).count(), 1)
        self.assertEqual(Notice.objects.filter(school=school).count(), 1)

        # The date-relative fixture is created once; next-day reruns do not
        # accumulate another attendance session and correction request.
        with patch(
            "schools.management.commands.seed_demo.timezone.localdate",
            return_value=timezone.localdate() + timedelta(days=1),
        ):
            self.seed()
        self.assertEqual(AttendanceRecord.objects.filter(session__section__school_class__school=school).count(), 1)
        self.assertEqual(record.correction_requests.count(), 1)

        # User changes and finalized histories survive future seed runs.
        setting.timezone = "UTC"
        setting.policy_values = {"attendance_correction_days": 5}
        setting.updated_by = admin
        setting.save()
        notice.body = "Operator-edited synthetic notice."
        notice.save()
        decide_admission_application(
            user=admin, application=application, decision=AdmissionApplication.Status.REJECTED,
            note="Synthetic demo decision.",
        )
        review_attendance_correction(
            admin, correction, approve=True, review_note="Synthetic demo approval.",
        )
        record.refresh_from_db()
        self.assertEqual(record.status, AttendanceRecord.Status.PRESENT)

        self.seed()
        setting.refresh_from_db()
        notice.refresh_from_db()
        application.refresh_from_db()
        correction.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(setting.timezone, "UTC")
        self.assertEqual(setting.policy_values["attendance_correction_days"], 5)
        self.assertEqual(setting.revisions.count(), 2)
        self.assertEqual(notice.body, "Operator-edited synthetic notice.")
        self.assertEqual(application.status, AdmissionApplication.Status.REJECTED)
        self.assertEqual(correction.status, AttendanceCorrectionRequest.Status.APPROVED)
        self.assertEqual(record.status, AttendanceRecord.Status.PRESENT)

