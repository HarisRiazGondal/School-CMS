import re
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from accounts.models import SchoolMembership, has_school_role
from audit.services import record_event
from academics.models import Section
from schools.models import AcademicYear, School
from .models import (
    ENROLLMENT_OUTCOME_TOKEN, STUDENT_REGISTRATION_TOKEN,
    Enrollment, Guardian, GuardianStudentRelation, Student,
)

STAFF_ROLES = (SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.REGISTRAR)


def _require_role(user, school, roles=STAFF_ROLES):
    if not has_school_role(user, school, *roles):
        raise PermissionDenied("You do not have permission for this school's student records.")


def _next_code(school):
    # Called while holding the school row lock to serialize registrations within a school.
    prefix = "STU-"
    largest = 0
    for code in Student.objects.filter(school=school, student_code__startswith=prefix).values_list("student_code", flat=True):
        match = re.fullmatch(re.escape(prefix) + r"(\d+)", code)
        if match:
            largest = max(largest, int(match.group(1)))
    return f"{prefix}{largest + 1:06d}"


@transaction.atomic
def register_student(*, user, school, first_name, last_name="", date_of_birth=None,
                     academic_year, section, roll_number, guardian_name="", guardian_phone="",
                     guardian_email="", guardian_relationship="", student_user=None):
    """Register a permanent identity and its first year placement atomically."""
    _require_role(user, school)
    school = School.objects.select_for_update().get(pk=school.pk)
    if not isinstance(academic_year, AcademicYear):
        academic_year = AcademicYear.objects.get(pk=academic_year)
    if not isinstance(section, Section):
        section = Section.objects.select_related("school_class").get(pk=section)
    if academic_year.school_id != school.pk or section.school_class.school_id != school.pk:
        raise ValidationError("The selected year and section must belong to this school.")
    if section.academic_year_id != academic_year.pk:
        raise ValidationError("The selected year must match the section's academic year.")
    try:
        with transaction.atomic():
            student = Student(
                school=school, student_code=_next_code(school), first_name=first_name.strip(),
                last_name=last_name.strip(), date_of_birth=date_of_birth, user=student_user,
            )
            student.save(_registration_token=STUDENT_REGISTRATION_TOKEN)
            enrollment = Enrollment(
                student=student, academic_year=academic_year, section=section,
                roll_number=roll_number.strip(), status=Enrollment.Status.ACTIVE,
            )
            enrollment.full_clean()
            enrollment.save()
            if guardian_name.strip():
                guardian = Guardian.objects.create(
                    school=school, name=guardian_name.strip(), phone=guardian_phone.strip(), email=guardian_email.strip()
                )
                relation = GuardianStudentRelation(
                    guardian=guardian, student=student, relationship=guardian_relationship.strip(), is_primary=True
                )
                relation.full_clean()
                relation.save()
            record_event(school=school, actor=user, action="student.registered", object_type="student",
                         object_id=student.student_code, details={"student_code": student.student_code,
                         "academic_year": academic_year.name})
    except IntegrityError as exc:
        raise ValidationError("A student code, academic-year enrollment, or section roll number conflicts with an existing record.") from exc
    return student, enrollment


@transaction.atomic
def enroll_existing_student(*, user, student, academic_year, section, roll_number):
    """Re-admit an existing identity without replacing or regenerating its code."""
    student = Student.objects.select_for_update().select_related("school").get(pk=getattr(student, "pk", student))
    _require_role(user, student.school)
    if not isinstance(academic_year, AcademicYear):
        academic_year = AcademicYear.objects.get(pk=academic_year)
    if not isinstance(section, Section):
        section = Section.objects.select_related("school_class").get(pk=section)
    if academic_year.school_id != student.school_id or section.school_class.school_id != student.school_id:
        raise ValidationError("The selected year and section must belong to the student's school.")
    if student.enrollments.filter(status=Enrollment.Status.ACTIVE).exists():
        raise ValidationError("The student already has an active enrollment; close that placement before re-admission.")
    try:
        with transaction.atomic():
            enrollment = Enrollment(
                student=student, academic_year=academic_year, section=section,
                roll_number=roll_number.strip(), status=Enrollment.Status.ACTIVE,
            )
            enrollment.full_clean()
            enrollment.save()
            record_event(school=student.school, actor=user, action="student.enrolled", object_type="enrollment",
                         object_id=student.student_code, details={"student_code": student.student_code,
                         "academic_year": academic_year.name})
    except IntegrityError as exc:
        raise ValidationError("A student year or section roll number conflicts with an existing enrollment.") from exc
    return enrollment


