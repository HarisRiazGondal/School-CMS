from datetime import date
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section
from audit.models import AuditEvent
from schools.models import AcademicYear, School
from students.models import AdmissionApplication, Enrollment, PromotionDecision, Student
from students.services import (
    commit_batch_promotion, decide_admission_application, link_student_account,
    preview_batch_promotion, register_student, submit_admission_application,
)


class StudentOperationsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Operations School", slug="operations")
        self.other_school = School.objects.create(name="Other Operations", slug="other-operations")
        self.admin = self.user("admin", self.school, SchoolMembership.Role.SCHOOL_ADMIN)
        self.registrar = self.user("registrar", self.school, SchoolMembership.Role.REGISTRAR)
        self.other_admin = self.user("other-admin", self.other_school, SchoolMembership.Role.SCHOOL_ADMIN)
        self.year1 = self.year(self.school, "2025-26", 2025)
        self.year2 = self.year(self.school, "2026-27", 2026)
        self.year3 = self.year(self.school, "2027-28", 2027)
        self.grade1 = SchoolClass.objects.create(school=self.school, name="Grade 1")
        self.grade2 = SchoolClass.objects.create(school=self.school, name="Grade 2")
        self.section1 = Section.objects.create(school_class=self.grade1, academic_year=self.year1, name="A")
        self.target_a = Section.objects.create(school_class=self.grade2, academic_year=self.year2, name="A")
        self.target_b = Section.objects.create(school_class=self.grade2, academic_year=self.year2, name="B")
        self.target3 = Section.objects.create(school_class=self.grade2, academic_year=self.year3, name="A")

    def user(self, username, school, role):
        user = User.objects.create_user(username=username, email=f"{username}@example.test", password="safe-long-password")
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def year(self, school, name, start):
        return AcademicYear.objects.create(school=school, name=name,
            starts_on=date(start, 8, 1), ends_on=date(start + 1, 7, 31))

    def intake(self, **changes):
        values = dict(user=self.registrar, school=self.school, first_name="Nora", last_name="Ali",
                      academic_year=self.year1, section=self.section1, roll_number="10",
                      guardian_name="Rana Ali", guardian_relationship="Parent", guardian_phone="555-0100")
        values.update(changes)
        return submit_admission_application(**values)

    def registered(self, name="Sam", roll="01", year=None, section=None):
        return register_student(user=self.admin, school=self.school, first_name=name,
            academic_year=year or self.year1, section=section or self.section1, roll_number=roll)

    def test_pending_admission_intake_creates_no_student_until_admin_approval(self):
        application = self.intake()
        self.assertEqual(application.status, AdmissionApplication.Status.PENDING)
        self.assertEqual(Student.objects.count(), 0)
        self.assertIsNone(application.student_id)

        approved, student, enrollment = decide_admission_application(
            user=self.admin, application=application, decision=AdmissionApplication.Status.APPROVED)
        self.assertEqual(approved.status, AdmissionApplication.Status.APPROVED)
        self.assertEqual(student.first_name, "Nora")
        self.assertEqual(enrollment.academic_year, self.year1)
        self.assertEqual(student.guardian_relations.get().guardian.name, "Rana Ali")
        self.assertEqual(Student.objects.count(), 1)
        approved_again, same_student, same_enrollment = decide_admission_application(
            user=self.admin, application=application.pk, decision=AdmissionApplication.Status.APPROVED)
        self.assertEqual(approved_again.pk, application.pk)
        self.assertEqual(same_student.pk, student.pk)
        self.assertEqual(same_enrollment.pk, enrollment.pk)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="student.registered").count(), 1)

    def test_admission_rejection_is_idempotent_and_final_decision_is_immutable(self):
        application = self.intake()
        decide_admission_application(user=self.admin, application=application,
                                     decision=AdmissionApplication.Status.REJECTED, note="Incomplete")
        decide_admission_application(user=self.admin, application=application,
                                     decision=AdmissionApplication.Status.REJECTED, note="Retry")
        application.refresh_from_db()
        self.assertEqual(application.decision_note, "Incomplete")
        self.assertEqual(Student.objects.count(), 0)
        with self.assertRaises(ValidationError):
            AdmissionApplication.objects.filter(pk=application.pk).update(status=AdmissionApplication.Status.APPROVED)
        with self.assertRaises(ValidationError):
            AdmissionApplication.objects.filter(pk=application.pk).delete()
        application.decision_note = "tampered"
        with self.assertRaises(ValidationError):
            application.save()

    def test_only_school_admin_decides_and_approval_registration_rolls_back(self):
        application = self.intake()
        with self.assertRaises(PermissionDenied):
            decide_admission_application(user=self.registrar, application=application,
                                         decision=AdmissionApplication.Status.APPROVED)
        with patch("students.services.register_student", side_effect=ValidationError("forced failure")):
            with self.assertRaises(ValidationError):
                decide_admission_application(user=self.admin, application=application,
                                             decision=AdmissionApplication.Status.APPROVED)
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionApplication.Status.PENDING)
        self.assertIsNone(application.student_id)
        self.assertEqual(Student.objects.count(), 0)

    def test_application_scope_and_intake_ui_are_scoped_and_pending(self):
        from django.urls import reverse
        self.client.force_login(self.registrar)
        intake_url = reverse("students:admission-intake", kwargs={"school_slug": self.school.slug})
        response = self.client.post(intake_url, {
            "first_name": "Lina", "last_name": "K", "academic_year": self.year1.pk,
            "section": self.section1.pk, "roll_number": "24", "guardian_name": "Mina",
            "guardian_relationship": "Parent", "guardian_phone": "", "guardian_email": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Student.objects.count(), 0)
        application = AdmissionApplication.objects.get(first_name="Lina")
        queue = self.client.get(reverse("students:admissions", kwargs={"school_slug": self.school.slug}))
        self.assertContains(queue, "Pending")
        self.assertContains(queue, "Approve and register")
        self.client.force_login(self.other_admin)
        self.assertEqual(self.client.get(reverse("students:admissions", kwargs={"school_slug": self.school.slug})).status_code, 403)
        self.assertNotEqual(application.school, self.other_school)

    def test_student_user_cannot_be_reassigned_except_through_admin_link_service(self):
        student, _ = self.registered()
        student_user = self.user("student-one", self.school, SchoolMembership.Role.STUDENT)
        another_student_user = self.user("student-two", self.school, SchoolMembership.Role.STUDENT)
        foreign_student = self.user("foreign-student", self.other_school, SchoolMembership.Role.STUDENT)
        with self.assertRaises(ValidationError):
            student.user = student_user
            student.save()
        with self.assertRaises(ValidationError):
            Student.objects.filter(pk=student.pk).update(user=student_user)
        linked = link_student_account(user=self.admin, student=student, account=student_user)
        self.assertEqual(linked.user_id, student_user.pk)
        with self.assertRaises(ValidationError):
            link_student_account(user=self.admin, student=student, account=another_student_user)
        with self.assertRaises(ValidationError):
            link_student_account(user=self.admin, student=student, account=foreign_student)
        with self.assertRaises(PermissionDenied):
            link_student_account(user=self.registrar, student=student, account=student_user)
        self.assertEqual(AuditEvent.objects.filter(action="student.account_linked").count(), 1)

    def test_batch_promotion_preview_and_commit_support_all_year_outcomes_and_retry(self):
        s1, e1 = self.registered("Promote", "01")
        s2, e2 = self.registered("Repeat", "02")
        s3, e3 = self.registered("Conditional", "03")
        s4, e4 = self.registered("Graduate", "04")
        rows = [
            {"source_id": str(e1.pk), "outcome": "promoted", "target_year": str(self.year2.pk), "target_section": str(self.target_a.pk), "roll_number": "01"},
            {"source_id": str(e2.pk), "outcome": "repeated", "target_year": str(self.year2.pk), "target_section": str(self.target_b.pk), "roll_number": "02"},
            {"source_id": str(e3.pk), "outcome": "conditional", "target_year": str(self.year2.pk), "target_section": str(self.target_a.pk), "roll_number": "03", "condition_reason": "Attend support sessions"},
            {"source_id": str(e4.pk), "outcome": "graduated", "target_year": "", "target_section": "", "roll_number": "04"},
        ]
        plans = preview_batch_promotion(user=self.registrar, school=self.school, rows=rows)
        self.assertTrue(all(plan.can_commit for plan in plans))
        self.assertEqual(Student.objects.count(), 4)
        results = commit_batch_promotion(user=self.admin, school=self.school, rows=rows)
        self.assertEqual(len(results), 4)
        e1.refresh_from_db(); e2.refresh_from_db(); e3.refresh_from_db(); e4.refresh_from_db()
        self.assertEqual([e1.status, e2.status, e3.status, e4.status], ["promoted", "repeated", "conditional", "graduated"])
        self.assertEqual(s1.enrollments.count(), 2)
        self.assertEqual(s2.enrollments.get(academic_year=self.year2).previous_enrollment_id, e2.pk)
        self.assertEqual(s3.enrollments.get(academic_year=self.year2).previous_enrollment_id, e3.pk)
        decision = PromotionDecision.objects.get(source_enrollment=e3)
        self.assertEqual(decision.actor, self.admin)
        self.assertEqual(decision.condition_reason, "Attend support sessions")
        with self.assertRaises(ValidationError):
            PromotionDecision.objects.filter(pk=decision.pk).update(condition_reason="changed")
        forged = PromotionDecision(
            id=decision.pk, source_enrollment=e1, actor=self.admin, outcome=Enrollment.Status.PROMOTED,
            source_year="forged", source_section="forged", source_roll_number="forged",
        )
        with self.assertRaises(ValidationError):
            forged.save()
        retry = commit_batch_promotion(user=self.admin, school=self.school, rows=rows)
        self.assertEqual(len(retry), 4)
        self.assertEqual(s1.enrollments.count(), 2)

    def test_batch_rejects_malformed_duplicate_roll_and_conflict_without_mutation(self):
        _, source = self.registered("Source", "01")
        _, other = self.registered("Other", "02")
        common = {"outcome": "promoted", "target_year": str(self.year2.pk),
                  "target_section": str(self.target_a.pk), "roll_number": "09"}
        malformed = preview_batch_promotion(user=self.admin, school=self.school,
            rows=[{**common, "source_id": "not-a-uuid"}])
        self.assertIn("Malformed", malformed[0].conflict)
        duplicate_ids = preview_batch_promotion(user=self.admin, school=self.school,
            rows=[{**common, "source_id": str(source.pk)}, {**common, "source_id": str(source.pk)}])
        self.assertIn("Duplicate", duplicate_ids[1].conflict)
        duplicate_roll = [{**common, "source_id": str(source.pk)}, {**common, "source_id": str(other.pk)}]
        with self.assertRaises(ValidationError):
            commit_batch_promotion(user=self.admin, school=self.school, rows=duplicate_roll)
        source.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(source.status, Enrollment.Status.ACTIVE)
        self.assertEqual(other.status, Enrollment.Status.ACTIVE)
        self.assertEqual(source.student.enrollments.count(), 1)

    def test_batch_requires_conditional_reason_and_graduation_has_no_target(self):
        _, source = self.registered("Conditional", "01")
        rows = [{"source_id": str(source.pk), "outcome": "conditional", "target_year": str(self.year2.pk),
                 "target_section": str(self.target_a.pk), "roll_number": "01"}]
        self.assertIn("condition reason", preview_batch_promotion(user=self.admin, school=self.school, rows=rows)[0].conflict)
        rows[0]["condition_reason"] = "Weekly review"
        rows[0]["outcome"] = "graduated"
        self.assertIn("cannot include a target", preview_batch_promotion(user=self.admin, school=self.school, rows=rows)[0].conflict)
        malformed = preview_batch_promotion(user=self.admin, school=self.school, rows=["bad row"])
        self.assertIn("row must be an object", malformed[0].conflict)

    def test_individual_conditional_preview_requires_and_displays_reason(self):
        from django.urls import reverse
        student, _ = self.registered("Conditional", "01")
        self.client.force_login(self.registrar)
        url = reverse("students:promotion-preview", kwargs={
            "school_slug": self.school.slug, "student_code": student.student_code, "year_name": self.year1.name,
        })
        response = self.client.post(url, {
            "outcome": Enrollment.Status.CONDITIONAL, "target_year": self.year2.pk,
            "target_section": self.target_a.pk, "roll_number": "01", "condition_reason": "Weekly review",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["preview"].can_commit)
        self.assertContains(response, "Weekly review")

    def test_batch_transaction_rolls_back_prior_rows_if_later_insert_fails(self):
        _, source = self.registered("One", "01")
        _, other = self.registered("Two", "02")
        rows = [
            {"source_id": str(source.pk), "outcome": "promoted", "target_year": str(self.year2.pk), "target_section": str(self.target_a.pk), "roll_number": "01"},
            {"source_id": str(other.pk), "outcome": "repeated", "target_year": str(self.year2.pk), "target_section": str(self.target_b.pk), "roll_number": "02"},
        ]
        original = Enrollment.save
        calls = {"count": 0}
        def fail_second_new(instance, *args, **kwargs):
            if instance._state.adding:
                calls["count"] += 1
                if calls["count"] == 2:
                    raise IntegrityError("simulated conflict")
            return original(instance, *args, **kwargs)
        with patch.object(Enrollment, "save", fail_second_new):
            with self.assertRaises(ValidationError):
                commit_batch_promotion(user=self.admin, school=self.school, rows=rows)
        source.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(source.status, Enrollment.Status.ACTIVE)
        self.assertEqual(other.status, Enrollment.Status.ACTIVE)
        self.assertEqual(source.student.enrollments.count(), 1)
        self.assertEqual(other.student.enrollments.count(), 1)

