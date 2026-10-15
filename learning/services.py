from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from accounts.models import SchoolMembership
from academics.models import Section
from audit.services import record_event
from .models import (
    AttendanceCorrectionRequest, AttendanceRecord, AttendanceSession, Assignment,
    GradeRevision, Submission, SubmissionRevision, TeacherAssignment,
    _attendance_write_authorized, _correction_write_authorized,
)


def can_manage_section(user, section, subject=None):
    """School admins may manage their school; teachers need a live matching assignment."""
    if not user.is_authenticated:
        return False
    school = section.school_class.school
    if SchoolMembership.objects.filter(
        user=user, user__is_active=True, school=school, school__is_active=True,
        role=SchoolMembership.Role.SCHOOL_ADMIN, is_active=True,
    ).exists():
        return True
    assignments = TeacherAssignment.objects.filter(
        user=user, section=section, is_active=True,
        user__is_active=True,
        user__school_memberships__school=school,
        user__school_memberships__role=SchoolMembership.Role.TEACHER,
        user__school_memberships__is_active=True,
        user__school_memberships__school__is_active=True,
    )
    if subject is not None:
        assignments = assignments.filter(subject=subject)
    return assignments.exists()


def _has_db_school_role(user, school, role):
    return bool(user.is_authenticated and SchoolMembership.objects.filter(
        user=user, user__is_active=True, school=school, school__is_active=True,
        role=role, is_active=True,
    ).exists())


def require_section_access(user, section, subject=None):
    if not can_manage_section(user, section, subject):
        raise PermissionDenied("You are not assigned to manage this section.")


def create_attendance(user, section, attendance_date, statuses):
    """Create one immutable attendance session covering exactly the active roster."""
    require_section_access(user, section)
    from students.models import Enrollment

    roster = Enrollment.objects.filter(section=section, academic_year=section.academic_year, status="active")
    expected = {str(pk) for pk in roster.values_list("pk", flat=True)}
    normalized = {str(key): value for key, value in statuses.items()}
    if set(normalized) != expected:
        raise ValidationError("Attendance must include every active enrollment in this section and no others.")
    allowed = set(AttendanceRecord.Status.values)
    if any(value not in allowed for value in normalized.values()):
        raise ValidationError("Choose a valid attendance status for each student.")
    try:
        with transaction.atomic():
            token = _attendance_write_authorized.set(True)
            try:
                session = AttendanceSession.objects.create(section=section, date=attendance_date, created_by=user)
                AttendanceRecord.objects.bulk_create([
                    AttendanceRecord(session=session, enrollment=enrollment, status=normalized[str(enrollment.pk)])
                    for enrollment in roster
                ])
            finally:
                _attendance_write_authorized.reset(token)
            record_event(
                school=section.school_class.school, actor=user,
                action="learning.attendance_recorded", object_type="attendance_session",
                object_id=session.pk,
                details={"section_id": section.pk, "date": attendance_date.isoformat(), "record_count": len(expected)},
            )
    except IntegrityError as exc:
        raise ValidationError("Attendance has already been recorded for this section and date.") from exc
    return session


def _school_policy(school, key, default):
    from oversight.services import get_school_policy
    return get_school_policy(school, key, default)


def school_local_date(school):
    """Return today's date in the school's configured timezone."""
    from oversight.services import get_school_timezone
    from django.utils import timezone
    return timezone.localdate(timezone=get_school_timezone(school))


def _attendance_correction_is_stale(record):
    window = int(_school_policy(record.session.section.school_class.school, "attendance_correction_days", 7))
    return record.session.date < school_local_date(record.session.section.school_class.school) - timedelta(days=window)


def _save_correction(correction, *, create=False, update_fields=None):
    token = _correction_write_authorized.set(True)
    try:
        if create:
            correction.save(force_insert=True)
        else:
            correction.save(update_fields=update_fields)
    finally:
        _correction_write_authorized.reset(token)
    return correction


