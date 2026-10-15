import re
import uuid
from dataclasses import dataclass
from django.utils import timezone

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from accounts.models import SchoolMembership, has_school_role
from audit.services import record_event
from academics.models import Section
from schools.models import AcademicYear, School
from .models import (
    ADMISSION_DECISION_TOKEN, ADMISSION_INTAKE_TOKEN, ENROLLMENT_OUTCOME_TOKEN,
    PROMOTION_DECISION_TOKEN, STUDENT_ACCOUNT_LINK_TOKEN, STUDENT_REGISTRATION_TOKEN,
    AdmissionApplication, Enrollment, Guardian, GuardianStudentRelation, PromotionDecision, Student,
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
    if student_user is not None and not has_school_role(student_user, school, SchoolMembership.Role.STUDENT):
        raise ValidationError("A linked portal account must be an active student member of this school.")
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
def submit_admission_application(*, user, school, first_name, last_name="", date_of_birth=None,
                                 academic_year, section, roll_number, guardian_name="",
                                 guardian_phone="", guardian_email="", guardian_relationship=""):
    """Create a pending intake record without creating a Student identity."""
    _require_role(user, school)
    year = academic_year if isinstance(academic_year, AcademicYear) else AcademicYear.objects.get(pk=academic_year)
    section = section if isinstance(section, Section) else Section.objects.select_related("school_class").get(pk=section)
    if year.school_id != school.pk or section.school_class.school_id != school.pk or section.academic_year_id != year.pk:
        raise ValidationError("The selected year and section must belong to this school and match.")
    application = AdmissionApplication(
        school=school, first_name=first_name.strip(), last_name=last_name.strip(), date_of_birth=date_of_birth,
        academic_year=year, section=section, roll_number=roll_number.strip(), guardian_name=guardian_name.strip(),
        guardian_phone=guardian_phone.strip(), guardian_email=guardian_email.strip(),
        guardian_relationship=guardian_relationship.strip(),
    )
    application.full_clean()
    application.save(_intake_token=ADMISSION_INTAKE_TOKEN)
    record_event(school=school, actor=user, action="student.admission_submitted", object_type="admission_application",
                 object_id=application.pk, details={"status": application.status, "academic_year": year.name})
    return application


@transaction.atomic
def decide_admission_application(*, user, application, decision, note=""):
    """Approve or reject an application; approval and first registration are one transaction."""
    application = AdmissionApplication.objects.select_for_update().select_related(
        "school", "academic_year", "section__school_class", "student"
    ).get(pk=getattr(application, "pk", application))
    _require_role(user, application.school, (SchoolMembership.Role.SCHOOL_ADMIN,))
    if decision not in {AdmissionApplication.Status.APPROVED, AdmissionApplication.Status.REJECTED}:
        raise ValidationError("Choose approved or rejected.")
    if len(note.strip()) > 500:
        raise ValidationError("Decision note must be 500 characters or fewer.")
    if application.status != AdmissionApplication.Status.PENDING:
        if application.status != decision:
            raise ValidationError("This application already has a different final decision.")
        enrollment = application.student.enrollments.get(academic_year=application.academic_year) if application.student else None
        return application, application.student, enrollment
    student = enrollment = None
    if decision == AdmissionApplication.Status.APPROVED:
        student, enrollment = register_student(
            user=user, school=application.school, first_name=application.first_name, last_name=application.last_name,
            date_of_birth=application.date_of_birth, academic_year=application.academic_year,
            section=application.section, roll_number=application.roll_number, guardian_name=application.guardian_name,
            guardian_phone=application.guardian_phone, guardian_email=application.guardian_email,
            guardian_relationship=application.guardian_relationship,
        )
    application.status = decision
    application.decision_note = note.strip()
    application.decided_by = user
    application.decided_at = timezone.now()
    application.student = student
    application.save(update_fields=["status", "decision_note", "decided_by", "decided_at", "student"],
                     _decision_token=ADMISSION_DECISION_TOKEN)
    record_event(school=application.school, actor=user, action=f"student.admission_{decision}",
                 object_type="admission_application", object_id=application.pk,
                 details={"student_code": student.student_code if student else None, "note": application.decision_note})
    return application, student, enrollment


@transaction.atomic
def link_student_account(*, user, student, account):
    """Admin-controlled one-time link to an active student account in the same school."""
    student = Student.objects.select_for_update().select_related("school").get(pk=getattr(student, "pk", student))
    _require_role(user, student.school, (SchoolMembership.Role.SCHOOL_ADMIN,))
    from accounts.models import User
    try:
        account = account if isinstance(account, User) else User.objects.get(pk=account)
    except User.DoesNotExist as exc:
        raise ValidationError("The selected student account does not exist.") from exc
    if not has_school_role(account, student.school, SchoolMembership.Role.STUDENT):
        raise ValidationError("The account must be active and have student membership in this school.")
    if student.user_id and student.user_id != account.pk:
        raise ValidationError("This student already has a different linked account.")
    if student.user_id != account.pk:
        student.user = account
        student.save(update_fields=["user"], _account_link_token=STUDENT_ACCOUNT_LINK_TOKEN)
        record_event(school=student.school, actor=user, action="student.account_linked", object_type="student",
                     object_id=student.student_code, details={"account_id": account.pk})
    return student


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


def preview_promotion(*, user, source, outcome, target_section=None, target_year=None, target_roll_number=None,
                      condition_reason=""):
    """Validate a proposed outcome without writing any records."""
    source = Enrollment.objects.select_related("student__school", "academic_year", "section").get(pk=getattr(source, "pk", source))
    _require_role(user, source.student.school)
    allowed = {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED, Enrollment.Status.CONDITIONAL, Enrollment.Status.GRADUATED}
    if outcome not in allowed:
        raise ValidationError("Choose promoted, repeated, or graduated.")
    if outcome == Enrollment.Status.CONDITIONAL and not condition_reason.strip():
        raise ValidationError("A condition reason is required for a conditional outcome.")
    if len(condition_reason.strip()) > 500:
        raise ValidationError("Condition reason must be 500 characters or fewer.")
    if source.status != Enrollment.Status.ACTIVE:
        raise ValidationError("Only an active enrollment can be processed.")
    section = year = None
    conflict = ""
    if outcome in {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED, Enrollment.Status.CONDITIONAL}:
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
def commit_promotion(*, user, source, outcome, target_section=None, target_year=None, roll_number=None,
                     condition_reason=""):
    """Commit a confirmed promotion/repeat/graduate decision; only admins may commit."""
    source_id = getattr(source, "pk", source)
    source_hint = Enrollment.objects.select_related("student__school").get(pk=source_id)
    School.objects.select_for_update().get(pk=source_hint.student.school_id)
    locked = Enrollment.objects.select_for_update().select_related("student__school", "academic_year", "section").get(pk=source_id)
    _require_role(user, locked.student.school, (SchoolMembership.Role.SCHOOL_ADMIN,))
    plan = preview_promotion(
        user=user, source=locked, outcome=outcome,
        target_section=target_section, target_year=target_year, target_roll_number=roll_number,
        condition_reason=condition_reason,
    )
    if not plan.can_commit:
        raise ValidationError(plan.conflict)
    try:
        with transaction.atomic():
            locked.status = outcome
            locked.save(update_fields=["status"], _outcome_transition_token=ENROLLMENT_OUTCOME_TOKEN)
            next_enrollment = None
            if outcome in {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED, Enrollment.Status.CONDITIONAL}:
                next_enrollment = Enrollment(
                    student=locked.student, academic_year=plan.target_year, section=plan.target_section,
                    roll_number=(roll_number or locked.roll_number).strip(), status=Enrollment.Status.ACTIVE,
                    previous_enrollment=locked,
                )
                next_enrollment.full_clean()
                next_enrollment.save()
            PromotionDecision(
                source_enrollment=locked, target_enrollment=next_enrollment, actor=user, outcome=outcome,
                source_year=locked.academic_year.name,
                source_section=f"{locked.section.school_class.name} · {locked.section.name}",
                source_roll_number=locked.roll_number,
                target_year=plan.target_year.name if plan.target_year else "",
                target_section=(f"{plan.target_section.school_class.name} · {plan.target_section.name}" if plan.target_section else ""),
                target_roll_number=(roll_number or locked.roll_number).strip() if next_enrollment else "",
                condition_reason=condition_reason.strip(),
            ).save(_decision_token=PROMOTION_DECISION_TOKEN)
            record_event(school=locked.student.school, actor=user,
                         action=f"student.{outcome}", object_type="enrollment",
                         object_id=locked.student.student_code,
                         details={"student_code": locked.student.student_code,
                                  "source_year": locked.academic_year.name,
                                  "target_year": plan.target_year.name if plan.target_year else None})
    except IntegrityError as exc:
        raise ValidationError("A target-year enrollment or section roll number conflicts with an existing record.") from exc
    return locked, next_enrollment


@dataclass(frozen=True)
class BatchPromotionRow:
    source_id: str
    source: Enrollment | None
    outcome: str
    target_year: AcademicYear | None = None
    target_section: Section | None = None
    roll_number: str = ""
    can_commit: bool = False
    repeated: bool = False
    conflict: str = ""
    condition_reason: str = ""


def preview_batch_promotion(*, user, school, rows):
    """Validate the whole submitted batch and report row-level outcomes without writes."""
    _require_role(user, school)
    result, seen_sources, seen_rolls = [], set(), set()
    for raw in rows or []:
        if not isinstance(raw, dict):
            result.append(BatchPromotionRow("", None, "", conflict="Each batch row must be an object."))
            continue
        source_id = str(raw.get("source_id", "")).strip()
        outcome = str(raw.get("outcome", "")).strip()
        condition_reason = str(raw.get("condition_reason", "")).strip()
        try:
            source_uuid = uuid.UUID(source_id)
        except (ValueError, TypeError, AttributeError):
            result.append(BatchPromotionRow(source_id, None, outcome, conflict="Malformed enrollment UUID."))
            continue
        if source_uuid in seen_sources:
            result.append(BatchPromotionRow(source_id, None, outcome, conflict="Duplicate enrollment row."))
            continue
        seen_sources.add(source_uuid)
        try:
            source = Enrollment.objects.select_related("student__school", "academic_year", "section").get(
                pk=source_uuid, student__school=school
            )
        except Enrollment.DoesNotExist:
            result.append(BatchPromotionRow(source_id, None, outcome, conflict="Enrollment was not found in this school."))
            continue
        allowed = {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED, Enrollment.Status.CONDITIONAL,
                   Enrollment.Status.GRADUATED}
        if outcome not in allowed:
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="Choose a valid outcome."))
            continue
        if outcome == Enrollment.Status.CONDITIONAL and not condition_reason:
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="A condition reason is required for a conditional outcome."))
            continue
        if len(condition_reason) > 500:
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="Condition reason must be 500 characters or fewer."))
            continue
        target_year, target_section = raw.get("target_year"), raw.get("target_section")
        roll = str(raw.get("roll_number") or source.roll_number).strip()
        repeated = source.status == outcome
        if source.status != Enrollment.Status.ACTIVE and not repeated:
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="Only active enrollments can be processed."))
            continue
        if outcome == Enrollment.Status.GRADUATED:
            if target_year not in (None, "") or target_section not in (None, ""):
                result.append(BatchPromotionRow(source_id, source, outcome, conflict="Graduation cannot include a target year or section."))
                continue
            result.append(BatchPromotionRow(source_id, source, outcome, can_commit=True, repeated=repeated))
            continue
        try:
            year = target_year if isinstance(target_year, AcademicYear) else AcademicYear.objects.get(pk=target_year)
            section = target_section if isinstance(target_section, Section) else Section.objects.select_related("school_class").get(pk=target_section)
        except (AcademicYear.DoesNotExist, Section.DoesNotExist, ValueError, TypeError, ValidationError):
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="A valid target year and section are required."))
            continue
        if year.school_id != school.pk or section.school_class.school_id != school.pk or section.academic_year_id != year.pk or year.starts_on <= source.academic_year.starts_on:
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="Target year and section are invalid for this enrollment."))
            continue
        successor = Enrollment.objects.filter(student=source.student, academic_year=year).first()
        if repeated:
            if not successor or successor.section_id != section.pk or successor.roll_number != roll:
                result.append(BatchPromotionRow(source_id, source, outcome, conflict="This outcome was already recorded with a different target."))
                continue
        elif successor:
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="Student already has an enrollment in the target year."))
            continue
        key = (section.pk, roll.casefold())
        if not repeated and (key in seen_rolls or Enrollment.objects.filter(section=section, roll_number=roll).exists()):
            result.append(BatchPromotionRow(source_id, source, outcome, conflict="Target section roll number conflicts with another row."))
            continue
        seen_rolls.add(key)
        result.append(BatchPromotionRow(source_id, source, outcome, year, section, roll, True, repeated,
                                        condition_reason=condition_reason))
    return result


