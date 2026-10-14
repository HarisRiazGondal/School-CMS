from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from accounts.models import SchoolMembership, has_school_role
from academics.models import Section
from audit.services import record_event
from .models import AttendanceRecord, AttendanceSession, Assignment, GradeRevision, Submission, SubmissionRevision, TeacherAssignment


def can_manage_section(user, section, subject=None):
    """School admins may manage their school; teachers need a live matching assignment."""
    school = section.school_class.school
    if not school.is_active:
        return False
    if has_school_role(user, school, SchoolMembership.Role.SCHOOL_ADMIN):
        return True
    assignments = TeacherAssignment.objects.filter(
        user=user, section=section, is_active=True,
        user__is_active=True,
        user__school_memberships__school=school,
        user__school_memberships__role=SchoolMembership.Role.TEACHER,
        user__school_memberships__is_active=True,
    )
    if subject is not None:
        assignments = assignments.filter(subject=subject)
    return assignments.exists()


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
            session = AttendanceSession.objects.create(section=section, date=attendance_date, created_by=user)
            AttendanceRecord.objects.bulk_create([
                AttendanceRecord(session=session, enrollment=enrollment, status=normalized[str(enrollment.pk)])
                for enrollment in roster
            ])
            record_event(
                school=section.school_class.school, actor=user,
                action="learning.attendance_recorded", object_type="attendance_session",
                object_id=session.pk,
                details={"section_id": section.pk, "date": attendance_date.isoformat(), "record_count": len(expected)},
            )
    except IntegrityError as exc:
        raise ValidationError("Attendance has already been recorded for this section and date.") from exc
    return session


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

    if not user.is_authenticated or not user.is_active or not assignment.section.school_class.school.is_active:
        raise PermissionDenied("Authentication is required.")
    if not assignment.is_published:
        raise PermissionDenied("This assignment is not published.")
    enrollment = student_enrollment_for_assignment(user, assignment)
    if enrollment is None:
        raise PermissionDenied("You are not an active student in this assignment's section.")
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
    if not user.is_authenticated or not user.is_active or not school.is_active:
        return None
    if not SchoolMembership.objects.filter(
        user=user, school=school, role=SchoolMembership.Role.STUDENT, is_active=True,
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
    if not has_school_role(user, submission.assignment.section.school_class.school, SchoolMembership.Role.SCHOOL_ADMIN):
        if submission.assignment.teacher_id != user.pk:
            raise PermissionDenied("Only the assignment's teacher may grade this submission.")


def teacher_sections(user):
    """Sections visible to the user through active school admin membership or assignments."""
    admin_school_ids = SchoolMembership.objects.filter(
        user=user, school__is_active=True, is_active=True,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).values_list("school_id", flat=True)
    assigned = TeacherAssignment.objects.filter(
        user=user, user__is_active=True, is_active=True,
        section__school_class__school__is_active=True,
        user__school_memberships__school=F("section__school_class__school"),
        user__school_memberships__is_active=True,
        user__school_memberships__role=SchoolMembership.Role.TEACHER,
    ).values_list("section_id", flat=True)
    return Section.objects.filter(
        Q(pk__in=assigned) | Q(school_class__school_id__in=admin_school_ids)
    ).distinct().order_by("school_class__name", "name")
