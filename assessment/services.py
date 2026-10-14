from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import SchoolMembership, has_school_role
from audit.services import record_event
from learning.models import TeacherAssignment
from learning.services import can_manage_section
from students.models import Enrollment
from .models import (
    ANSWER_LIFECYCLE_TOKEN, ASSESSMENT_LIFECYCLE_TOKEN, ATTEMPT_LIFECYCLE_TOKEN, QUESTION_LIFECYCLE_TOKEN,
    Assessment, Answer, Attempt, Question,
)


DEFAULT_GRADING_POLICY_VERSION = "schoolcms-default-v1"


def _active_student_enrollment(user, assessment):
    if not user.is_authenticated or not user.is_active or not assessment.school.is_active:
        return None
    if not SchoolMembership.objects.filter(
        user=user, school=assessment.school, role=SchoolMembership.Role.STUDENT, is_active=True,
    ).exists():
        return None
    return Enrollment.objects.filter(
        student__user=user, student__school=assessment.school,
        section=assessment.section, academic_year=assessment.academic_year,
        status=Enrollment.Status.ACTIVE,
    ).select_related("student", "section", "academic_year").first()


def student_enrollment_for_assessment(user, assessment):
    """Return only the requesting student's active enrollment in this assessment scope."""
    return _active_student_enrollment(user, assessment)


def can_manage_assessment(user, assessment):
    return bool(user.is_authenticated and user.is_active and can_manage_section(user, assessment.section, assessment.subject))


def require_assessment_manager(user, assessment):
    if not can_manage_assessment(user, assessment):
        raise PermissionDenied("You are not assigned to manage this assessment.")


def teacher_assessments(user):
    if not user.is_authenticated or not user.is_active:
        return Assessment.objects.none()
    admin_ids = SchoolMembership.objects.filter(
        user=user, user__is_active=True, school__is_active=True,
        is_active=True, role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).values_list("school_id", flat=True)
    assigned_ids = TeacherAssignment.objects.filter(
        user=user, user__is_active=True, is_active=True,
        user__school_memberships__school=models_outer_school(),
        user__school_memberships__role=SchoolMembership.Role.TEACHER,
        user__school_memberships__is_active=True,
        user__school_memberships__school__is_active=True,
        section__school_class__school__is_active=True,
    ).values_list("section_id", "subject_id")
    from django.db.models import Q
    predicate = Q(school_id__in=admin_ids)
    for section_id, subject_id in assigned_ids:
        predicate |= Q(section_id=section_id, subject_id=subject_id)
    return Assessment.objects.filter(predicate).select_related("section", "subject", "academic_year").order_by("-opens_at")


def models_outer_school():
    """Outer reference used to require a matching active school membership."""
    from django.db.models import F
    return F("section__school_class__school")


def student_assessments(user):
    if not user.is_authenticated or not user.is_active:
        return Assessment.objects.none()
    school_ids = SchoolMembership.objects.filter(
        user=user, user__is_active=True, is_active=True,
        role=SchoolMembership.Role.STUDENT, school__is_active=True,
    ).values_list("school_id", flat=True)
    enrollment_scopes = Enrollment.objects.filter(
        student__user=user, student__school_id__in=school_ids,
        student__user__is_active=True, student__school__is_active=True,
        status=Enrollment.Status.ACTIVE,
    ).values_list("section_id", "academic_year_id")
    from django.db.models import Q
    predicate = Q(pk__in=[])
    for section_id, year_id in enrollment_scopes:
        predicate |= Q(section_id=section_id, academic_year_id=year_id)
    return Assessment.objects.filter(
        predicate, status=Assessment.Status.OPEN, school_id__in=school_ids,
    ).distinct().order_by("opens_at")


