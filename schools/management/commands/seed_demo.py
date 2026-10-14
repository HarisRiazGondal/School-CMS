from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import SchoolMembership, User
from academics.models import SchoolClass, Section, Subject, Term
from assessment.models import Assessment, Question
from assessment.services import attach_question, create_assessment, create_question, open_assessment
from finance.models import FeePlan, Invoice
from finance.services import create_fee_plan, issue_invoice
from learning.models import Assignment, TeacherAssignment
from schools.models import AcademicYear, Campus, School
from students.models import Enrollment, Student
from students.services import close_enrollment, enroll_existing_student, register_student


class Command(BaseCommand):
    help = "Create or refresh a synthetic school and role accounts for local browser testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            required=True,
            help="Password to set for all demo accounts (choose a local-only value).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is available only when DEBUG=True.")
        password = options["password"]
        if not password or len(password) < 8:
            raise CommandError("Choose a demo password with at least 8 characters.")

        today = timezone.localdate()
        if today.month >= 8:
            start_year = today.year
        else:
            start_year = today.year - 1
        year_name = f"{start_year}-{start_year + 1}"
        year_start = date(start_year, 8, 1)
        year_end = date(start_year + 1, 7, 31)

        with transaction.atomic():
            school, _ = School.objects.update_or_create(
                slug="demo-school",
                defaults={"name": "Demo School", "is_active": True},
            )
            campus, _ = Campus.objects.update_or_create(
                school=school,
                code="MAIN",
                defaults={"name": "Main Campus", "is_active": True},
            )
            year, _ = AcademicYear.objects.get_or_create(
                school=school,
                name=year_name,
                defaults={"starts_on": year_start, "ends_on": year_end},
            )
            AcademicYear.objects.filter(school=school, is_active=True).exclude(pk=year.pk).update(is_active=False)
            if not year.is_active:
                year.is_active = True
                year.save(update_fields=["is_active"])

            term_start = year_start
            term_end = min(year_end, year_start + timedelta(days=119))
            term, _ = Term.objects.get_or_create(
                academic_year=year,
                code="T1",
                defaults={"name": "Term 1", "starts_on": term_start, "ends_on": term_end, "sort_order": 1},
            )

            school_class, _ = SchoolClass.objects.update_or_create(
                school=school,
                name="Grade 7",
                defaults={"sort_order": 7, "is_active": True},
            )
            section, _ = Section.objects.get_or_create(
                school_class=school_class,
                academic_year=year,
                campus=campus,
                name="A",
            )
            next_year, _ = AcademicYear.objects.get_or_create(
                school=school, name=f"{start_year + 1}-{start_year + 2}",
                defaults={"starts_on": date(start_year + 1, 8, 1), "ends_on": date(start_year + 2, 7, 31)},
            )
            next_grade, _ = SchoolClass.objects.get_or_create(
                school=school, name="Grade 8", defaults={"sort_order": 8, "is_active": True},
            )
            Section.objects.get_or_create(school_class=next_grade, academic_year=next_year, campus=campus, name="B")
            subject, _ = Subject.objects.update_or_create(
                school=school,
                code="MATH",
                defaults={"name": "Mathematics", "is_active": True},
            )

            roles = (
                ("demo-admin", "admin@example.test", "Demo", "Admin", SchoolMembership.Role.SCHOOL_ADMIN),
                ("demo-registrar", "registrar@example.test", "Demo", "Registrar", SchoolMembership.Role.REGISTRAR),
                ("demo-teacher", "teacher@example.test", "Demo", "Teacher", SchoolMembership.Role.TEACHER),
                ("demo-accountant", "accountant@example.test", "Demo", "Accountant", SchoolMembership.Role.ACCOUNTANT),
                ("demo-student", "student@example.test", "Casey", "Learner", SchoolMembership.Role.STUDENT),
            )
            users = {}
            for username, email, first_name, last_name, role in roles:
                user, _ = User.objects.get_or_create(
                    username=username,
                    defaults={"email": email, "first_name": first_name, "last_name": last_name},
                )
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.is_active = True
                user.is_staff = False
                user.is_superuser = False
                user.set_password(password)
                user.save()
                users[role] = user
                SchoolMembership.objects.update_or_create(
                    user=user,
                    school=school,
                    role=role,
                    defaults={"is_active": True},
                )

            teacher = users[SchoolMembership.Role.TEACHER]
            TeacherAssignment.objects.update_or_create(
                user=teacher,
                section=section,
                subject=subject,
                defaults={"is_active": True},
            )

            student_user = users[SchoolMembership.Role.STUDENT]
            registrar = users[SchoolMembership.Role.SCHOOL_ADMIN]
            student = Student.objects.filter(school=school, user=student_user).first()
            if student is None:
                student, enrollment = register_student(
                    user=registrar, school=school, first_name="Casey", last_name="Learner",
                    date_of_birth=date(start_year - 13, 5, 12), academic_year=year,
                    section=section, roll_number="07", student_user=student_user,
                )
            enrollment = Enrollment.objects.filter(student=student, academic_year=year).first()
            if enrollment is None:
                current = student.enrollments.filter(status=Enrollment.Status.ACTIVE).first()
                if current:
                    close_enrollment(user=registrar, source=current, outcome=Enrollment.Status.TRANSFERRED)
                enrollment = enroll_existing_student(
                    user=registrar, student=student, academic_year=year, section=section, roll_number="07",
                )

            # The finance services post an immutable charge and append-only ledger entry.
            # Reuse an existing fixture invoice without rewriting its balance or payments.
            fee_plan = FeePlan.objects.filter(
                school=school, academic_year=year, grade=school_class, name="Demo annual fee",
            ).first()
            if fee_plan is None:
                fee_plan = create_fee_plan(
                    user=users[SchoolMembership.Role.ACCOUNTANT], school=school, academic_year=year,
                    grade=school_class, name="Demo annual fee", amount="5000.00", currency="PKR",
                )
            if not Invoice.objects.filter(enrollment=enrollment, fee_plan=fee_plan).exists():
                issue_invoice(
                    user=users[SchoolMembership.Role.ACCOUNTANT], enrollment=enrollment,
                    fee_plan=fee_plan,
                )

            # Seed one live assessment and its questions through the normal lifecycle.
            # A rerun leaves an existing assessment, attempts, answers and results intact.
            assessment_title = "Fractions mastery check"
            assessment = Assessment.objects.filter(
                school=school, academic_year=year, section=section, subject=subject,
                title=assessment_title,
            ).first()
            if assessment is None:
                assessment = create_assessment(
                    teacher, section=section, subject=subject, term=term, title=assessment_title,
                    opens_at=timezone.now() - timedelta(hours=1),
                    closes_at=timezone.now() + timedelta(days=30), attempt_limit=2, pass_percent="60.00",
                )
            if assessment.status == Assessment.Status.DRAFT and not assessment.questions.exists():
                question_specs = (
                    (Question.Kind.MCQ, "Which fraction is equivalent to 1/2?", ["2/4", "2/3", "3/5"], "2/4", "2.00"),
                    (Question.Kind.TRUE_FALSE, "A fraction with equal numerator and denominator equals 1.", [], "true", "1.00"),
                    (Question.Kind.MANUAL, "Explain how you would compare 3/4 and 2/3.", [], "", "3.00"),
                )
                for position, (kind, prompt, choices, correct_answer, points) in enumerate(question_specs, start=1):
                    bank_question = create_question(
                        teacher, subject=subject, kind=kind, prompt=prompt,
                        max_points=points, choices=choices, correct_answer=correct_answer,
                        position=position,
                    )
                    attach_question(teacher, assessment, bank_question)
            if assessment.status == Assessment.Status.DRAFT and assessment.questions.exists():
                open_assessment(teacher, assessment)

            assignment, created = Assignment.objects.get_or_create(
                section=section,
                subject=subject,
                teacher=teacher,
                title="Fractions practice",
                defaults={
                    "instructions": "Complete the synthetic practice set and submit your working.",
                    "due_at": timezone.make_aware(datetime.combine(today + timedelta(days=7), time.min)),
                    "is_published": True,
                },
            )
            if not created and not assignment.is_published:
                assignment.is_published = True
                assignment.save(update_fields=["is_published"])

        self.stdout.write(self.style.SUCCESS(
            f"Demo school ready for {year_name}. Accounts: demo-admin, demo-registrar, demo-teacher, demo-accountant, demo-student."
        ))
        self.stdout.write("All accounts use the password supplied with --password.")
