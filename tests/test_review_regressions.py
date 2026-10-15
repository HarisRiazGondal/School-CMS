from datetime import date, time
from types import SimpleNamespace

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone
from django.urls import reverse

from accounts.models import SchoolMembership, User, active_school_memberships
from academics.models import SchoolClass, Section, Subject
from assessment.services import published_transcript
from audit.models import AuditEvent
from audit.services import record_event
from finance.services import _require_invoice_read, fee_statement
from learning.models import AttendanceCorrectionRequest, AttendanceRecord, TeacherAssignment
from learning.services import create_attendance, request_attendance_correction
from oversight.admin import TimetableSlotAdmin
from oversight.models import Notice, NoticeRevision, SchoolSetting, SchoolSettingRevision, TimetableSlot
from oversight.services import create_timetable_slot
from schools.models import AcademicYear, School
from students.models import Enrollment, PromotionDecision
from students.services import register_student


class ReviewRegressionTests(TestCase):
    """Regression coverage for authorization freshness and write-path bypasses."""

    def setUp(self):
        self.school = School.objects.create(name="Review School", slug="review-school")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.klass = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.section = Section.objects.create(school_class=self.klass, academic_year=self.year, name="A")
        self.admin = User.objects.create_user(username="review-admin", email="review-admin@example.test", password="long-safe-password")
        self.registrar = User.objects.create_user(username="review-registrar", email="review-registrar@example.test", password="long-safe-password")
        self.student_user = User.objects.create_user(username="review-student", email="review-student@example.test", password="long-safe-password")
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.registrar, school=self.school, role=SchoolMembership.Role.REGISTRAR)
        self.student_membership = SchoolMembership.objects.create(
            user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT,
        )
        self.student, self.enrollment = register_student(
            user=self.admin, school=self.school, first_name="Review", academic_year=self.year,
            section=self.section, roll_number="4A-01", student_user=self.student_user,
        )

    def test_cached_school_membership_does_not_survive_database_deactivation(self):
        self.student_user = User.objects.prefetch_related("school_memberships").get(pk=self.student_user.pk)
        self.assertEqual(list(active_school_memberships(self.student_user).values_list("pk", flat=True)), [self.student_membership.pk])
        SchoolMembership.objects.filter(pk=self.student_membership.pk).update(is_active=False)
        self.assertFalse(active_school_memberships(self.student_user).exists())
        with self.assertRaises(PermissionDenied):
            published_transcript(self.student, self.student_user)
        with self.assertRaises(PermissionDenied):
            fee_statement(user=self.student_user, student=self.student)
        fake_invoice = SimpleNamespace(school=self.school, enrollment=SimpleNamespace(student=self.student))
        with self.assertRaises(PermissionDenied):
            _require_invoice_read(self.student_user, fake_invoice)

    def test_audit_queryset_cannot_bypass_append_only_model_guards(self):
        event = record_event(
            school=self.school, action="review.created", object_type="review", object_id="1",
        )
        replacement = AuditEvent(
            school=self.school, action="review.forged", object_type="review", object_id="2",
        )
        operations = (
            lambda: AuditEvent.objects.filter(pk=event.pk).update(action="review.forged"),
            lambda: AuditEvent.objects.filter(pk=event.pk).delete(),
            lambda: AuditEvent.objects.bulk_update([event], ["action"]),
            lambda: AuditEvent.objects.bulk_create([replacement]),
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()
        event.refresh_from_db()
        self.assertEqual(event.action, "review.created")
        self.assertEqual(AuditEvent.objects.filter(object_type="review").count(), 1)

    def test_oversight_revisions_and_snapshots_cannot_be_bypassed_by_querysets(self):
        setting = SchoolSetting.objects.create(school=self.school)
        notice = Notice.objects.create(
            school=self.school, title="First", body="Initial notice", audience=Notice.Audience.ALL,
            publish_at=timezone.now(), is_published=True, created_by=self.admin,
        )
        notice.title = "Second"
        notice.save()
        revision = notice.revisions.get()
        guarded_operations = (
            lambda: SchoolSetting.objects.filter(pk=setting.pk).update(contact_name="forged"),
            lambda: SchoolSettingRevision.objects.filter(setting=setting).delete(),
            lambda: Notice.objects.filter(pk=notice.pk).update(title="forged"),
            lambda: NoticeRevision.objects.filter(pk=revision.pk).delete(),
        )
        for operation in guarded_operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()
        self.assertEqual(SchoolSetting.objects.get(pk=setting.pk).contact_name, "")
        self.assertEqual(Notice.objects.get(pk=notice.pk).title, "Second")
        self.assertEqual(notice.revisions.count(), 1)

    def test_timetable_queryset_mutation_cannot_bypass_overlap_validation(self):
        teacher = User.objects.create_user(username="review-teacher", email="review-teacher@example.test", password="long-safe-password")
        SchoolMembership.objects.create(user=teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        second_section = Section.objects.create(school_class=self.klass, academic_year=self.year, name="B")
        subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        first_assignment = TeacherAssignment.objects.create(user=teacher, section=self.section, subject=subject)
        second_assignment = TeacherAssignment.objects.create(user=teacher, section=second_section, subject=subject)
        first = TimetableSlot.objects.create(
            assignment=first_assignment, weekday=TimetableSlot.Weekday.MONDAY,
            starts_at=time(9), ends_at=time(10), created_by=self.admin,
        )
        second = TimetableSlot.objects.create(
            assignment=second_assignment, weekday=TimetableSlot.Weekday.MONDAY,
            starts_at=time(10), ends_at=time(11), created_by=self.admin,
        )
        with self.assertRaises(ValidationError):
            TimetableSlot.objects.filter(pk=second.pk).update(starts_at=time(9, 30))
        second.refresh_from_db()
        self.assertEqual(second.starts_at, time(10))

    def test_attendance_correction_history_cannot_be_forged_or_deleted_by_queryset(self):
        from learning.services import school_local_date

        session = create_attendance(
            self.admin, self.section, school_local_date(self.school),
            {str(self.enrollment.pk): AttendanceRecord.Status.PRESENT},
        )
        record = session.records.get(enrollment=self.enrollment)
        correction = request_attendance_correction(
            self.admin, record, new_status=AttendanceRecord.Status.ABSENT, reason="Clerical correction",
        )
        forged = AttendanceCorrectionRequest(
            attendance_record=record, old_status=record.status, new_status=AttendanceRecord.Status.ABSENT,
            reason="Forged second request", requested_by=self.admin,
        )
        operations = (
            lambda: AttendanceCorrectionRequest.objects.filter(pk=correction.pk).update(status="approved"),
            lambda: AttendanceCorrectionRequest.objects.filter(pk=correction.pk).delete(),
            lambda: AttendanceCorrectionRequest.objects.bulk_update([correction], ["status"]),
            lambda: AttendanceCorrectionRequest.objects.bulk_create([forged]),
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()
        correction.refresh_from_db()
        self.assertEqual(correction.status, AttendanceCorrectionRequest.Status.PENDING)
        self.assertEqual(AttendanceCorrectionRequest.objects.count(), 1)

    def test_conditional_batch_preview_carries_reason_through_admin_confirmation(self):
        next_year = AcademicYear.objects.create(
            school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31),
        )
        next_class = SchoolClass.objects.create(school=self.school, name="Class 5")
        next_section = Section.objects.create(school_class=next_class, academic_year=next_year, name="A")
        url = reverse("students:batch-promotion", kwargs={"school_slug": self.school.slug})
        payload = {
            "source_id": str(self.enrollment.pk), "outcome": "conditional",
            "target_year": str(next_year.pk), "target_section": str(next_section.pk),
            "roll_number": self.enrollment.roll_number, "condition_reason": "Review attendance monthly",
        }
        client = Client()
        client.force_login(self.registrar)
        preview = client.post(url, payload)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Review attendance monthly")
        self.assertNotContains(preview, "Confirm entire batch")
        client.force_login(self.admin)
        admin_preview = client.post(url, payload)
        self.assertContains(admin_preview, "Confirm entire batch")
        committed = client.post(url, {**payload, "confirm": "1"})
        self.assertEqual(committed.status_code, 302)
        self.enrollment.refresh_from_db()
        decision = PromotionDecision.objects.get(source_enrollment=self.enrollment)
        self.assertEqual(self.enrollment.status, Enrollment.Status.CONDITIONAL)
        self.assertEqual(decision.condition_reason, "Review attendance monthly")
        self.assertEqual(decision.actor, self.admin)

    def test_conditional_single_student_preview_passes_reason_to_service(self):
        next_year = AcademicYear.objects.create(
            school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31),
        )
        next_class = SchoolClass.objects.create(school=self.school, name="Class 5")
        next_section = Section.objects.create(school_class=next_class, academic_year=next_year, name="A")
        url = reverse("students:promotion-preview", kwargs={
            "school_slug": self.school.slug, "student_code": self.student.student_code,
            "year_name": self.year.name,
        })
        client = Client()
        client.force_login(self.admin)
        response = client.post(url, {
            "outcome": "conditional", "target_year": str(next_year.pk),
            "target_section": str(next_section.pk), "roll_number": self.enrollment.roll_number,
            "condition_reason": "Review attendance monthly",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm outcome")
        self.assertContains(response, "Review attendance monthly")

    def test_student_timetable_hides_slot_after_teacher_membership_is_deactivated(self):
        teacher = User.objects.create_user(username="scheduled-teacher", email="scheduled-teacher@example.test", password="long-safe-password")
        membership = SchoolMembership.objects.create(
            user=teacher, school=self.school, role=SchoolMembership.Role.TEACHER,
        )
        subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        assignment = TeacherAssignment.objects.create(user=teacher, section=self.section, subject=subject)
        create_timetable_slot(
            self.admin, assignment=assignment, weekday=TimetableSlot.Weekday.MONDAY,
            starts_at=time(9), ends_at=time(10), room="Science lab",
        )
        client = Client()
        client.force_login(self.student_user)
        url = reverse("oversight:dashboard", kwargs={"school_slug": self.school.slug})
        before = client.get(url)
        self.assertContains(before, "Science")
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        after = client.get(url)
        self.assertEqual(after.status_code, 200)
        self.assertNotContains(after, "Science")

    def test_timetable_admin_changelist_queryset_uses_related_school_scope(self):
        request = RequestFactory().get("/admin/oversight/timetableslot/")
        request.user = self.admin
        rows = TimetableSlotAdmin(TimetableSlot, admin.site).get_queryset(request)
        self.assertEqual(rows.count(), 0)