def _require_authoring_access(user, section, subject):
    if not can_manage_section(user, section, subject):
        raise PermissionDenied("You are not assigned to this subject and section.")
    if not has_school_role(user, section.school_class.school, SchoolMembership.Role.SCHOOL_ADMIN):
        if not TeacherAssignment.objects.filter(
            user=user, user__is_active=True, is_active=True,
            user__school_memberships__school=section.school_class.school,
            user__school_memberships__role=SchoolMembership.Role.TEACHER,
            user__school_memberships__is_active=True,
        user__school_memberships__school__is_active=True,
            section=section, subject=subject,
        ).exists():
            raise PermissionDenied("An active assignment for this subject and section is required.")


@transaction.atomic
def create_assessment(user, *, section, subject, title, opens_at, closes_at, attempt_limit=1,
                     pass_percent=Decimal("50.00"), term=None):
    _require_authoring_access(user, section, subject)
    pass_pct = Decimal(str(pass_percent))
    if not pass_pct.is_finite():
        raise ValidationError("Pass percent must be a finite decimal value.")
    assessment = Assessment(
        school=section.school_class.school, academic_year=section.academic_year,
        section=section, subject=subject, term=term, title=title,
        opens_at=opens_at, closes_at=closes_at, attempt_limit=attempt_limit,
        pass_percent=pass_pct, created_by=user,
    )
    assessment.full_clean()
    assessment.save(_assessment_lifecycle_token=ASSESSMENT_LIFECYCLE_TOKEN)
    record_event(
        school=assessment.school, actor=user, action="assessment.created",
        object_type="assessment", object_id=assessment.pk,
        details={"section_id": section.pk, "subject_id": subject.pk},
    )
    return assessment


@transaction.atomic
def create_question(user, *, subject, kind, prompt, max_points, choices=None,
                    correct_answer="", position=0):
    if not user.is_authenticated or not user.is_active or not subject.school.is_active:
        raise PermissionDenied("An active account and school are required to author questions.")
    if has_school_role(user, subject.school, SchoolMembership.Role.SCHOOL_ADMIN):
        pass
    else:
        has_assignment = TeacherAssignment.objects.filter(
            user=user, user__is_active=True, is_active=True, subject=subject,
            section__school_class__school=subject.school,
            user__school_memberships__school=subject.school,
            user__school_memberships__role=SchoolMembership.Role.TEACHER,
            user__school_memberships__is_active=True,
        user__school_memberships__school__is_active=True,
        ).exists()
        if not has_assignment:
            raise PermissionDenied("An active teacher assignment for this subject is required.")
    try:
        maximum = Decimal(str(max_points))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Question points must be a valid decimal value.") from exc
    if not maximum.is_finite():
        raise ValidationError("Question points must be a finite decimal value.")
    question = Question(
        school=subject.school, subject=subject, kind=kind, prompt=prompt,
        choices=choices or [], max_points=maximum,
        correct_answer=correct_answer, position=position,
    )
    question.full_clean()
    question.save(_question_lifecycle_token=QUESTION_LIFECYCLE_TOKEN)
    record_event(
        school=subject.school, actor=user, action="assessment.question_created",
        object_type="assessment_question", object_id=question.pk,
        details={"subject_id": subject.pk, "kind": kind},
    )
    return question


@transaction.atomic
def attach_question(user, assessment, question):
    require_assessment_manager(user, assessment)
    if assessment.status != Assessment.Status.DRAFT:
        raise ValidationError("Questions cannot be attached after the assessment opens.")
    if question.assessment_id is not None or question.school_id != assessment.school_id or question.subject_id != assessment.subject_id:
        raise ValidationError("Choose an unattached question from this school's subject bank.")
    position = assessment.questions.count()
    attached = Question(
        school=question.school, subject=question.subject, assessment=assessment,
        kind=question.kind, prompt=question.prompt, choices=list(question.choices),
        max_points=question.max_points, correct_answer=question.correct_answer,
        position=position,
    )
    attached.full_clean()
    attached.save(_question_lifecycle_token=QUESTION_LIFECYCLE_TOKEN)
    record_event(
        school=assessment.school, actor=user, action="assessment.question_attached",
        object_type="assessment", object_id=assessment.pk,
        details={"question_id": attached.pk, "position": position},
    )
    return attached


