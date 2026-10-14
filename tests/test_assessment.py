from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from audit.models import AuditEvent
from assessment.models import Assessment, Attempt, Question
from assessment.services import (
    attach_question, begin_attempt, create_assessment, create_question, finalize_attempt,
    grade_answer, open_assessment, publish_attempt, published_transcript, save_answer, submit_attempt,
    _grade_label,
)
from learning.models import TeacherAssignment
from schools.models import AcademicYear, School
from students.models import Enrollment
from students.services import commit_promotion, register_student


class AssessmentLifecycleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north")
        self.other_school = School.objects.create(name="South School", slug="south")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31),
        )
        self.next_year = AcademicYear.objects.create(
            school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31),
        )
        self.klass = SchoolClass.objects.create(school=self.school, name="Class 4")
        self.next_class = SchoolClass.objects.create(school=self.school, name="Class 5")
        self.section = Section.objects.create(school_class=self.klass, academic_year=self.year, name="A")
        self.next_section = Section.objects.create(school_class=self.next_class, academic_year=self.next_year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Science", code="SCI")
        self.other_subject = Subject.objects.create(school=self.other_school, name="Science", code="SCI")
        self.teacher = User.objects.create_user(username="teacher", email="teacher@north.test", password="safe-password")
        self.admin = User.objects.create_user(username="admin", email="admin@north.test", password="safe-password")
        self.student_user = User.objects.create_user(username="student", email="student@north.test", password="safe-password")
        self.other_student_user = User.objects.create_user(username="other-student", email="other@north.test", password="safe-password")
        SchoolMembership.objects.create(user=self.teacher, school=self.school, role=SchoolMembership.Role.TEACHER)
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        SchoolMembership.objects.create(user=self.other_student_user, school=self.school, role=SchoolMembership.Role.STUDENT)
        TeacherAssignment.objects.create(user=self.teacher, section=self.section, subject=self.subject)
        self.student, self.enrollment = register_student(
            user=self.admin, school=self.school, first_name="Amina", academic_year=self.year,
            section=self.section, roll_number="4A-01", student_user=self.student_user,
        )
        self.outsider, self.outsider_enrollment = register_student(
            user=self.admin, school=self.school, first_name="Bilal", academic_year=self.year,
            section=self.section, roll_number="4A-02", student_user=self.other_student_user,
        )
        self.now = timezone.now()

    def make_assessment(self, *, close_delta=timedelta(days=1), opens_delta=-timedelta(minutes=1), attempts=1, title="Unit test"):
        assessment = create_assessment(
            self.teacher, section=self.section, subject=self.subject, title=title,
            opens_at=self.now + opens_delta, closes_at=self.now + close_delta,
            attempt_limit=attempts, pass_percent=Decimal("60.00"),
        )
        q1 = create_question(self.teacher, subject=self.subject, kind=Question.Kind.MCQ,
                             prompt="Select the planet", max_points="2.00", choices=["Earth", "Mars"], correct_answer="Mars")
        q2 = create_question(self.teacher, subject=self.subject, kind=Question.Kind.TRUE_FALSE,
                             prompt="Water freezes at 0 C", max_points="1.00", correct_answer="true")
        q3 = create_question(self.teacher, subject=self.subject, kind=Question.Kind.SHORT_ANSWER,
                             prompt="Name the star", max_points="2.00", correct_answer="Sun")
        q4 = create_question(self.teacher, subject=self.subject, kind=Question.Kind.MANUAL,
                             prompt="Explain why", max_points="5.00")
        attached = [attach_question(self.teacher, assessment, q) for q in (q1, q2, q3, q4)]
        open_assessment(self.teacher, assessment)
        return assessment, attached

    def answer_all(self, attempt, questions):
        for question, value in zip(questions, ["Mars", "TRUE", " sun  ", "Light and heat"]):
            save_answer(attempt, question, value, self.student_user)

    def test_all_question_types_score_objectively_and_manual_review_retains_decimal_raw_marks(self):
        assessment, questions = self.make_assessment()
        attempt = begin_attempt(assessment, self.enrollment, self.student_user)
        self.answer_all(attempt, questions)
        submit_attempt(attempt, self.student_user)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.answers.get(question=questions[0]).awarded_points, Decimal("2.00"))
        self.assertEqual(attempt.answers.get(question=questions[1]).awarded_points, Decimal("1.00"))
        self.assertEqual(attempt.answers.get(question=questions[2]).awarded_points, Decimal("2.00"))
        self.assertIsNone(attempt.answers.get(question=questions[3]).awarded_points)
        with self.assertRaises(PermissionDenied):
            finalize_attempt(attempt, self.teacher)
        with self.assertRaises(ValidationError):
            finalize_attempt(attempt, self.admin)
        manual = attempt.answers.get(question=questions[3])
        grade_answer(manual, "4.25", self.teacher, "Sound reasoning.")
        finalized = finalize_attempt(attempt, self.admin)
        self.assertEqual(finalized.raw_score, Decimal("9.25"))
        self.assertEqual(finalized.total_points, Decimal("10.00"))
        self.assertEqual(finalized.grade_label, "A")
        self.assertEqual(finalized.grading_policy_version, "schoolcms-default-v1")
        with self.assertRaises(ValidationError):
            save_answer(attempt, questions[0], "Earth", self.student_user)
        with self.assertRaises(ValidationError):
            grade_answer(manual, "10", self.teacher)

    def test_scope_attempt_limit_and_schedule_deadline_enforced(self):
        assessment, questions = self.make_assessment(attempts=1)
        with self.assertRaises(PermissionDenied):
            begin_attempt(assessment, self.outsider_enrollment, self.student_user)
        outsider = User.objects.create_user(username="visitor", email="visitor@north.test", password="safe-password")
        with self.assertRaises(PermissionDenied):
            begin_attempt(assessment, self.enrollment, outsider)
        self.student_user.school_memberships.filter(role=SchoolMembership.Role.STUDENT).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            begin_attempt(assessment, self.enrollment, self.student_user)
        self.student_user.school_memberships.filter(role=SchoolMembership.Role.STUDENT).update(is_active=True)
        attempt = begin_attempt(assessment, self.enrollment, self.student_user)
        with self.assertRaises(ValidationError):
            begin_attempt(assessment, self.enrollment, self.student_user)
        with patch("assessment.services.timezone.now", return_value=assessment.closes_at + timedelta(seconds=1)):
            with self.assertRaises(ValidationError):
                save_answer(attempt, questions[0], "Mars", self.student_user)
        # Submission at/after deadline preserves already entered answers and cannot reopen the attempt.
        with patch("assessment.services.timezone.now", return_value=assessment.closes_at + timedelta(seconds=1)):
            submit_attempt(attempt, self.student_user)
        with self.assertRaises(ValidationError):
            begin_attempt(assessment, self.enrollment, self.student_user)

    def test_publication_does_not_close_assessment_or_block_other_enrolled_students(self):
        assessment, questions = self.make_assessment(attempts=2)
        first = begin_attempt(assessment, self.enrollment, self.student_user)
        self.answer_all(first, questions)
        submit_attempt(first, self.student_user)
        grade_answer(first.answers.get(question=questions[3]), "5", self.teacher)
        finalize_attempt(first, self.admin)
        publish_attempt(first, self.admin)
        second = begin_attempt(assessment, self.enrollment, self.student_user)
        self.assertEqual(second.number, 2)
        outsider_attempt = begin_attempt(assessment, self.outsider_enrollment, self.other_student_user)
        self.assertEqual(outsider_attempt.number, 1)
        with self.assertRaises(PermissionDenied):
            published_transcript(self.student, self.other_student_user)

    def test_student_must_wait_for_open_time(self):
        assessment, _ = self.make_assessment(opens_delta=timedelta(minutes=5), close_delta=timedelta(hours=1))
        with self.assertRaises(ValidationError):
            begin_attempt(assessment, self.enrollment, self.student_user)

    def test_configured_pass_threshold_takes_precedence_over_letter_band(self):
        self.assertEqual(_grade_label(Decimal("92.00"), Decimal("95.00")), "F")
        self.assertEqual(_grade_label(Decimal("95.00"), Decimal("95.00")), "A")

    def test_results_are_invisible_until_finalization_and_publication(self):
        assessment, questions = self.make_assessment()
        attempt = begin_attempt(assessment, self.enrollment, self.student_user)
        self.answer_all(attempt, questions)
        submit_attempt(attempt, self.student_user)
        with self.assertRaises(ValidationError):
            publish_attempt(attempt, self.admin)
        with self.assertRaises(ValidationError):
            finalize_attempt(attempt, self.admin)
        grade_answer(attempt.answers.get(question=questions[3]), "3", self.teacher)
        finalize_attempt(attempt, self.admin)
        self.assertEqual(Attempt.objects.filter(pk=attempt.pk, status=Attempt.Status.PUBLISHED).count(), 0)
        publish_attempt(attempt, self.admin)
        attempt.refresh_from_db()
        assessment.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.PUBLISHED)
        self.assertEqual(assessment.status, Assessment.Status.OPEN)
        self.assertTrue(AuditEvent.objects.filter(action="assessment.result_published", object_id=str(attempt.pk)).exists())

    def test_final_result_survives_student_promotion_and_is_grouped_in_historical_year(self):
        assessment, questions = self.make_assessment()
        attempt = begin_attempt(assessment, self.enrollment, self.student_user)
        self.answer_all(attempt, questions)
        submit_attempt(attempt, self.student_user)
        grade_answer(attempt.answers.get(question=questions[3]), "5", self.teacher)
        finalize_attempt(attempt, self.admin)
        publish_attempt(attempt, self.admin)
        _, next_enrollment = commit_promotion(
            user=self.admin, source=self.enrollment, outcome=Enrollment.Status.PROMOTED,
            target_year=self.next_year, target_section=self.next_section,
        )
        self.assertEqual(next_enrollment.previous_enrollment, self.enrollment)
        with self.assertRaises(PermissionDenied):
            begin_attempt(assessment, self.enrollment, self.student_user)
        history = published_transcript(self.student, self.student_user)
        self.assertEqual(list(history), [self.year])
        self.assertEqual(history[self.year][0]["attempt"].pk, attempt.pk)
        self.assertEqual(history[self.year][0]["enrollment"].pk, self.enrollment.pk)
        self.assertEqual(history[self.year][0]["grade_label"], "A")

    def test_attempt_freezes_assessment_and_question_edits_and_queryset_mutation(self):
        assessment, questions = self.make_assessment()
        attempt = begin_attempt(assessment, self.enrollment, self.student_user)
        changed = Assessment.objects.get(pk=assessment.pk)
        changed.title = "Tampered"
        with self.assertRaises(ValidationError):
            changed.save()
        changed_question = Question.objects.get(pk=questions[0].pk)
        changed_question.correct_answer = "Earth"
        with self.assertRaises(ValidationError):
            changed_question.save()
        with self.assertRaises(ValidationError):
            attempt.answers.update(response="forged")
        with self.assertRaises(ValidationError):
            Assessment.objects.filter(pk=assessment.pk).update(title="Forged")
        with self.assertRaises(ValidationError):
            attempt.delete()

    def test_teacher_needs_explicit_active_subject_section_assignment_and_cross_school_keys_rejected(self):
        with self.assertRaises(ValidationError):
            create_assessment(self.admin, section=self.section, subject=self.other_subject, title="bad",
                              opens_at=self.now, closes_at=self.now + timedelta(hours=1))
        self.teacher.school_memberships.filter(role=SchoolMembership.Role.TEACHER).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            create_question(self.teacher, subject=self.subject, kind=Question.Kind.MANUAL,
                            prompt="Try", max_points="1")

    def test_question_authoring_rejects_anonymous_and_inactive_school(self):
        with self.assertRaises(PermissionDenied):
            create_question(AnonymousUser(), subject=self.subject, kind=Question.Kind.MANUAL,
                            prompt="Try", max_points="1")
        self.school.is_active = False
        self.school.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            create_question(self.teacher, subject=self.subject, kind=Question.Kind.MANUAL,
                            prompt="Try", max_points="1")