@transaction.atomic
def request_attendance_correction(user, attendance_record, *, new_status, reason, new_note=""):
    """Capture a correction proposal without changing the original attendance record."""
    record = AttendanceRecord.objects.select_for_update().select_related(
        "session__section__school_class__school", "session__section", "enrollment"
    ).get(pk=attendance_record.pk)
    require_section_access(user, record.session.section)
    if new_status not in AttendanceRecord.Status.values:
        raise ValidationError("Choose a valid attendance status.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required for an attendance correction.")
    if len(reason) > 500:
        raise ValidationError("The correction reason is too long.")
    if _attendance_correction_is_stale(record):
        raise ValidationError("The attendance correction window has expired.")
    try:
        with transaction.atomic():
            correction = AttendanceCorrectionRequest(
            attendance_record=record, old_status=record.status, old_note=record.note,
            new_status=new_status, new_note=(new_note or "")[:240], reason=reason,
            requested_by=user,
            )
            _save_correction(correction, create=True)
    except IntegrityError as exc:
        raise ValidationError("A correction request is already pending for this attendance record.") from exc
    school = record.session.section.school_class.school
    record_event(
        school=school, actor=user, action="learning.attendance_correction_requested",
        object_type="attendance_correction", object_id=correction.pk,
        details={"attendance_record_id": record.pk, "new_status": new_status},
    )
    return correction