@transaction.atomic
def open_assessment(user, assessment):
    require_assessment_manager(user, assessment)
    if assessment.status != Assessment.Status.DRAFT:
        raise ValidationError("Only a draft assessment can be opened.")
    if not assessment.questions.exists():
        raise ValidationError("Add at least one question before opening the assessment.")
    if assessment.closes_at <= timezone.now():
        raise ValidationError("An assessment cannot open after its closing time.")
    assessment.status = Assessment.Status.OPEN
    assessment.save(_assessment_lifecycle_token=ASSESSMENT_LIFECYCLE_TOKEN, update_fields=["status"])
    record_event(
        school=assessment.school, actor=user, action="assessment.opened",
        object_type="assessment", object_id=assessment.pk,
        details={"question_count": assessment.questions.count()},
    )
    return assessment


def _require_student_attempt_access(user, attempt):
    enrollment = _active_student_enrollment(user, attempt.assessment)
    if enrollment is None or enrollment.pk != attempt.enrollment_id:
        raise PermissionDenied("This attempt does not belong to your active enrollment.")


def _require_attempt_owner_or_manager(user, attempt):
    if user.is_authenticated and user.is_active and user.pk == attempt.enrollment.student.user_id:
        _require_student_attempt_access(user, attempt)
        return "student"
    require_assessment_manager(user, attempt.assessment)
    return "manager"


@transaction.atomic
def begin_attempt(assessment, enrollment, actor):
    now = timezone.now()
    if not actor.is_authenticated or enrollment is None:
        raise PermissionDenied("An active student enrollment is required.")
    allowed = _active_student_enrollment(actor, assessment)
    if allowed is None or allowed.pk != enrollment.pk:
        raise PermissionDenied("You may only begin an assessment for your active enrollment.")
    assessment = Assessment.objects.select_for_update().get(pk=assessment.pk)
    if assessment.status != Assessment.Status.OPEN:
        raise ValidationError("This assessment is not open.")
    if now < assessment.opens_at or now >= assessment.closes_at:
        raise ValidationError("This assessment is outside its scheduled window.")
    if not assessment.questions.exists():
        raise ValidationError("This assessment has no questions.")
    count = Attempt.objects.filter(assessment=assessment, enrollment=enrollment).count()
    if count >= assessment.attempt_limit:
        raise ValidationError("You have reached the attempt limit.")
    try:
        attempt = Attempt(
            assessment=assessment, enrollment=enrollment, number=count + 1,
            status=Attempt.Status.IN_PROGRESS, started_at=now,
        )
        attempt.save(_attempt_lifecycle_token=ATTEMPT_LIFECYCLE_TOKEN)
    except IntegrityError as exc:
        raise ValidationError("Could not begin another attempt.") from exc
    for question in assessment.questions.all():
        Answer(attempt=attempt, question=question).save(_answer_lifecycle_token=ANSWER_LIFECYCLE_TOKEN)
    record_event(
        school=assessment.school, actor=actor, action="assessment.attempt_started",
        object_type="assessment_attempt", object_id=attempt.pk,
        details={"assessment_id": assessment.pk, "enrollment_id": str(enrollment.pk), "attempt_number": attempt.number},
    )
    return attempt


@transaction.atomic
def save_answer(attempt, question, response, actor):
    attempt = Attempt.objects.select_for_update().select_related("assessment", "enrollment__student").get(pk=attempt.pk)
    if _require_attempt_owner_or_manager(actor, attempt) != "student":
        raise PermissionDenied("Only the enrolled student may answer an attempt.")
    if attempt.status != Attempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt is already submitted.")
    if timezone.now() >= attempt.assessment.closes_at:
        raise ValidationError("The assessment deadline has passed.")
    if question.assessment_id != attempt.assessment_id:
        raise PermissionDenied("This question is outside the attempt.")
    answer = Answer.objects.get(attempt=attempt, question=question)
    answer.response = str(response)[:10000]
    answer.awarded_points = None if question.kind == Question.Kind.MANUAL else _objective_score(question, answer.response)
    answer.save(_answer_lifecycle_token=ANSWER_LIFECYCLE_TOKEN, update_fields=["response", "awarded_points", "answered_at"])
    return answer