@transaction.atomic
def commit_batch_promotion(*, user, school, rows):
    """Confirm a valid batch atomically. Any stale/conflicting row rolls back every write."""
    _require_role(user, school, (SchoolMembership.Role.SCHOOL_ADMIN,))
    School.objects.select_for_update().get(pk=school.pk)
    normalized = [
        ({**row, "source_id": str(row.get("source_id", "")).strip()} if isinstance(row, dict) else {})
        for row in (rows or [])
    ]
    source_ids = []
    for row in normalized:
        try:
            source_ids.append(uuid.UUID(row["source_id"]))
        except (ValueError, TypeError, AttributeError):
            pass
    list(Enrollment.objects.select_for_update().filter(pk__in=source_ids, student__school=school).order_by("pk"))
    # Recheck every row under the school and enrollment locks to reject stale previews.
    plans = preview_batch_promotion(user=user, school=school, rows=normalized)
    if not plans or any(not plan.can_commit for plan in plans):
        raise ValidationError("The batch has invalid or conflicting rows; nothing was changed.")
    outcomes = []
    batch_id = uuid.uuid4()
    try:
        with transaction.atomic():
            for plan in plans:
                source = Enrollment.objects.select_for_update().select_related("student__school", "academic_year", "section").get(pk=plan.source.pk)
                if plan.repeated:
                    outcomes.append((source, source.next_enrollments.first()))
                    continue
                source.status = plan.outcome
                source.save(update_fields=["status"], _outcome_transition_token=ENROLLMENT_OUTCOME_TOKEN)
                next_enrollment = None
                if plan.outcome != Enrollment.Status.GRADUATED:
                    next_enrollment = Enrollment(
                        student=source.student, academic_year=plan.target_year, section=plan.target_section,
                        roll_number=plan.roll_number, status=Enrollment.Status.ACTIVE, previous_enrollment=source,
                    )
                    next_enrollment.full_clean()
                    next_enrollment.save()
                PromotionDecision(
                    source_enrollment=source, target_enrollment=next_enrollment, actor=user, outcome=plan.outcome,
                    source_year=source.academic_year.name,
                    source_section=f"{source.section.school_class.name} · {source.section.name}",
                    source_roll_number=source.roll_number,
                    target_year=plan.target_year.name if plan.target_year else "",
                    target_section=(f"{plan.target_section.school_class.name} · {plan.target_section.name}" if plan.target_section else ""),
                    target_roll_number=plan.roll_number if next_enrollment else "",
                    condition_reason=plan.condition_reason, batch_id=batch_id,
                ).save(_decision_token=PROMOTION_DECISION_TOKEN)
                record_event(school=school, actor=user, action=f"student.{plan.outcome}", object_type="enrollment",
                             object_id=source.student.student_code, details={"source_year": source.academic_year.name,
                             "target_year": plan.target_year.name if plan.target_year else None, "batch": True})
                outcomes.append((source, next_enrollment))
    except IntegrityError as exc:
        raise ValidationError("A batch target year or section roll conflicts with an existing enrollment; nothing was changed.") from exc
    return outcomes
