from datetime import timedelta
from decimal import Decimal
from datetime import date
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from learning.models import TeacherAssignment
from assessment.models import Answer, Assessment, Attempt, Question
from assessment.services import create_assessment, create_question
from schools.models import AcademicYear, School
from students.services import commit_promotion, register_student


class AssessmentHTTPWorkflowTests(TestCase):
    password = "assessment-http-test-password"

    def setUp(self):
        self.school = School.objects.create(name="North School", slug="assess-north")
        self.other_school = School.objects.create(name="South School", slug="assess-south")
        self.year = AcademicYear.objects.create(school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31))
        self.next_year = AcademicYear.objects.create(school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31))
        self.other_year = AcademicYear.objects.create(school=self.other_school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31))
        self.school_class = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.next_class = SchoolClass.objects.create(school=self.school, name="Class 5")
        self.other_class = SchoolClass.objects.create(school=self.other_school, name="Class 4")
        self.section = Section.objects.create(school_class=self.school_class, academic_year=self.year, name="A")
        self.next_section = Section.objects.create(school_class=self.next_class, academic_year=self.next_year, name="A")
        self.other_section = Section.objects.create(school_class=self.other_class, academic_year=self.other_year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        self.other_subject = Subject.objects.create(school=self.other_school, name="Science", code="SCI")
        self.teacher = User.objects.create_user(username="assess-teacher", email="assess-teacher@example.com", password=self.password)
        self.outside_teacher = User.objects.create_user(username="outside-teacher", email="outside-teacher@example.com", password=self.password)
        self.admin = User.objects.create_user(username="assess-admin", email="assess-admin@example.com", password=self.password)
        self.student_user = User.objects.create_user(username="assess-student", email="assess-student@example.com", password=self.password)
        self.outside_student = User.objects.create_user(username="outside-student", email="outside-student@example.com", password=self.password)
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.outside_teacher, school=self.other_school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.outside_teacher, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        SchoolMembership.objects.create(user=self.outside_student, school=self.other_school, role=SchoolMembership.Role.STUDENT)
        TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        TeacherAssignment.objects.create(user=self.outside_teacher, section=self.other_section, subject=self.other_subject)
        self.student, self.enrollment = register_student(
            user=self.admin, school=self.school, first_name="Ada", last_name="Learner",
            academic_year=self.year, section=self.section, roll_number="04-01", student_user=self.student_user,
        )
        self.outside_profile, self.outside_enrollment = register_student(
            user=self.outside_teacher, school=self.other_school, first_name="Sam", last_name="Outside",
            academic_year=self.other_year, section=self.other_section, roll_number="04-01", student_user=self.outside_student,
        )
        self.client.force_login(self.teacher)

    def _make_assessment(self):
        now = timezone.now()
        assessment = create_assessment(
            self.teacher, section=self.section, subject=self.subject, title="Science check",
            opens_at=now - timedelta(minutes=2), closes_at=now + timedelta(hours=2),
            attempt_limit=2, pass_percent=Decimal("50"),
        )
        question = create_question(
            self.teacher, subject=self.subject, kind=Question.Kind.MCQ,
            prompt="Which is a star?", choices=["Sun", "Moon"], correct_answer="Sun", max_points=2,
        )
        manual = create_question(
            self.teacher, subject=self.subject, kind=Question.Kind.MANUAL,
            prompt="Explain one observation.", max_points=3,
        )
        from assessment.services import attach_question, open_assessment
        attached = attach_question(self.teacher, assessment, question)
        attached_manual = attach_question(self.teacher, assessment, manual)
        open_assessment(self.teacher, assessment)
        return assessment, attached, attached_manual

    def test_authoring_choices_are_scoped_and_other_school_roles_are_denied(self):
        response = self.client.get(reverse("assessment:question-create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North School")
        self.assertNotContains(response, "South School")
        response = self.client.get(reverse("assessment:create"))
        self.assertEqual(response.status_code, 200)
        now = timezone.now()
        created_question = self.client.post(reverse("assessment:question-create"), {
            "subject": self.subject.pk, "kind": "mcq", "prompt": "Pick a planet.",
            "max_points": "1", "choices_text": "Mars\nVenus", "correct_answer": "Mars",
        })
        self.assertEqual(created_question.status_code, 302)
        bank_question = Question.objects.get(prompt="Pick a planet.")
        created_assessment = self.client.post(reverse("assessment:create"), {
            "section": self.section.pk, "subject": self.subject.pk, "title": "Form-created assessment",
            "opens_at": (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "attempt_limit": "1", "pass_percent": "50.00",
        })
        self.assertEqual(created_assessment.status_code, 302)
        draft = Assessment.objects.get(title="Form-created assessment")
        self.assertEqual(self.client.post(reverse("assessment:attach", args=[draft.pk]), {"questions": [bank_question.pk]}).status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.questions.count(), 1)
        self.assertEqual(self.client.post(reverse("assessment:open", args=[draft.pk])).status_code, 302)
        assessment, _, _ = self._make_assessment()
        self.client.force_login(self.outside_teacher)
        self.assertEqual(self.client.get(reverse("assessment:detail", args=[assessment.pk])).status_code, 403)
        self.client.force_login(self.outside_student)
        self.assertEqual(self.client.get(reverse("assessment:detail", args=[assessment.pk])).status_code, 403)
        report = self.client.get(reverse("assessment:report-card"))
        self.assertEqual(report.status_code, 200)
        self.assertNotContains(report, "Science check")
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("assessment:report-card")).status_code, 403)
        self.client.force_login(self.admin)
        choose_student = self.client.get(reverse("assessment:report-card"))
        self.assertEqual(choose_student.status_code, 200)
        self.assertContains(choose_student, "Ada Learner")
        self.assertNotContains(choose_student, "Sam Outside")
        self.assertEqual(self.client.get(reverse("assessment:report-card"), {"student": str(self.outside_profile.pk)}).status_code, 400)
        self.assertEqual(self.client.get(reverse("assessment:report-card"), {"student": "not-a-uuid"}).status_code, 400)

    def test_mcq_and_manual_mark_admin_publish_and_historical_report(self):
        assessment, mcq, manual = self._make_assessment()
        self.client.force_login(self.student_user)
        detail = self.client.get(reverse("assessment:detail", args=[assessment.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "correct_answer")
        self.assertNotContains(detail, "Private answer key")
        self.client.post(reverse("assessment:start", args=[assessment.pk]))
        attempt = Attempt.objects.get(assessment=assessment, enrollment=self.enrollment)
        attempt_page = self.client.get(reverse("assessment:attempt", args=[attempt.pk]))
        self.assertEqual(attempt_page.status_code, 200)
        self.assertNotContains(attempt_page, "correct_answer")
        submit = self.client.post(reverse("assessment:submit", args=[attempt.pk]), {
            f"answer_{mcq.pk}": "Sun", f"answer_{manual.pk}": "I saw a bright point of light.",
        })
        self.assertEqual(submit.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)

        self.client.force_login(self.teacher)
        manual_answer = Answer.objects.get(attempt=attempt, question=manual)
        mark_page = self.client.get(reverse("assessment:mark", args=[manual_answer.pk]))
        self.assertEqual(mark_page.status_code, 200)
        self.client.post(reverse("assessment:mark", args=[manual_answer.pk]), {"awarded_points": "2.50", "feedback": "Clear observation."})
        self.assertEqual(self.client.post(reverse("assessment:finalize", args=[attempt.pk])).status_code, 403)
        self.client.force_login(self.admin)
        finalize = self.client.post(reverse("assessment:finalize", args=[attempt.pk]), follow=True)
        self.assertEqual(finalize.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.FINALIZED)
        self.assertEqual(attempt.raw_score, Decimal("4.50"))
        self.client.post(reverse("assessment:publish", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.PUBLISHED)

        commit_promotion(user=self.admin, source=self.enrollment, outcome="promoted", target_year=self.next_year, target_section=self.next_section, roll_number="05-01")
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("assessment:attempt", args=[attempt.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("assessment:submit", args=[attempt.pk]), {}).status_code, 403)
        report = self.client.get(reverse("assessment:report-card"))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, "Science check")
        self.assertContains(report, "2026-27")
        self.assertContains(report, "4.50 / 5.00")
        self.assertContains(report, "04-01")

    def test_finalize_conflict_is_visible_until_all_manual_answers_are_marked(self):
        assessment, mcq, manual = self._make_assessment()
        self.client.force_login(self.student_user)
        self.client.post(reverse("assessment:start", args=[assessment.pk]))
        attempt = Attempt.objects.get(assessment=assessment, enrollment=self.enrollment)
        self.client.post(reverse("assessment:submit", args=[attempt.pk]), {f"answer_{mcq.pk}": "Sun", f"answer_{manual.pk}": ""})
        self.client.force_login(self.admin)
        response = self.client.post(reverse("assessment:finalize", args=[attempt.pk]), follow=True)
        self.assertContains(response, "All manual questions must be graded")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(self.client.post(reverse("assessment:publish", args=[attempt.pk])).status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)

    @override_settings(SESSION_COOKIE_AGE=86400)
    def test_late_submit_preserves_last_saved_answers_and_ignores_late_body(self):
        assessment, mcq, manual = self._make_assessment()
        self.client.force_login(self.student_user)
        self.client.post(reverse("assessment:start", args=[assessment.pk]))
        attempt = Attempt.objects.get(assessment=assessment, enrollment=self.enrollment)
        self.assertEqual(self.client.post(reverse("assessment:save", args=[attempt.pk]), {
            f"answer_{mcq.pk}": "Moon", f"answer_{manual.pk}": "Saved before closing.",
        }).status_code, 302)
        mcq_answer = Answer.objects.get(attempt=attempt, question=mcq)
        self.assertEqual(mcq_answer.response, "Moon")
        with patch("django.utils.timezone.now", return_value=assessment.closes_at + timedelta(seconds=1)):
            response = self.client.post(reverse("assessment:submit", args=[attempt.pk]), {
                f"answer_{mcq.pk}": "Sun", f"answer_{manual.pk}": "Late edit.",
            }, follow=True)
        self.assertContains(response, "late responses were not saved")
        mcq_answer.refresh_from_db()
        self.assertEqual(mcq_answer.response, "Moon")
        self.assertEqual(mcq_answer.awarded_points, Decimal("0.00"))
        manual_answer = Answer.objects.get(attempt=attempt, question=manual)
        self.assertEqual(manual_answer.response, "Saved before closing.")