@transaction.atomic
def close_enrollment(*, user, source, outcome):
    """Close an active enrollment as withdrawn or transferred before re-admission."""
    source = Enrollment.objects.select_for_update().select_related("student__school").get(pk=getattr(source, "pk", source))
    _require_role(user, source.student.school)
    if outcome not in {Enrollment.Status.WITHDRAWN, Enrollment.Status.TRANSFERRED}:
        raise ValidationError("Choose withdrawn or transferred.")
    if source.status != Enrollment.Status.ACTIVE:
        raise ValidationError("Only an active enrollment can be closed.")
    source.status = outcome
    source.save(update_fields=["status"], _outcome_transition_token=ENROLLMENT_OUTCOME_TOKEN)
    record_event(school=source.student.school, actor=user, action=f"student.{outcome}",
                 object_type="enrollment", object_id=source.student.student_code,
                 details={"student_code": source.student.student_code,
                          "academic_year": source.academic_year.name})
    return source


@dataclass(frozen=True)
class PromotionPreview:
    source: Enrollment
    outcome: str
    target_section: Section | None
    target_year: AcademicYear | None
    can_commit: bool
    conflict: str = ""


def preview_promotion(*, user, source, outcome, target_section=None, target_year=None, target_roll_number=None):
    """Validate a proposed outcome without writing any records."""
    source = Enrollment.objects.select_related("student__school", "academic_year", "section").get(pk=getattr(source, "pk", source))
    _require_role(user, source.student.school)
    allowed = {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED, Enrollment.Status.GRADUATED}
    if outcome not in allowed:
        raise ValidationError("Choose promoted, repeated, or graduated.")
    if source.status != Enrollment.Status.ACTIVE:
        raise ValidationError("Only an active enrollment can be processed.")
    section = year = None
    conflict = ""
    if outcome in {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED}:
        if not target_section or not target_year:
            raise ValidationError("A target academic year and section are required.")
        section = target_section if isinstance(target_section, Section) else Section.objects.select_related("school_class").get(pk=target_section)
        year = target_year if isinstance(target_year, AcademicYear) else AcademicYear.objects.get(pk=target_year)
        if year.school_id != source.student.school_id or section.school_class.school_id != source.student.school_id:
            raise ValidationError("The target must belong to the student's school.")
        if section.academic_year_id != year.pk:
            raise ValidationError("The target year must match the target section's academic year.")
        if year.starts_on <= source.academic_year.starts_on:
            raise ValidationError("The target year must be later than the source year.")
        if Enrollment.objects.filter(student=source.student, academic_year=year).exists():
            conflict = "The student already has an enrollment in the target year."
        elif Enrollment.objects.filter(section=section, roll_number=(target_roll_number or source.roll_number).strip()).exists():
            conflict = "The selected roll number is already used in the target section."
    return PromotionPreview(source, outcome, section, year, not conflict, conflict)


@transaction.atomic
def commit_promotion(*, user, source, outcome, target_section=None, target_year=None, roll_number=None):
    """Commit a confirmed promotion/repeat/graduate decision; only admins may commit."""
    source_id = getattr(source, "pk", source)
    locked = Enrollment.objects.select_for_update().select_related("student__school", "academic_year", "section").get(pk=source_id)
    _require_role(user, locked.student.school, (SchoolMembership.Role.SCHOOL_ADMIN,))
    plan = preview_promotion(
        user=user, source=locked, outcome=outcome,
        target_section=target_section, target_year=target_year, target_roll_number=roll_number,
    )
    if not plan.can_commit:
        raise ValidationError(plan.conflict)
    try:
        with transaction.atomic():
            locked.status = outcome
            locked.save(update_fields=["status"], _outcome_transition_token=ENROLLMENT_OUTCOME_TOKEN)
            next_enrollment = None
            if outcome in {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED}:
                next_enrollment = Enrollment(
                    student=locked.student, academic_year=plan.target_year, section=plan.target_section,
                    roll_number=(roll_number or locked.roll_number).strip(), status=Enrollment.Status.ACTIVE,
                    previous_enrollment=locked,
                )
                next_enrollment.full_clean()
                next_enrollment.save()
            record_event(school=locked.student.school, actor=user,
                         action=f"student.{outcome}", object_type="enrollment",
                         object_id=locked.student.student_code,
                         details={"student_code": locked.student.student_code,
                                  "source_year": locked.academic_year.name,
                                  "target_year": plan.target_year.name if plan.target_year else None})
    except IntegrityError as exc:
        raise ValidationError("A target-year enrollment or section roll number conflicts with an existing record.") from exc
    return locked, next_enrollment
