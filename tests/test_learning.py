from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from learning.models import AttendanceRecord, AttendanceSession, TeacherAssignment
from learning.services import create_assignment, create_attendance
from schools.models import AcademicYear, School
from students.services import register_student


class LearningAuthorizationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north")
        self.other_school = School.objects.create(name="South School", slug="south")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.other_year = AcademicYear.objects.create(
            school=self.other_school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.school_class = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.other_class = SchoolClass.objects.create(school=self.other_school, name="Class 4")
        self.section = Section.objects.create(school_class=self.school_class, academic_year=self.year, name="A")
        self.other_section = Section.objects.create(school_class=self.other_class, academic_year=self.other_year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        self.other_subject = Subject.objects.create(school=self.other_school, name="Science", code="SCI")
        self.teacher = User.objects.create_user(username="teach", email="teach@example.com", password="secret-test-pass")
        self.unassigned_teacher = User.objects.create_user(username="otherteach", email="otherteach@example.com", password="secret-test-pass")
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.unassigned_teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.unassigned_teacher, school=self.school, role=SchoolMembership.Role.REGISTRAR)
        self.assignment_link = TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        self.student_user = User.objects.create_user(username="student", email="student@example.com", password="secret-test-pass")
        SchoolMembership.objects.create(user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        self.student, self.enrollment = register_student(
            user=self.unassigned_teacher, school=self.school, first_name="Ada", last_name="Learner",
            academic_year=self.year, section=self.section, roll_number="4A-01", student_user=self.student_user,
        )
        self.client = Client()

    def _assignment(self, *, section=None, subject=None):
        return create_assignment(
            self.teacher, section or self.section, subject or self.subject,
            title="Read chapter 2", instructions="Answer the questions.", publish=True,
        )

    def test_wrong_teacher_assignment_is_denied(self):
        with self.assertRaises(PermissionDenied):
            create_assignment(self.unassigned_teacher, self.section, self.subject, title="No access")
        with self.assertRaises(PermissionDenied):
            create_attendance(self.unassigned_teacher, self.section, date(2026, 10, 1), {str(self.enrollment.pk): "present"})

    def test_cross_school_teacher_assignment_is_rejected(self):
        assignment = TeacherAssignment(user=self.teacher, section=self.section, subject=self.other_subject)
        with self.assertRaises(ValidationError):
            assignment.full_clean()
        with self.assertRaises(PermissionDenied):
            create_assignment(self.teacher, self.other_section, self.other_subject, title="Cross-school")

    def test_attendance_is_unique_and_duplicate_post_does_not_replace_records(self):
        session = create_attendance(self.teacher, self.section, date(2026, 10, 5), {str(self.enrollment.pk): "present"})
        self.assertEqual(session.records.get(enrollment=self.enrollment).status, AttendanceRecord.Status.PRESENT)
        with self.assertRaises(ValidationError):
            create_attendance(self.teacher, self.section, date(2026, 10, 5), {str(self.enrollment.pk): "absent"})
        self.assertEqual(AttendanceSession.objects.filter(section=self.section, date=date(2026, 10, 5)).count(), 1)
        self.assertEqual(session.records.get(enrollment=self.enrollment).status, AttendanceRecord.Status.PRESENT)

    def test_attendance_requires_exact_roster(self):
        with self.assertRaises(ValidationError):
            create_attendance(self.teacher, self.section, date(2026, 10, 6), {})

    def test_students_can_read_and_submit_only_for_their_own_assignment(self):
        assignment = self._assignment()
        outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="secret-test-pass")
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("learning:assignment-detail", args=[assignment.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("learning:assignment-submit", args=[assignment.pk]), {"response": "My answer"})
        self.assertEqual(response.status_code, 302)
        submission = assignment.submissions.get(enrollment=self.enrollment)
        self.assertEqual(submission.response, "My answer")
        self.client.force_login(outsider)
        response = self.client.get(reverse("learning:assignment-detail", args=[assignment.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("learning:assignment-submit", args=[assignment.pk]), {"response": "Not mine"})
        self.assertEqual(response.status_code, 403)

    def test_inactive_school_is_denied_for_teachers_and_students(self):
        assignment = self._assignment()
        self.school.is_active = False
        self.school.save(update_fields=["is_active"])
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("learning:attendance-list", args=[self.section.pk])).status_code, 403)
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("learning:assignment-detail", args=[assignment.pk])).status_code, 403)

    def test_role_home_pages_render_with_scoped_data(self):
        self.client.force_login(self.teacher)
        teacher_home = self.client.get(reverse("learning:home"))
        self.assertEqual(teacher_home.status_code, 200)
        self.assertContains(teacher_home, "Class 4")
        self.client.force_login(self.student_user)
        student_home = self.client.get(reverse("learning:home"))
        self.assertEqual(student_home.status_code, 200)
        self.assertContains(student_home, "4A-01")
        admin = User.objects.create_user(username="schooladmin", email="admin@example.com", password="secret-test-pass")
        SchoolMembership.objects.create(user=admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("learning:home")).status_code, 200)

    def test_teacher_learning_pages_render_and_assignment_can_be_created(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("learning:attendance-list", args=[self.section.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("learning:attendance-entry", args=[self.section.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("learning:assignment-create")).status_code, 200)
        response = self.client.post(reverse("learning:assignment-create"), {
            "section": self.section.pk, "subject": self.subject.pk,
            "title": "Practice", "instructions": "Try these.", "due_at": "", "publish": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.section.learning_assignments.filter(title="Practice", is_published=True).exists())
        response = self.client.post(reverse("learning:attendance-entry", args=[self.section.pk]), {
            "date": "2026-10-07", f"status_{self.enrollment.pk}": "late",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AttendanceSession.objects.get(section=self.section, date=date(2026, 10, 7)).records.get().status, "late")

    def test_student_without_membership_for_profile_school_cannot_open_learning_home(self):
        self.student_user.school_memberships.filter(school=self.school).update(is_active=False)
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("learning:home")).status_code, 403)

    def test_student_resubmission_preserves_prior_response_and_teacher_can_grade(self):
        assignment = self._assignment()
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.post(reverse("learning:assignment-submit", args=[assignment.pk]), {"response": "First answer"}).status_code, 302)
        submission = assignment.submissions.get(enrollment=self.enrollment)
        first_submitted_at = submission.submitted_at
        self.assertEqual(self.client.post(reverse("learning:assignment-submit", args=[assignment.pk]), {"response": "Improved answer"}).status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.response, "Improved answer")
        self.assertEqual(submission.revisions.count(), 1)
        self.assertEqual(submission.revisions.get().response, "First answer")
        self.assertEqual(submission.revisions.get().submitted_at, first_submitted_at)

        self.client.force_login(self.teacher)
        grade_url = reverse("learning:submission-grade", args=[submission.pk])
        self.assertEqual(self.client.get(grade_url).status_code, 200)
        response = self.client.post(grade_url, {"grade": "92.50", "feedback": "Clear reasoning."})
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(str(submission.grade), "92.50")
        self.assertEqual(submission.feedback, "Clear reasoning.")
        response = self.client.post(grade_url, {"grade": "95.00", "feedback": "Updated after moderation."})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(submission.grade_revisions.count(), 1)
        self.assertEqual(str(submission.grade_revisions.get().grade), "92.50")
        self.assertEqual(submission.grade_revisions.get().feedback, "Clear reasoning.")

        self.client.force_login(self.student_user)
        detail = self.client.get(reverse("learning:assignment-detail", args=[assignment.pk]))
        self.assertContains(detail, "95.00")
        self.assertContains(detail, "Updated after moderation.")
        self.assertContains(detail, "locked after grading")
        response = self.client.post(reverse("learning:assignment-submit", args=[assignment.pk]), {"response": "Changed after grading"})
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.response, "Improved answer")

