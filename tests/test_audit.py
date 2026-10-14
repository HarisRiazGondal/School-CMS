from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from audit.models import AuditEvent
from audit.services import record_event
from schools.models import School


class AuditEventTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north")

    def test_record_event_persists_actor_and_school(self):
        actor = User.objects.create_user(
            username="registrar", email="registrar@example.test", password="safe-test-password"
        )
        event = record_event(
            school=self.school,
            actor=actor,
            action="student.registered",
            object_type="student",
            object_id="student-123",
            details={"student_code": "STU-2026-001", "source": "office"},
        )

        event.refresh_from_db()
        self.assertEqual(event.school, self.school)
        self.assertEqual(event.actor, actor)
        self.assertEqual(event.action, "student.registered")
        self.assertEqual(event.object_type, "student")
        self.assertEqual(event.object_id, "student-123")
        self.assertEqual(event.details["student_code"], "STU-2026-001")
        self.assertIsNotNone(event.timestamp)

    def test_record_event_rejects_sensitive_detail_keys(self):
        for details in (
            {"password": "do-not-store"},
            {"credentials": {"refresh_token": "do-not-store"}},
            {"session_key": "do-not-store"},
        ):
            with self.subTest(details=details), self.assertRaisesRegex(ValidationError, "Sensitive key"):
                record_event(
                    school=self.school,
                    action="user.changed",
                    object_type="user",
                    object_id="1",
                    details=details,
                )

    def test_audit_event_is_append_only_through_model_methods(self):
        event = record_event(
            school=self.school,
            action="student.registered",
            object_type="student",
            object_id="1",
        )

        event.action = "student.deleted"
        with self.assertRaisesRegex(ValidationError, "append-only"):
            event.save()
        with self.assertRaisesRegex(ValidationError, "append-only"):
            event.delete()
