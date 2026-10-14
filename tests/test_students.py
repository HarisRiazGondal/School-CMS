from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from unittest.mock import patch
from django.test import TestCase

from accounts.models import SchoolMembership, User
from audit.models import AuditEvent
from academics.models import SchoolClass, Section
from schools.models import AcademicYear, School
from students.models import Enrollment, Student
from students.services import close_enrollment, commit_promotion, enroll_existing_student, preview_promotion, register_student


class StudentLifecycleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="North School", slug="north")
        self.other_school = School.objects.create(name="South School", slug="south")
        self.admin = User.objects.create_user(username="admin", email="admin@north.test", password="long-safe-password")
        self.registrar = User.objects.create_user(username="registrar", email="registrar@north.test", password="long-safe-password")
        self.other_admin = User.objects.create_user(username="other", email="admin@south.test", password="long-safe-password")
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        SchoolMembership.objects.create(user=self.registrar, school=self.school, role=SchoolMembership.Role.REGISTRAR)
        SchoolMembership.objects.create(user=self.other_admin, school=self.other_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        self.class_one = SchoolClass.objects.create(school=self.school, name="Class 1")
        self.class_two = SchoolClass.objects.create(school=self.school, name="Class 2")
        self.other_class = SchoolClass.objects.create(school=self.other_school, name="Class 1")
        self.year_one = self.make_year(self.school, "2025-26", 2025)
        self.year_two = self.make_year(self.school, "2026-27", 2026)
        self.year_three = self.make_year(self.school, "2027-28", 2027)
        self.section_one = Section.objects.create(school_class=self.class_one, academic_year=self.year_one, name="A")
        self.section_two = Section.objects.create(school_class=self.class_two, academic_year=self.year_two, name="A")
        self.section_two_b = Section.objects.create(school_class=self.class_two, academic_year=self.year_two, name="B")
        self.other_year = self.make_year(self.other_school, "2026-27", 2026)
        self.other_section = Section.objects.create(school_class=self.other_class, academic_year=self.other_year, name="A")

    def make_year(self, school, name, year):
        return AcademicYear.objects.create(
            school=school, name=name, starts_on=date(year, 8, 1), ends_on=date(year + 1, 7, 31)
        )

    def register(self, **overrides):
        data = dict(user=self.admin, school=self.school, first_name="Amina", last_name="Khan",
                    academic_year=self.year_one, section=self.section_one, roll_number="01")
        data.update(overrides)
        return register_student(**data)

    def test_registration_creates_stable_school_scoped_code_and_year_context(self):
        student, enrollment = self.register(guardian_name="Sana Khan", guardian_phone="555-0100", guardian_relationship="Mother")
        self.assertEqual(student.student_code, "STU-000001")
        self.assertEqual(student.enrollments.count(), 1)
        self.assertEqual(enrollment.roll_number, "01")
        self.assertEqual(enrollment.academic_year, self.year_one)
        self.assertEqual(enrollment.section, self.section_one)
        self.assertEqual(student.guardian_relations.count(), 1)
        student.first_name = "Amina Noor"
        student.save()
        student.refresh_from_db()
        self.assertEqual(student.student_code, "STU-000001")
        self.assertEqual(student.first_name, "Amina Noor")

    def test_long_school_slug_still_generates_a_valid_school_scoped_code(self):
        long_school = School.objects.create(name="Long Slug School", slug="s" * 80)
        long_admin = User.objects.create_user(username="long-admin", email="long-admin@test", password="long-safe-password")
        SchoolMembership.objects.create(user=long_admin, school=long_school, role=SchoolMembership.Role.SCHOOL_ADMIN)
        school_class = SchoolClass.objects.create(school=long_school, name="Class 1")
        year = self.make_year(long_school, "2025-26", 2025)
        section = Section.objects.create(school_class=school_class, academic_year=year, name="A")
        student, _ = register_student(user=long_admin, school=long_school, first_name="Long", academic_year=year,
                                      section=section, roll_number="01")
        self.assertLessEqual(len(student.student_code), 48)
        self.assertEqual(student.student_code, "STU-000001")

    def test_student_uuid_code_and_school_are_immutable(self):
        import uuid
        student, _ = self.register()
        student.student_code = "CHANGED"
        with self.assertRaises(ValidationError):
            student.save()
        student.refresh_from_db()
        student.school = self.other_school
        with self.assertRaises(ValidationError):
            student.save()
        student.refresh_from_db()
        student.pk = uuid.uuid4()
        with self.assertRaises(ValidationError):
            student.save()

    def test_constructed_instances_and_querysets_cannot_mutate_or_delete_identity(self):
        with self.assertRaises(ValidationError):
            Student.objects.create(school=self.school, student_code="FORGED", first_name="Forged")
        student, enrollment = self.register()
        forged_student = Student(
            id=student.pk, school=self.other_school, student_code="SOUTH-000999",
            first_name="Tampered", last_name="", date_of_birth=None,
        )
        with self.assertRaises(ValidationError):
            forged_student.save()
        with self.assertRaises(ValidationError):
            Student.objects.filter(pk=student.pk).update(student_code="REUSED")
        with self.assertRaises(ValidationError):
            Student.objects.filter(pk=student.pk).delete()

        forged_enrollment = Enrollment(
            id=enrollment.pk, student=student, academic_year=self.year_one,
            section=self.section_two, roll_number="99", status=Enrollment.Status.ACTIVE,
        )
        with self.assertRaises(ValidationError):
            forged_enrollment.save()
        changed_status = Enrollment.objects.get(pk=enrollment.pk)
        changed_status.status = Enrollment.Status.WITHDRAWN
        with self.assertRaises(ValidationError):
            changed_status.save()
        with self.assertRaises(ValidationError):
            Enrollment.objects.filter(pk=enrollment.pk).update(status=Enrollment.Status.WITHDRAWN)
        with self.assertRaises(ValidationError):
            Enrollment.objects.filter(pk=enrollment.pk).delete()

    def test_registration_rejects_mismatched_year_and_other_school(self):
        with self.assertRaises(ValidationError):
            self.register(academic_year=self.year_two, section=self.section_one)
        with self.assertRaises(ValidationError):
            self.register(academic_year=self.other_year, section=self.other_section)
        self.assertEqual(Student.objects.count(), 0)

    def test_re_admission_reuses_identity_only_after_active_enrollment_is_closed(self):
        student, first = self.register()
        with self.assertRaises(ValidationError):
            enroll_existing_student(user=self.admin, student=student, academic_year=self.year_two,
                                    section=self.section_two, roll_number="01")
        close_enrollment(user=self.registrar, source=first, outcome=Enrollment.Status.WITHDRAWN)
        new_placement = enroll_existing_student(user=self.admin, student=student, academic_year=self.year_two,
                                                section=self.section_two, roll_number="01")
        self.assertEqual(new_placement.student, student)
        self.assertEqual(student.student_code, "STU-000001")
        with self.assertRaises(ValidationError):
            enroll_existing_student(user=self.admin, student=student, academic_year=self.year_three,
                                    section=self.section_two, roll_number="03")
        with self.assertRaises(ValidationError):
            self.register(first_name="Another", academic_year=self.year_two, section=self.section_two, roll_number="01")
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(student.enrollments.count(), 2)

    def test_registration_and_promotion_are_scoped_to_active_staff_membership(self):
        with self.assertRaises(PermissionDenied):
            self.register(user=self.other_admin)
        with self.assertRaises(PermissionDenied):
            register_student(user=self.admin, school=self.other_school, first_name="Nope",
                             academic_year=self.other_year, section=self.other_section, roll_number="55")

    def test_preview_is_read_only_and_commit_preserves_identity_and_history(self):
        student, first = self.register()
        plan = preview_promotion(user=self.registrar, source=first, outcome=Enrollment.Status.PROMOTED,
                                 target_year=self.year_two, target_section=self.section_two)
        self.assertTrue(plan.can_commit)
        self.assertEqual(student.enrollments.count(), 1)
        old, next_enrollment = commit_promotion(user=self.admin, source=first, outcome=Enrollment.Status.PROMOTED,
                                               target_year=self.year_two, target_section=self.section_two)
        self.assertEqual(old.status, Enrollment.Status.PROMOTED)
        self.assertEqual(next_enrollment.previous_enrollment, first)
        self.assertEqual(next_enrollment.student, student)
        self.assertEqual(next_enrollment.roll_number, "01")
        self.assertEqual(student.student_code, "STU-000001")
        self.assertEqual(student.enrollments.count(), 2)

    def test_duplicate_target_year_and_wrong_target_school_rejected_without_writes(self):
        student, first = self.register()
        existing_student, existing_enrollment = self.register(
            first_name="Existing", academic_year=self.year_two, section=self.section_two, roll_number="01"
        )
        # Preview reports a target-section roll conflict without writing.
        plan = preview_promotion(user=self.admin, source=first, outcome=Enrollment.Status.PROMOTED,
                                 target_year=self.year_two, target_section=self.section_two)
        self.assertFalse(plan.can_commit)
        self.assertIn("roll number", plan.conflict)
        with self.assertRaises(ValidationError):
            preview_promotion(user=self.admin, source=first, outcome=Enrollment.Status.PROMOTED,
                             target_year=self.other_year, target_section=self.other_section)
        self.assertEqual(student.enrollments.count(), 1)
        self.assertEqual(existing_student.enrollments.count(), 1)
        self.assertEqual(existing_enrollment.status, Enrollment.Status.ACTIVE)
        self.assertEqual(first.status, Enrollment.Status.ACTIVE)

    def test_invalid_target_roll_rolls_back_source_status_change(self):
        student, first = self.register()
        self.register(first_name="Occupied", academic_year=self.year_two, section=self.section_two, roll_number="02")
        with self.assertRaises(ValidationError):
            commit_promotion(user=self.admin, source=first, outcome=Enrollment.Status.PROMOTED,
                            target_year=self.year_two, target_section=self.section_two, roll_number="02")
        first.refresh_from_db()
        self.assertEqual(first.status, Enrollment.Status.ACTIVE)
        self.assertEqual(student.enrollments.count(), 1)

    def test_registrar_can_preview_but_only_admin_can_confirm(self):
        _, first = self.register()
        preview_promotion(user=self.registrar, source=first, outcome=Enrollment.Status.GRADUATED)
        with self.assertRaises(PermissionDenied):
            commit_promotion(user=self.registrar, source=first, outcome=Enrollment.Status.GRADUATED)
        first.refresh_from_db()
        self.assertEqual(first.status, Enrollment.Status.ACTIVE)

    def test_graduation_keeps_existing_enrollment_and_creates_no_new_row(self):
        student, first = self.register()
        commit_promotion(user=self.admin, source=first, outcome=Enrollment.Status.GRADUATED)
        first.refresh_from_db()
        self.assertEqual(first.status, Enrollment.Status.GRADUATED)
        self.assertEqual(student.enrollments.count(), 1)


    def test_scoped_superuser_admin_read_is_audited(self):
        from django.urls import reverse

        student, _ = self.register()
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:students_student_changelist"))
        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.get(action="student.admin_records_viewed", object_type="student")
        self.assertEqual(event.school, self.school)
        self.assertEqual(event.actor, self.admin)
        detail = self.client.get(reverse("admin:students_student_change", args=[student.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(AuditEvent.objects.filter(action="student.admin_records_viewed").count(), 2)

    def test_registration_and_promotion_translate_integrity_races_and_rollback(self):
        from students.models import Enrollment as EnrollmentModel
        save = EnrollmentModel.save
        def fail_new_row(instance, *args, **kwargs):
            if instance._state.adding:
                raise IntegrityError("simulated uniqueness race")
            return save(instance, *args, **kwargs)

        with patch.object(EnrollmentModel, "save", fail_new_row):
            with self.assertRaises(ValidationError):
                self.register()
        self.assertEqual(Student.objects.count(), 0)

        student, source = self.register()
        with patch.object(EnrollmentModel, "save", fail_new_row):
            with self.assertRaises(ValidationError):
                commit_promotion(user=self.admin, source=source, outcome=Enrollment.Status.PROMOTED,
                                 target_year=self.year_two, target_section=self.section_two)
        source.refresh_from_db()
        self.assertEqual(source.status, Enrollment.Status.ACTIVE)
        self.assertEqual(student.enrollments.count(), 1)

    def test_register_preview_and_admin_confirmation_workflow(self):
        from django.urls import reverse

        self.client.force_login(self.registrar)
        list_response = self.client.get(reverse("students:list", kwargs={"school_slug": self.school.slug}))
        self.assertEqual(list_response.status_code, 200)
        register_url = reverse("students:register", kwargs={"school_slug": self.school.slug})
        self.assertEqual(self.client.get(register_url).status_code, 200)
        response = self.client.post(register_url, {
            "first_name": "Mariam", "last_name": "Ali", "academic_year": self.year_one.pk,
            "section": self.section_one.pk, "roll_number": "12", "guardian_name": "Nadia Ali",
            "guardian_relationship": "Mother", "guardian_phone": "555-0112", "guardian_email": "",
        })
        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(first_name="Mariam")
        detail = self.client.get(reverse("students:detail", kwargs={
            "school_slug": self.school.slug, "student_code": student.student_code,
        }))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, student.student_code)
        self.assertContains(detail, "Nadia Ali")
        self.assertTrue(AuditEvent.objects.filter(action="student.register_viewed", school=self.school).exists())
        self.assertTrue(AuditEvent.objects.filter(action="student.list_viewed", school=self.school).exists())
        history_event = AuditEvent.objects.get(action="student.history_viewed", object_id=student.student_code)
        self.assertEqual(history_event.details, {"enrollment_count": 1})
        self.assertNotIn("Mariam", str(history_event.details))

        preview_url = reverse("students:promotion-preview", kwargs={
            "school_slug": self.school.slug, "student_code": student.student_code,
            "year_name": self.year_one.name,
        })
        preview = self.client.post(preview_url, {"outcome": Enrollment.Status.GRADUATED})
        self.assertEqual(preview.status_code, 200)
        self.assertIsNotNone(preview.context["preview"])
        self.assertFalse(preview.context["can_confirm"])
        source = student.enrollments.get()
        self.assertEqual(source.status, Enrollment.Status.ACTIVE)

        self.client.force_login(self.admin)
        preview = self.client.post(preview_url, {"outcome": Enrollment.Status.GRADUATED})
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.context["can_confirm"])
        confirm_url = reverse("students:promotion-confirm", kwargs={
            "school_slug": self.school.slug, "student_code": student.student_code,
            "year_name": self.year_one.name,
        })
        confirmed = self.client.post(confirm_url, {"outcome": Enrollment.Status.GRADUATED})
        self.assertEqual(confirmed.status_code, 302)
        source.refresh_from_db()
        self.assertEqual(source.status, Enrollment.Status.GRADUATED)