@transaction.atomic
def review_attendance_correction(user, correction, *, approve, review_note=""):
    """School administrators decide a pending correction; approved changes remain attributed."""
    correction = AttendanceCorrectionRequest.objects.select_for_update().select_related(
        "attendance_record__session__section__school_class__school"
    ).get(pk=correction.pk)
    record = AttendanceRecord.objects.select_for_update().get(pk=correction.attendance_record_id)
    school = record.session.section.school_class.school
    if not _has_db_school_role(user, school, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied("Only an active school administrator may review attendance corrections.")
    if correction.status != AttendanceCorrectionRequest.Status.PENDING:
        raise ValidationError("This correction request has already been reviewed.")
    if _attendance_correction_is_stale(record):
        correction.status = AttendanceCorrectionRequest.Status.AUTO_REJECTED
        correction.reviewed_by = None
        correction.reviewed_at = timezone.now()
        correction.review_note = "Automatically rejected because the correction window expired."
        _save_correction(correction, update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
        record_event(school=school, actor=None, action="learning.attendance_correction_auto_rejected",
                     object_type="attendance_correction", object_id=correction.pk,
                     details={"attendance_record_id": record.pk})
        return correction
    correction.status = AttendanceCorrectionRequest.Status.APPROVED if approve else AttendanceCorrectionRequest.Status.REJECTED
    correction.reviewed_by = user
    correction.reviewed_at = timezone.now()
    correction.review_note = (review_note or "")[:500]
    _save_correction(correction, update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
    if approve:
        token = _attendance_write_authorized.set(True)
        try:
            record.status = correction.new_status
            record.note = correction.new_note
            record.save(update_fields=["status", "note"])
        finally:
            _attendance_write_authorized.reset(token)
    record_event(
        school=school, actor=user, action="learning.attendance_correction_approved" if approve else "learning.attendance_correction_rejected",
        object_type="attendance_correction", object_id=correction.pk,
        details={"attendance_record_id": record.pk, "review_note": correction.review_note},
    )
    return correction


@transaction.atomic
def auto_reject_stale_attendance_corrections(school=None):
    """Close stale pending requests with a system-attributed audit event."""
    pending = AttendanceCorrectionRequest.objects.filter(status=AttendanceCorrectionRequest.Status.PENDING).select_related(
        "attendance_record__session__section__school_class__school"
    )
    if school is not None:
        pending = pending.filter(attendance_record__session__section__school_class__school=school)
    rejected = []
    for correction in pending.select_for_update():
        record = correction.attendance_record
        record_school = record.session.section.school_class.school
        if _attendance_correction_is_stale(record):
            correction.status = AttendanceCorrectionRequest.Status.AUTO_REJECTED
            correction.reviewed_at = timezone.now()
            correction.review_note = "Automatically rejected because the correction window expired."
            _save_correction(correction, update_fields=["status", "reviewed_at", "review_note"])
            record_event(school=record_school, actor=None, action="learning.attendance_correction_auto_rejected",
                         object_type="attendance_correction", object_id=correction.pk,
                         details={"attendance_record_id": record.pk})
            rejected.append(correction.pk)
    return rejected


@transaction.atomic
def create_assignment(user, section, subject, *, title, instructions="", due_at=None, publish=False):
    require_section_access(user, section, subject)
    if not TeacherAssignment.objects.filter(user=user, section=section, subject=subject, is_active=True).exists():
        raise PermissionDenied("You are not assigned to teach this subject in this section.")
    assignment = Assignment(
        section=section, subject=subject, teacher=user, title=title,
        instructions=instructions, due_at=due_at, is_published=publish,
    )
    assignment.full_clean()
    assignment.save()
    record_event(
        school=section.school_class.school, actor=user,
        action="learning.assignment_created", object_type="assignment", object_id=assignment.pk,
        details={"section_id": section.pk, "subject_id": subject.pk, "published": bool(publish)},
    )
    return assignment


@transaction.atomic
def submit_assignment(user, assignment, response):
    """Save a student's own submission; never trust an enrollment ID from the request."""
    from students.models import Enrollment

    if not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")
    if not assignment.is_published:
        raise PermissionDenied("This assignment is not published.")
    enrollment = student_enrollment_for_assignment(user, assignment)
    if enrollment is None:
        raise PermissionDenied("You are not an active student in this assignment's section.")
    if assignment.due_at and timezone.now() > assignment.due_at and not bool(
        _school_policy(assignment.section.school_class.school, "late_submission_allowed", True)
    ):
        raise ValidationError("Late submissions are not allowed for this school.")
    submission, created = Submission.objects.get_or_create(
        assignment=assignment, enrollment=enrollment, defaults={"response": response}
    )
    if not created:
        if submission.graded_at is not None:
            raise ValidationError("This response is locked after grading. Contact your teacher if it needs correction.")
        SubmissionRevision.objects.create(
            submission=submission, response=submission.response, submitted_at=submission.submitted_at,
        )
        submission.response = response
        submission.submitted_at = timezone.now()
        submission.save(update_fields=["response", "submitted_at"])
    record_event(
        school=assignment.section.school_class.school, actor=user,
        action="learning.submission_saved", object_type="submission", object_id=submission.pk,
        details={"assignment_id": assignment.pk, "enrollment_id": str(enrollment.pk)},
    )
    return submission


def student_enrollment_for_assignment(user, assignment):
    from students.models import Enrollment

    school = assignment.section.school_class.school
    if not user.is_authenticated:
        return None
    if not SchoolMembership.objects.filter(
        user=user, user__is_active=True, school=school, school__is_active=True,
        role=SchoolMembership.Role.STUDENT, is_active=True,
    ).exists():
        return None
    return Enrollment.objects.filter(
        student__user=user, section=assignment.section,
        academic_year=assignment.section.academic_year, status="active",
    ).first()


@transaction.atomic
def grade_submission(user, submission, *, grade=None, feedback=""):
    require_grade_access(user, submission)
    if submission.graded_at is not None:
        GradeRevision.objects.create(
            submission=submission, grade=submission.grade, feedback=submission.feedback,
            graded_by=submission.graded_by, graded_at=submission.graded_at,
        )
    submission.grade = grade
    submission.feedback = feedback
    submission.graded_by = user
    submission.graded_at = timezone.now()
    submission.full_clean()
    submission.save(update_fields=["grade", "feedback", "graded_by", "graded_at"])
    record_event(
        school=submission.assignment.section.school_class.school, actor=user,
        action="learning.submission_graded", object_type="submission", object_id=submission.pk,
        details={"assignment_id": submission.assignment_id, "enrollment_id": str(submission.enrollment_id)},
    )
    return submission


def require_grade_access(user, submission):
    require_section_access(user, submission.assignment.section, submission.assignment.subject)
    if not _has_db_school_role(user, submission.assignment.section.school_class.school, SchoolMembership.Role.SCHOOL_ADMIN):
        if submission.assignment.teacher_id != user.pk:
            raise PermissionDenied("Only the assignment's teacher may grade this submission.")


def teacher_sections(user):
    """Sections visible to the user through active school admin membership or assignments."""
    if not user.is_authenticated:
        return Section.objects.none()
    admin_school_ids = SchoolMembership.objects.filter(
        user=user, school__is_active=True, is_active=True,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).values_list("school_id", flat=True)
    assigned = TeacherAssignment.objects.filter(
        user=user, user__is_active=True, is_active=True,
        section__school_class__school__is_active=True,
        user__school_memberships__school=F("section__school_class__school"),
        user__school_memberships__is_active=True,
        user__school_memberships__school__is_active=True,
        user__school_memberships__role=SchoolMembership.Role.TEACHER,
    ).values_list("section_id", flat=True)
    return Section.objects.filter(
        Q(pk__in=assigned) | Q(school_class__school_id__in=admin_school_ids)
    ).distinct().order_by("school_class__name", "name")
