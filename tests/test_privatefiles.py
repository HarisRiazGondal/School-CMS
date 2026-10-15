import hashlib
import io
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from learning.models import Assignment, Submission, TeacherAssignment
from learning.services import create_assignment, grade_submission
from schools.models import AcademicYear, School
from students.services import commit_promotion, register_student
from privatefiles.models import PrivateAttachment
from privatefiles.services import create_attachment, sanitize_filename


class PrivateFilesTests(TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.file_settings = override_settings(
            PRIVATE_FILE_ROOT=Path(self.storage.name) / "private",
            PRIVATE_FILE_MAX_BYTES=1024,
            PRIVATE_FILE_SCANNER_COMMAND=["fake-scanner", "{path}"],
        )
        self.file_settings.enable()
        self.addCleanup(self.file_settings.disable)
        self.scanner = patch("privatefiles.services.subprocess.run", return_value=SimpleNamespace(returncode=0))
        self.mock_scan = self.scanner.start()
        self.addCleanup(self.scanner.stop)

        self.school = School.objects.create(name="North School", slug="north-private")
        self.other_school = School.objects.create(name="South School", slug="south-private")
        self.year = AcademicYear.objects.create(school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31))
        self.other_year = AcademicYear.objects.create(school=self.other_school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31))
        self.section = Section.objects.create(school_class=SchoolClass.objects.create(school=self.school, name="Class 4"), academic_year=self.year, name="A")
        self.other_section = Section.objects.create(school_class=SchoolClass.objects.create(school=self.other_school, name="Class 4"), academic_year=self.other_year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        self.other_subject = Subject.objects.create(school=self.other_school, name="Science", code="SCI")
        self.teacher = User.objects.create_user(username="teacher-private", email="teacher-private@example.com", password="secret-test-pass")
        self.other_teacher = User.objects.create_user(username="other-teacher-private", email="other-teacher-private@example.com", password="secret-test-pass")
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.other_teacher, school=self.other_school, role=SchoolMembership.Role.TEACHER)
        TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        self.assignment = create_assignment(self.teacher, self.section, self.subject, title="Classwork", publish=True)
        self.student_user = User.objects.create_user(username="student-private", email="student-private@example.com", password="secret-test-pass")
        SchoolMembership.objects.create(user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        self.student, self.enrollment = register_student(
            user=self.teacher, school=self.school, first_name="A", last_name="Learner",
            academic_year=self.year, section=self.section, roll_number="4A-01", student_user=self.student_user,
        )
        self.submission = Submission.objects.create(assignment=self.assignment, enrollment=self.enrollment, response="answer")
        self.client = Client()

    @staticmethod
    def upload(name="answer.txt", data=b"My private answer\n"):
        return SimpleUploadedFile(name, data)

    @staticmethod
    def pdf(*, active=False):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        if active:
            writer.add_js("app.alert('unsafe')")
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def test_pdf_is_structurally_parsed_and_active_content_is_rejected(self):
        valid = create_attachment(self.teacher, self.upload("worksheet.pdf", self.pdf()), assignment=self.assignment)
        self.assertEqual(valid.content_type, "application/pdf")
        with self.assertRaises(ValidationError):
            create_attachment(self.teacher, self.upload("active.pdf", self.pdf(active=True)), assignment=self.assignment)
        self.assertEqual(PrivateAttachment.objects.count(), 1)

    def test_opaque_private_storage_scanned_and_authorized_attachment_download(self):
        attachment = create_attachment(self.teacher, self.upload("../unsafe-name.txt"), assignment=self.assignment)
        stored = Path(self.storage.name) / "private" / "clean" / attachment.storage_key
        self.assertTrue(stored.is_file())
        self.assertNotIn("unsafe-name", str(stored))
        self.assertNotIn("..", attachment.storage_key)
        self.assertEqual(stored.read_bytes(), b"My private answer\n")
        self.assertEqual(attachment.scan_status, PrivateAttachment.ScanStatus.CLEAN)
        self.assertEqual(attachment.sha256, hashlib.sha256(b"My private answer\n").hexdigest())
        self.mock_scan.assert_called_once()
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("privatefiles:download", args=[attachment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Content-Length"], str(attachment.size))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"My private answer\n")

    def test_upload_pages_accept_authorized_teacher_and_student_posts(self):
        self.client.force_login(self.teacher)
        assignment_url = reverse("privatefiles:assignment-upload", args=[self.assignment.pk])
        self.assertEqual(self.client.get(assignment_url).status_code, 200)
        response = self.client.post(assignment_url, {"file": self.upload()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.assignment.private_attachments.count(), 1)

        self.client.force_login(self.student_user)
        submission_url = reverse("privatefiles:submission-upload", args=[self.submission.pk])
        self.assertEqual(self.client.get(submission_url).status_code, 200)
        response = self.client.post(submission_url, {"file": self.upload()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.submission.private_attachments.count(), 1)

    def test_student_can_read_own_published_assignment_and_submission_files(self):
        assignment_file = create_attachment(self.teacher, self.upload(), assignment=self.assignment)
        submission_file = create_attachment(self.student_user, self.upload(), submission=self.submission)
        self.client.force_login(self.student_user)
        for item in (assignment_file, submission_file):
            with self.subTest(item=item.pk):
                self.assertEqual(self.client.get(reverse("privatefiles:download", args=[item.pk])).status_code, 200)

    def test_historical_submission_file_remains_readable_after_promotion_but_upload_stops(self):
        attachment = create_attachment(self.student_user, self.upload(), submission=self.submission)
        target_year = AcademicYear.objects.create(
            school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31),
        )
        target_section = Section.objects.create(
            school_class=SchoolClass.objects.create(school=self.school, name="Class 5"),
            academic_year=target_year, name="A",
        )
        commit_promotion(
            user=self.teacher, source=self.enrollment, outcome="promoted",
            target_section=target_section, target_year=target_year, roll_number="5A-01",
        )
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("privatefiles:download", args=[attachment.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("privatefiles:submission-upload", args=[self.submission.pk])).status_code, 403)
        history = self.client.get(reverse("privatefiles:my-files"))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "answer.txt")

    def test_students_cannot_upload_assignment_level_files(self):
        with self.assertRaises(PermissionDenied):
            create_attachment(self.student_user, self.upload(), assignment=self.assignment)

    def test_other_students_and_unassigned_staff_cannot_read_submission_files(self):
        attachment = create_attachment(self.student_user, self.upload(), submission=self.submission)
        outsider = User.objects.create_user(username="outsider-private", email="outsider-private@example.com", password="secret-test-pass")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("privatefiles:download", args=[attachment.pk])).status_code, 403)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse("privatefiles:download", args=[attachment.pk])).status_code, 403)

    def test_storage_rejects_symlink_root_and_wide_permissions_when_chmod_fails(self):
        from privatefiles.services import _root
        target = Path(self.storage.name) / "target"
        target.mkdir()
        symlink = Path(self.storage.name) / "linked-private"
        symlink.symlink_to(target, target_is_directory=True)
        with override_settings(PRIVATE_FILE_ROOT=symlink):
            with self.assertRaises(ValidationError):
                _root()
        unsafe = Path(self.storage.name) / "unsafe-private"
        unsafe.mkdir(mode=0o755)
        unsafe.chmod(0o755)
        with override_settings(PRIVATE_FILE_ROOT=unsafe):
            with patch("pathlib.Path.chmod", side_effect=PermissionError("cannot secure directory")):
                with self.assertRaises(ValidationError):
                    _root()

    def test_download_rejects_modified_file_bytes(self):
        attachment = create_attachment(self.teacher, self.upload(), assignment=self.assignment)
        stored = Path(self.storage.name) / "private" / "clean" / attachment.storage_key
        stored.write_bytes(b"X" * len(b"My private answer\n"))
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("privatefiles:download", args=[attachment.pk])).status_code, 404)

    def test_upload_rejects_bad_extensions_signatures_oversize_and_missing_scanner(self):
        with self.assertRaises(ValidationError):
            create_attachment(self.teacher, self.upload("script.exe", b"plain"), assignment=self.assignment)
        with self.assertRaises(ValidationError):
            create_attachment(self.teacher, self.upload("fake.pdf", b"not a pdf"), assignment=self.assignment)
        with self.assertRaises(ValidationError):
            create_attachment(self.teacher, self.upload("large.txt", b"x" * 1025), assignment=self.assignment)
        with override_settings(PRIVATE_FILE_SCANNER_COMMAND=None):
            with self.assertRaises(ValidationError):
                create_attachment(self.teacher, self.upload(), assignment=self.assignment)
        self.assertEqual(PrivateAttachment.objects.count(), 0)
        self.assertFalse(any(path.is_file() for path in (Path(self.storage.name) / "private").rglob("*")))

    def test_scanner_infection_is_quarantined_and_never_downloadable(self):
        self.mock_scan.return_value = SimpleNamespace(returncode=1)
        attachment = create_attachment(self.student_user, self.upload(), submission=self.submission)
        quarantine_path = Path(self.storage.name) / "private" / "quarantine" / attachment.storage_key
        self.assertTrue(quarantine_path.exists())
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("privatefiles:download", args=[attachment.pk])).status_code, 403)

    def test_grading_during_scan_wins_and_cleans_staged_submission_file(self):
        def grade_while_scanning(*args, **kwargs):
            grade_submission(self.teacher, self.submission, grade="80.00")
            return SimpleNamespace(returncode=0)
        self.mock_scan.side_effect = grade_while_scanning
        with self.assertRaises(PermissionDenied):
            create_attachment(self.student_user, self.upload(), submission=self.submission)
        self.assertEqual(PrivateAttachment.objects.count(), 0)
        private_root = Path(self.storage.name) / "private"
        self.assertFalse(any(path.is_file() for path in private_root.rglob("*")))

    def test_late_submission_policy_can_block_additional_files(self):
        self.assignment.due_at = timezone.now() - timedelta(minutes=1)
        self.assignment.save(update_fields=["due_at"])
        with patch("learning.services._school_policy", return_value=False):
            with self.assertRaises(PermissionDenied):
                create_attachment(self.student_user, self.upload(), submission=self.submission)
        self.assertEqual(PrivateAttachment.objects.count(), 0)

    def test_database_audit_failure_rolls_back_metadata_and_removes_file(self):
        with patch("privatefiles.services.record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                create_attachment(self.teacher, self.upload(), assignment=self.assignment)
        private_root = Path(self.storage.name) / "private"
        self.assertEqual(PrivateAttachment.objects.count(), 0)
        self.assertFalse(any(path.is_file() for path in private_root.rglob("*")))

    def test_scanner_execution_error_fails_closed_and_cleans_staging_file(self):
        self.mock_scan.side_effect = OSError("scanner missing")
        with self.assertRaises(ValidationError):
            create_attachment(self.teacher, self.upload(), assignment=self.assignment)
        private_root = Path(self.storage.name) / "private"
        self.assertEqual(PrivateAttachment.objects.count(), 0)
        self.assertFalse(any(path.is_file() for path in private_root.rglob("*")))

    def test_filename_sanitization_never_retains_path_components_or_header_controls(self):
        safe = sanitize_filename("../../folder/\r\nsecret.txt")
        self.assertNotIn("/", safe)
        self.assertNotIn("\\", safe)
        self.assertNotIn("\r", safe)
        self.assertNotIn("\n", safe)