def _objective_score(question, response):
    if question.kind == Question.Kind.MANUAL:
        return None
    normalized_response = " ".join((response or "").strip().casefold().split())
    normalized_key = " ".join((question.correct_answer or "").strip().casefold().split())
    return question.max_points if normalized_response == normalized_key else Decimal("0.00")


@transaction.atomic
def submit_attempt(attempt, actor):
    attempt = Attempt.objects.select_for_update().select_related("assessment", "enrollment__student").get(pk=attempt.pk)
    _require_student_attempt_access(actor, attempt)
    if attempt.status != Attempt.Status.IN_PROGRESS:
        raise ValidationError("This attempt has already been submitted.")
    now = timezone.now()
    if now < attempt.assessment.opens_at:
        raise ValidationError("This assessment is not open yet.")
    # Deadline submission is allowed to preserve the work already entered; further answers are blocked at close.
    for answer in attempt.answers.select_related("question"):
        if answer.question.kind != Question.Kind.MANUAL:
            answer.awarded_points = _objective_score(answer.question, answer.response)
            answer.save(_answer_lifecycle_token=ANSWER_LIFECYCLE_TOKEN, update_fields=["awarded_points", "answered_at"])
    attempt.status = Attempt.Status.SUBMITTED
    attempt.submitted_at = now
    attempt.save(_attempt_lifecycle_token=ATTEMPT_LIFECYCLE_TOKEN, update_fields=["status", "submitted_at"])
    record_event(
        school=attempt.assessment.school, actor=actor, action="assessment.attempt_submitted",
        object_type="assessment_attempt", object_id=attempt.pk,
        details={"assessment_id": attempt.assessment_id, "enrollment_id": str(attempt.enrollment_id)},
    )
    return attempt


@transaction.atomic
def grade_answer(answer, awarded_points, actor, feedback=""):
    answer = Answer.objects.select_for_update().select_related("attempt__assessment", "question").get(pk=answer.pk)
    attempt = Attempt.objects.select_for_update().get(pk=answer.attempt_id)
    require_assessment_manager(actor, attempt.assessment)
    if attempt.status != Attempt.Status.SUBMITTED:
        raise ValidationError("Only submitted attempts can be graded.")
    if answer.question.kind != Question.Kind.MANUAL:
        raise ValidationError("Objective questions are scored automatically.")
    try:
        points = Decimal(str(awarded_points))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Enter a valid decimal score.") from exc
    if not points.is_finite():
        raise ValidationError("Enter a finite decimal score.")
    if points < 0 or points > answer.question.max_points:
        raise ValidationError("Awarded points must be between zero and the question maximum.")
    answer.awarded_points = points
    answer.feedback = feedback[:4000]
    answer.save(_answer_lifecycle_token=ANSWER_LIFECYCLE_TOKEN, update_fields=["awarded_points", "feedback", "answered_at"])
    record_event(
        school=attempt.assessment.school, actor=actor, action="assessment.answer_graded",
        object_type="assessment_answer", object_id=answer.pk,
        details={"assessment_id": attempt.assessment_id, "attempt_id": attempt.pk, "awarded_points": str(points)},
    )
    return answer


def _grade_label(percent, pass_percent):
    if percent < pass_percent:
        return "F"
    if percent >= Decimal("90"):
        return "A"
    if percent >= Decimal("80"):
        return "B"
    if percent >= Decimal("70"):
        return "C"
    return "D"


