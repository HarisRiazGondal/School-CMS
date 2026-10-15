"""Realistic five-role request-level lifecycle; no browser or network is used."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject
from assessment.models import Answer, Assessment, Attempt, Question
from finance.models import FeePlan, Invoice, Payment
from learning.models import Assignment, AttendanceCorrectionRequest, AttendanceRecord, Submission, TeacherAssignment
from oversight.models import TimetableSlot
from schools.models import AcademicYear, School
from students.models import AdmissionApplication, Enrollment, Student
from students.services import link_student_account


class SchoolHTTPJourneyTests(TestCase):
    """Exercise form validation, CSRF, views and retained history as one journey."""
    password = "Synthetic-School-Journey-Only-52!"

    def setUp(self):
        self.school = School.objects.create(name="Crescent Model School", slug="crescent-demo")
        self.year = AcademicYear.objects.create(school=self.school, name="2026-27", starts_on=date(2026, 8, 1), ends_on=date(2027, 7, 31))
        self.next_year = AcademicYear.objects.create(school=self.school, name="2027-28", starts_on=date(2027, 8, 1), ends_on=date(2028, 7, 31))
        self.grade7 = SchoolClass.objects.create(school=self.school, name="Class 7")
        self.grade8 = SchoolClass.objects.create(school=self.school, name="Class 8")
        self.section7 = Section.objects.create(school_class=self.grade7, academic_year=self.year, name="A")
        self.section8 = Section.objects.create(school_class=self.grade8, academic_year=self.next_year, name="A")
        self.subject = Subject.objects.create(school=self.school, name="Mathematics", code="MATH")
        self.users = {}
        for role in ("school_admin", "registrar", "teacher", "accountant", "student"):
            user = User.objects.create_user(username=f"journey-{role}", email=f"journey-{role}@example.invalid", password=self.password)
            SchoolMembership.objects.create(user=user, school=self.school, role=role)
            self.users[role] = user
        self.assignment = TeacherAssignment.objects.create(user=self.users["teacher"], section=self.section7, subject=self.subject)

    def login_role(self, role):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(reverse("login")).status_code, 200)
        response = client.post(reverse("login"), {"username": self.users[role].username, "password": self.password,
                                                  "csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get(reverse("home")).status_code, 200)
        return client

    def post(self, client, route, data=None, args=None, expected=302):
        response = client.post(reverse(route, args=args), (data or {}) | {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, expected, f"{route}: HTTP {response.status_code}")
        return response

    def test_school_year_forms_marks_class_fees_and_promotion_history(self):
        registrar = self.login_role("registrar")
        intake = {"first_name": "Ayesha", "last_name": "Example", "academic_year": self.year.pk,
                  "section": self.section7.pk, "roll_number": "7-021", "guardian_name": "Synthetic Guardian"}
        self.post(registrar, "students:admission-intake", intake, args=[self.school.slug])
        application = AdmissionApplication.objects.get(first_name="Ayesha")
        self.assertEqual(application.status, AdmissionApplication.Status.PENDING)
        self.assertFalse(Student.objects.exists())
        # The view reports a denied registrar decision as a redirect/message;
        # the permission boundary is proved by the unchanged pending record.
        self.post(registrar, "students:admission-decision", {"decision": "approved"}, args=[self.school.slug, application.pk])
        application.refresh_from_db()
        self.assertEqual(application.status, AdmissionApplication.Status.PENDING)
        self.assertFalse(Student.objects.exists())

        admin = self.login_role("school_admin")
        self.post(admin, "students:admission-decision", {"decision": "approved", "note": "Synthetic documents checked"}, args=[self.school.slug, application.pk])
        student = Student.objects.get(first_name="Ayesha")
        source = student.enrollments.get()
        identity = (student.pk, student.student_code)
        # Account provisioning is fixture/service setup, not a UI feature claim.
        link_student_account(user=self.users["school_admin"], student=student, account=self.users["student"])
        self.post(admin, "oversight:timetable-create", {"assignment": self.assignment.pk, "weekday": 0,
                  "starts_at": "09:00", "ends_at": "09:45", "room": "R-7"}, args=[self.school.slug])
        self.post(admin, "oversight:timetable-create", {"assignment": self.assignment.pk, "weekday": 0,
                  "starts_at": "09:15", "ends_at": "10:00", "room": "R-7"}, args=[self.school.slug], expected=200)
        self.assertEqual(TimetableSlot.objects.count(), 1)

        teacher = self.login_role("teacher")
        self.post(teacher, "learning:attendance-entry", {"date": timezone.localdate().isoformat(),
                  f"status_{source.pk}": "absent"}, args=[self.section7.pk])
        record = AttendanceRecord.objects.get(enrollment=source)
        self.post(teacher, "learning:attendance-correction-request", {"new_status": "present", "new_note": "Register verified",
                  "reason": "Entered absent in error"}, args=[record.pk])
        record.refresh_from_db()
        self.assertEqual(record.status, "absent")
        correction = AttendanceCorrectionRequest.objects.get(attendance_record=record)
        self.post(admin, "learning:attendance-correction-review", {"decision": "approve", "review_note": "Checked"}, args=[correction.pk])
        record.refresh_from_db()
        self.assertEqual(record.status, "present")
        self.post(teacher, "learning:assignment-create", {"section": self.section7.pk, "subject": self.subject.pk,
                  "title": "Ratios practice", "instructions": "Show your work", "publish": "on"})
        work = Assignment.objects.get(title="Ratios practice")
        learner = self.login_role("student")
        self.post(learner, "learning:assignment-submit", {"response": "Synthetic solution"}, args=[work.pk])
        submission = Submission.objects.get(assignment=work)
        self.post(teacher, "learning:submission-grade", {"grade": "88.00", "feedback": "Clear working"}, args=[submission.pk])
        submission.refresh_from_db()
        self.assertEqual(submission.grade, Decimal("88.00"))

        for kind, prompt, maximum, extra in (
            ("mcq", "One half plus one half?", "2", {"choices_text": "1\n2", "correct_answer": "1"}),
            ("manual", "Explain equivalent fractions", "3", {}),
        ):
            self.post(teacher, "assessment:question-create", {"subject": self.subject.pk, "kind": kind,
                      "prompt": prompt, "max_points": maximum} | extra)
        now = timezone.localtime()
        self.post(teacher, "assessment:create", {"section": self.section7.pk, "subject": self.subject.pk,
                  "title": "Class 7 term check", "opens_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
                  "closes_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"), "attempt_limit": 1, "pass_percent": "50"})
        exam = Assessment.objects.get(title="Class 7 term check")
        self.post(teacher, "assessment:attach", {"questions": list(Question.objects.filter(assessment=None).values_list("pk", flat=True))}, args=[exam.pk])
        self.post(teacher, "assessment:open", args=[exam.pk])
        self.post(learner, "assessment:start", args=[exam.pk])
        attempt = Attempt.objects.get(assessment=exam, enrollment=source)
        mcq = exam.questions.get(kind="mcq")
        manual = exam.questions.get(kind="manual")
        self.post(learner, "assessment:submit", {f"answer_{mcq.pk}": "1", f"answer_{manual.pk}": "Multiply both sides equally"}, args=[attempt.pk])
        manual_answer = Answer.objects.get(attempt=attempt, question=manual)
        self.post(teacher, "assessment:mark", {"awarded_points": "4", "feedback": "Invalid over maximum"}, args=[manual_answer.pk], expected=200)
        manual_answer.refresh_from_db()
        self.assertIsNone(manual_answer.awarded_points)
        self.post(teacher, "assessment:mark", {"awarded_points": "2.50", "feedback": "Correct explanation"}, args=[manual_answer.pk])
        self.post(teacher, "assessment:finalize", args=[attempt.pk], expected=403)
        self.post(admin, "assessment:finalize", args=[attempt.pk])
        self.post(admin, "assessment:publish", args=[attempt.pk])
        attempt.refresh_from_db()
        self.assertEqual(attempt.raw_score, Decimal("4.50"))
        self.assertContains(learner.get(reverse("assessment:report-card")), "Class 7 term check")

        accountant = self.login_role("accountant")
        for grade, year, amount in ((self.grade7, self.year, "10000.00"), (self.grade8, self.next_year, "12000.00")):
            self.post(accountant, "finance:plan-create", {"academic_year": year.pk, "grade": grade.pk,
                      "name": f"{grade.name} annual fee", "amount": amount, "currency": "PKR"}, args=[self.school.slug])
        plan7 = FeePlan.objects.get(grade=self.grade7)
        plan8 = FeePlan.objects.get(grade=self.grade8)
        self.assertFalse(Invoice.objects.exists())
        self.post(accountant, "finance:invoice-issue", {"enrollment": source.pk, "fee_plan": plan7.pk, "concession": "0"}, args=[self.school.slug])
        invoice7 = Invoice.objects.get(enrollment=source)
        self.assertEqual(invoice7.balance, Decimal("10000.00"))
        self.post(accountant, "finance:payment-post", {"amount": "3000", "idempotency_key": "http-journey-payment"}, args=[invoice7.pk])
        payment = Payment.objects.get(invoice=invoice7)
        self.assertEqual(invoice7.balance, Decimal("7000.00"))
        self.assertEqual(learner.get(reverse("finance:receipt-detail", args=[payment.receipt.pk])).status_code, 200)

        promotion = {"outcome": "promoted", "target_year": self.next_year.pk,
                     "target_section": self.section8.pk, "roll_number": "8-014"}
        path = [self.school.slug, student.student_code, self.year.name]
        self.post(registrar, "students:promotion-preview", promotion, args=path, expected=200)
        source.refresh_from_db()
        self.assertEqual(source.status, "active")
        self.assertEqual(student.enrollments.count(), 1)
        self.post(registrar, "students:promotion-confirm", promotion, args=path, expected=403)
        self.post(admin, "students:promotion-confirm", promotion, args=path)
        target = student.enrollments.get(academic_year=self.next_year)
        source.refresh_from_db()
        student.refresh_from_db()
        self.assertEqual(source.status, "promoted")
        self.assertEqual(target.previous_enrollment_id, source.pk)
        self.assertEqual((student.pk, student.student_code), identity)
        self.assertFalse(Invoice.objects.filter(enrollment=target).exists())
        self.post(accountant, "finance:invoice-issue", {"enrollment": target.pk, "fee_plan": plan8.pk, "concession": "0"}, args=[self.school.slug])
        self.assertEqual(Invoice.objects.get(enrollment=target).balance, Decimal("12000.00"))
        self.assertEqual(invoice7.balance, Decimal("7000.00"))
        self.assertContains(learner.get(reverse("finance:student-statement")), "2026-27")
        self.assertContains(learner.get(reverse("finance:student-statement")), "2027-28")
        self.assertContains(learner.get(reverse("assessment:report-card")), "Class 7 term check")
        self.post(accountant, "finance:payment-reverse", {"reason": "Synthetic cashier correction", "confirm": "on",
                  "idempotency_key": "http-journey-reversal"}, args=[payment.pk])
        self.assertEqual(invoice7.balance, Decimal("10000.00"))
        self.assertEqual(learner.get(reverse("finance:receipt-detail", args=[payment.receipt.pk])).status_code, 200)
