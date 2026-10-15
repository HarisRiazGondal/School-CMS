from django.test import TestCase, override_settings
from django.urls import reverse

from assessment.models import Question
from assessment.services import (
    begin_attempt, finalize_attempt, grade_answer, publish_attempt,
    published_transcript, submit_attempt,
)
from oversight.services import save_school_setting
from tests import test_assessment as assessment_fixtures


@override_settings(DEBUG=True)
class ResultVisibilityIntegrationTests(TestCase):
    """A stored school policy must affect both student HTML and service reads."""

    def setUp(self):
        assessment_fixtures.AssessmentLifecycleTests.setUp(self)
        self.assessment, questions = assessment_fixtures.AssessmentLifecycleTests.make_assessment(self)
        self.attempt = begin_attempt(self.assessment, self.enrollment, self.student_user)
        assessment_fixtures.AssessmentLifecycleTests.answer_all(self, self.attempt, questions)
        submit_attempt(self.attempt, self.student_user)
        manual = self.attempt.answers.get(question__kind=Question.Kind.MANUAL)
        grade_answer(manual, "4.25", self.teacher)
        finalize_attempt(self.attempt, self.admin)
        publish_attempt(self.attempt, self.admin)

    def test_hide_results_suppresses_transcript_and_student_detail_but_retains_admin_access(self):
        save_school_setting(self.admin, self.school, policy_values={"student_results_visible": False})
        self.assertEqual(published_transcript(self.student, self.student_user), {})
        self.assertTrue(published_transcript(self.student, self.admin))
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("assessment:detail", args=[self.assessment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Result:")
        report = self.client.get(reverse("assessment:report-card"))
        self.assertEqual(report.status_code, 200)
        self.assertNotContains(report, "9.25")
        self.assertNotContains(report, "schoolcms-default-v1")

    def test_default_and_reenabled_policy_show_published_result(self):
        self.assertTrue(published_transcript(self.student, self.student_user))
        save_school_setting(self.admin, self.school, policy_values={"student_results_visible": False})
        save_school_setting(self.admin, self.school, policy_values={"student_results_visible": True})
        self.assertTrue(published_transcript(self.student, self.student_user))
        self.client.force_login(self.student_user)
        self.assertContains(self.client.get(reverse("assessment:detail", args=[self.assessment.pk])), "Result:")

    def test_teacher_summary_excludes_revoked_subject_work_in_same_section(self):
        from academics.models import Subject
        from learning.models import TeacherAssignment
        from learning.services import create_assignment, submit_assignment
        from oversight.services import scoped_dashboard_summary

        extra_subject = Subject.objects.create(school=self.school, name="Art", code="ART")
        grant = TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=extra_subject)
        owned = create_assignment(self.teacher, self.section, self.subject, title="Owned science", publish=True)
        revoked = create_assignment(self.teacher, self.section, extra_subject, title="Old art", publish=True)
        submit_assignment(self.student_user, owned, "Science response")
        submit_assignment(self.student_user, revoked, "Art response")
        grant.is_active = False
        grant.save(update_fields=["is_active"])
        summary = scoped_dashboard_summary(self.teacher, self.school)
        self.assertEqual(summary["pending_submissions"], 1)
        self.assertEqual(summary["published_attempts"], 1)
        save_school_setting(self.admin, self.school, policy_values={"student_results_visible": False})
        self.assertEqual(scoped_dashboard_summary(self.teacher, self.school)["published_attempts"], 1)

    def test_teacher_cannot_take_over_school_notice_by_moving_it_into_assigned_section(self):
        from django.core.exceptions import PermissionDenied
        from oversight.services import create_notice, update_notice

        notice = create_notice(self.admin, school=self.school, title="School notice", body="Original", publish=True)
        # A caller may already have mutated its in-memory instance; authorization
        # must use the persisted source scope as well as the submitted target.
        notice.section = self.section
        with self.assertRaises(PermissionDenied):
            update_notice(self.teacher, notice, section=self.section, body="Changed")
        notice.refresh_from_db()
        self.assertIsNone(notice.section)
        self.assertEqual(notice.body, "Original")
        self.assertEqual(notice.revisions.count(), 0)