@transaction.atomic
def finalize_attempt(attempt, actor):
    attempt = Attempt.objects.select_for_update().select_related("assessment").get(pk=attempt.pk)
    assessment = Assessment.objects.select_for_update().get(pk=attempt.assessment_id)
    if not has_school_role(actor, assessment.school, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied("Only an active school admin may moderate and finalize results.")
    if attempt.status != Attempt.Status.SUBMITTED:
        raise ValidationError("Only submitted attempts can be finalized.")
    answers = list(attempt.answers.select_related("question"))
    if any(answer.awarded_points is None for answer in answers):
        raise ValidationError("All manual questions must be graded before finalization.")
    total = sum((answer.question.max_points for answer in answers), Decimal("0.00"))
    raw = sum((answer.awarded_points for answer in answers), Decimal("0.00"))
    percent = (raw * Decimal("100") / total) if total else Decimal("0")
    attempt.status = Attempt.Status.FINALIZED
    attempt.finalized_at = timezone.now()
    attempt.raw_score = raw
    attempt.total_points = total
    attempt.grade_label = _grade_label(percent, assessment.pass_percent)
    attempt.pass_percent_snapshot = assessment.pass_percent
    attempt.grading_policy_version = DEFAULT_GRADING_POLICY_VERSION
    attempt.save(_attempt_lifecycle_token=ATTEMPT_LIFECYCLE_TOKEN, update_fields=[
        "status", "finalized_at", "raw_score", "total_points", "grade_label",
        "pass_percent_snapshot", "grading_policy_version",
    ])
    record_event(
        school=assessment.school, actor=actor, action="assessment.attempt_finalized",
        object_type="assessment_attempt", object_id=attempt.pk,
        details={"assessment_id": assessment.pk, "raw_score": str(raw), "total_points": str(total), "grade_label": attempt.grade_label, "grading_policy_version": DEFAULT_GRADING_POLICY_VERSION},
    )
    return attempt


@transaction.atomic
def publish_attempt(attempt, actor):
    attempt = Attempt.objects.select_for_update().select_related("assessment").get(pk=attempt.pk)
    assessment = Assessment.objects.select_for_update().get(pk=attempt.assessment_id)
    if not has_school_role(actor, assessment.school, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied("Only an active school admin may publish results.")
    if attempt.status != Attempt.Status.FINALIZED:
        raise ValidationError("Only finalized results can be published.")
    attempt.status = Attempt.Status.PUBLISHED
    attempt.published_at = timezone.now()
    attempt.save(_attempt_lifecycle_token=ATTEMPT_LIFECYCLE_TOKEN, update_fields=["status", "published_at"])
    record_event(
        school=assessment.school, actor=actor, action="assessment.result_published",
        object_type="assessment_attempt", object_id=attempt.pk,
        details={"assessment_id": assessment.pk, "enrollment_id": str(attempt.enrollment_id)},
    )
    return attempt


def published_transcript(student, actor):
    """Published results across every historical enrollment, including after promotion."""
    if not actor.is_authenticated or not actor.is_active or not student.school.is_active:
        raise PermissionDenied("An active account and school are required to read a report card.")
    owns_profile = student.user_id == actor.pk and SchoolMembership.objects.filter(
        user=actor, school=student.school, role=SchoolMembership.Role.STUDENT, is_active=True,
    ).exists()
    if not owns_profile and not has_school_role(actor, student.school, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied("You are not authorized to view this student's published report card.")

    attempts = Attempt.objects.filter(
        enrollment__student=student, status=Attempt.Status.PUBLISHED,
    ).select_related("assessment__subject", "assessment__academic_year", "assessment__term", "enrollment").order_by(
        "assessment__academic_year__starts_on", "assessment__term__sort_order", "assessment__subject__name", "assessment__title",
    )
    transcript = {}
    for attempt in attempts:
        year = attempt.assessment.academic_year
        transcript.setdefault(year, []).append({
            "enrollment": attempt.enrollment,
            "subject": attempt.assessment.subject,
            "assessment": attempt.assessment,
            "attempt": attempt,
            "raw_score": attempt.raw_score,
            "total_points": attempt.total_points,
            "grade_label": attempt.grade_label,
            "grading_policy_version": attempt.grading_policy_version,
        })
    return transcript
