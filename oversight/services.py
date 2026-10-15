from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings as django_settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import SchoolMembership, User, has_school_role
from audit.services import record_event
from .models import POLICY_DEFAULTS, Notice, NoticeRevision, SchoolSetting, TimetableSlot


def get_school_policy(school, key, default=None):
    """Resolve one allowlisted effective school policy, with stable built-in defaults."""
    if key not in POLICY_DEFAULTS:
        return default
    stored = SchoolSetting.objects.filter(school=school).values_list("policy_values", flat=True).first() or {}
    return stored.get(key, POLICY_DEFAULTS.get(key, default))


def get_school_timezone(school):
    name = SchoolSetting.objects.filter(school=school).values_list("timezone", flat=True).first()
    return ZoneInfo(name or django_settings.TIME_ZONE)


def require_school_role(user, school, role=SchoolMembership.Role.SCHOOL_ADMIN):
    if not has_school_role(user, school, role):
        raise PermissionDenied("You do not have the required active role in this school.")


def require_notice_access(user, school, section):
    """Admins may publish school notices; teachers are limited to assigned sections."""
    if has_school_role(user, school, SchoolMembership.Role.SCHOOL_ADMIN):
        return
    from learning.models import TeacherAssignment

    if section is not None and has_school_role(user, school, SchoolMembership.Role.TEACHER) and TeacherAssignment.objects.filter(
        user=user, section=section, is_active=True, subject__school=school,
        section__school_class__school=school,
    ).exists():
        return
    raise PermissionDenied("Teachers may only manage notices for sections they actively teach.")


def save_school_setting(user, school, **values):
    """Update the singleton settings through the same revisioned model save path."""
    require_school_role(user, school)
    with transaction.atomic():
        type(school).objects.select_for_update().get(pk=school.pk)
        setting = SchoolSetting.objects.select_for_update().filter(school=school).first()
        if setting is None:
            setting = SchoolSetting(school=school)
        allowed = {"terminology", "contact_name", "contact_email", "contact_phone", "contact_address", "timezone", "report_branding", "policy_values"}
        unknown = set(values) - allowed
        if unknown:
            raise ValidationError(f"Unsupported setting fields: {', '.join(sorted(unknown))}.")
        for field, value in values.items():
            setattr(setting, field, value)
        setting.updated_by = user
        setting.save()
        record_event(school=school, actor=user, action="oversight.settings_updated", object_type="school_setting", object_id=setting.pk, details={"version": setting.version})
    return setting


def save_timetable_slot(slot, *args, **kwargs):
    """Serialize timetable checks by teacher and school before checking overlaps."""
    if not slot.assignment_id:
        return super(TimetableSlot, slot).save(*args, **kwargs)
    school = slot.assignment.section.school_class.school
    with transaction.atomic():
        # A teacher may have assignments in several schools. Locking just this
        # school permits two schools to book that teacher at the same time.
        teacher_ids = {slot.assignment.user_id}
        old_school_id = None
        if slot.pk:
            old_assignment = TimetableSlot.objects.filter(pk=slot.pk).values(
                "assignment__user_id", "assignment__section__school_class__school_id"
            ).first()
            if old_assignment:
                teacher_ids.add(old_assignment["assignment__user_id"])
                old_school_id = old_assignment["assignment__section__school_class__school_id"]
        list(User.objects.select_for_update().filter(pk__in=sorted(teacher_ids)).order_by("pk"))
        school_ids = {school.pk}
        if old_school_id:
            school_ids.add(old_school_id)
        list(type(school).objects.select_for_update().filter(pk__in=sorted(school_ids)).order_by("pk"))
        slot.full_clean()
        if slot.is_active:
            overlaps = TimetableSlot.objects.filter(
                is_active=True,
                weekday=slot.weekday,
                starts_at__lt=slot.ends_at,
                ends_at__gt=slot.starts_at,
            ).exclude(pk=slot.pk).select_related("assignment__section__school_class", "assignment__user")
            teacher_conflict = overlaps.filter(assignment__user_id=slot.assignment.user_id).exists()
            section_conflict = overlaps.filter(assignment__section_id=slot.assignment.section_id).exists()
            room_conflict = False
            if slot.room.strip():
                room_matches = overlaps.filter(
                    room__iexact=slot.room.strip(),
                    assignment__section__school_class__school=school,
                )
                if slot.assignment.section.campus_id:
                    room_matches = room_matches.filter(
                        Q(assignment__section__campus__isnull=True)
                        | Q(assignment__section__campus_id=slot.assignment.section.campus_id)
                    )
                room_conflict = room_matches.exists()
            if teacher_conflict:
                raise ValidationError({"assignment": "This teacher already has a timetable slot at an overlapping time."})
            if section_conflict:
                raise ValidationError({"assignment": "This section already has a timetable slot at an overlapping time."})
            if room_conflict:
                raise ValidationError({"room": "This room is already booked at an overlapping time."})
        return super(TimetableSlot, slot).save(*args, **kwargs)


@transaction.atomic
def create_timetable_slot(user, *, assignment, weekday, starts_at, ends_at, room=""):
    school = assignment.section.school_class.school
    require_school_role(user, school)
    slot = TimetableSlot(
        assignment=assignment, weekday=weekday, starts_at=starts_at, ends_at=ends_at,
        room=room, created_by=user,
    )
    slot.save()
    record_event(school=school, actor=user, action="oversight.timetable_slot_created", object_type="timetable_slot", object_id=slot.pk, details={"section_id": assignment.section_id, "subject_id": assignment.subject_id, "weekday": weekday})
    return slot


def notice_snapshot(notice):
    return {
        "school_id": str(notice.school_id), "section_id": notice.section_id,
        "title": notice.title, "body": notice.body, "audience": notice.audience,
        "publish_at": notice.publish_at.isoformat() if notice.publish_at else None,
        "expires_at": notice.expires_at.isoformat() if notice.expires_at else None,
        "is_published": notice.is_published,
    }


def save_notice(notice, *args, **kwargs):
    """Apply configured default expiry and retain the prior published version before edits."""
    with transaction.atomic():
        require_notice_access(notice.updated_by or notice.created_by, notice.school, notice.section)
        previous = None
        if notice.pk:
            previous = Notice.objects.select_for_update().filter(pk=notice.pk).first()
        if notice.is_published and notice.expires_at is None:
            days = get_school_policy(notice.school, "notice_expiry_days", 0)
            if days:
                notice.expires_at = (notice.publish_at or timezone.now()) + timedelta(days=days)
        if previous and previous.is_published:
            NoticeRevision.objects.create(
                notice=previous,
                snapshot=notice_snapshot(previous),
                changed_by=getattr(notice, "updated_by", None) or notice.created_by,
            )
        saved = super(Notice, notice).save(*args, **kwargs)
        if previous:
            record_event(
                school=previous.school, actor=notice.updated_by,
                action="oversight.notice_updated", object_type="notice", object_id=notice.pk,
                details={"published_revision_created": bool(previous.is_published)},
            )
        return saved


@transaction.atomic
def create_notice(user, *, school, title, body, section=None, audience=Notice.Audience.ALL, publish_at=None, expires_at=None, publish=False):
    require_notice_access(user, school, section)
    notice = Notice(
        school=school, section=section, title=title, body=body, audience=audience,
        publish_at=publish_at or timezone.now(), expires_at=expires_at,
        is_published=publish, created_by=user,
    )
    notice.save()
    record_event(school=school, actor=user, action="oversight.notice_created", object_type="notice", object_id=notice.pk, details={"published": bool(publish), "audience": audience, "section_id": section.pk if section else None})
    return notice


@transaction.atomic
def update_notice(user, notice, **values):
    """Authorize both the persisted scope and target scope before a revisioned edit."""
    allowed = {"section", "title", "body", "audience", "publish_at", "expires_at", "is_published"}
    unknown = set(values) - allowed
    if unknown:
        raise ValidationError(f"Unsupported notice fields: {', '.join(sorted(unknown))}.")
    notice = Notice.objects.select_for_update().select_related("school", "section").get(pk=notice.pk)
    require_notice_access(user, notice.school, notice.section)
    target_section = values.get("section", notice.section)
    require_notice_access(user, notice.school, target_section)
    for field, value in values.items():
        setattr(notice, field, value)
    notice.updated_by = user
    notice.save()
    return notice


def teacher_assignments_for_school(user, school):
    """Return only active exact teacher/subject/section scope with live teacher membership."""
    from learning.models import TeacherAssignment

    return TeacherAssignment.objects.filter(
        user=user, is_active=True, user__is_active=True,
        section__school_class__school=school, section__school_class__school__is_active=True,
        user__school_memberships__school=school, user__school_memberships__role=SchoolMembership.Role.TEACHER,
        user__school_memberships__is_active=True, user__school_memberships__school__is_active=True,
    ).select_related("section", "subject", "user", "section__academic_year", "section__school_class").distinct()


def teacher_timetable(user, school):
    return TimetableSlot.objects.filter(
        is_active=True, assignment__in=teacher_assignments_for_school(user, school),
    ).select_related("assignment__section__school_class", "assignment__subject", "assignment__user")


def accountant_finance_only(user, school):
    """Require the accountant role before exposing any finance-only balance summary."""
    require_school_role(user, school, SchoolMembership.Role.ACCOUNTANT)
    from finance.models import Invoice, MONEY_ZERO

    balances = {}
    for invoice in Invoice.objects.filter(school=school).prefetch_related("entries"):
        balances.setdefault(invoice.currency, MONEY_ZERO)
        balances[invoice.currency] += sum((entry.amount for entry in invoice.entries.all()), MONEY_ZERO)
    return balances


def scoped_dashboard_summary(user, school):
    """Return role-bounded operational counts for the school dashboard."""
    if has_school_role(user, school, SchoolMembership.Role.SCHOOL_ADMIN):
        from assessment.models import Attempt
        from learning.models import AttendanceCorrectionRequest, AttendanceRecord
        from students.models import AdmissionApplication, Enrollment

        published_attempts = Attempt.objects.filter(
            assessment__school=school, assessment__section__school_class__school=school,
            enrollment__student__school=school, status=Attempt.Status.PUBLISHED,
        )
        result_distribution = {}
        for grade in published_attempts.values_list("grade_label", flat=True):
            result_distribution[grade] = result_distribution.get(grade, 0) + 1
        attendance_status_counts = {}
        for status in AttendanceRecord.objects.filter(
            enrollment__student__school=school,
            session__section__school_class__school=school,
        ).values_list("status", flat=True):
            attendance_status_counts[status] = attendance_status_counts.get(status, 0) + 1
        return {
            "role": SchoolMembership.Role.SCHOOL_ADMIN,
            "active_enrollments": Enrollment.objects.filter(
                student__school=school, academic_year__school=school,
                section__school_class__school=school, status=Enrollment.Status.ACTIVE,
            ).count(),
            "pending_admissions": AdmissionApplication.objects.filter(
                school=school, status=AdmissionApplication.Status.PENDING,
            ).count(),
            "pending_attendance_corrections": AttendanceCorrectionRequest.objects.filter(
                status=AttendanceCorrectionRequest.Status.PENDING,
                attendance_record__enrollment__student__school=school,
            ).count(),
            "attendance_status_counts": attendance_status_counts,
            "published_attempts": published_attempts.count(),
            "result_distribution": result_distribution,
        }

    if has_school_role(user, school, SchoolMembership.Role.REGISTRAR):
        from students.models import AdmissionApplication, Enrollment

        return {
            "role": SchoolMembership.Role.REGISTRAR,
            "active_enrollments": Enrollment.objects.filter(
                student__school=school, academic_year__school=school,
                section__school_class__school=school, status=Enrollment.Status.ACTIVE,
            ).count(),
            "pending_admissions": AdmissionApplication.objects.filter(
                school=school, status=AdmissionApplication.Status.PENDING,
            ).count(),
        }

    if has_school_role(user, school, SchoolMembership.Role.TEACHER):
        from assessment.models import Attempt, Assessment
        from learning.models import Submission

        assignments = teacher_assignments_for_school(user, school)
        section_subject = assignments.values_list("section_id", "subject_id")
        submitted = Submission.objects.filter(
            assignment__teacher=user,
            assignment__section__school_class__school=school,
            assignment__section_id__in=assignments.values_list("section_id", flat=True),
            assignment__subject_id__in=assignments.values_list("subject_id", flat=True),
            graded_at__isnull=True,
        )
        # Filter the exact active assignment pairs, avoiding cross-combinations
        # where a teacher has multiple sections and subjects.
        exact = Q()
        for section_id, subject_id in section_subject:
            exact |= Q(assignment__section_id=section_id, assignment__subject_id=subject_id)
        pending_submissions = submitted.filter(exact).count() if section_subject else 0
        assessment_data = {"published_attempts": 0, "result_distribution": {}}
        owned_assessments = Assessment.objects.filter(
            school=school, section_id__in=assignments.values_list("section_id", flat=True),
            subject_id__in=assignments.values_list("subject_id", flat=True),
        )
        # Keep the section/subject pairing exact for an overlapping teacher portfolio.
        owned_pairs = Q()
        for section_id, subject_id in section_subject:
            owned_pairs |= Q(section_id=section_id, subject_id=subject_id)
        owned_assessments = owned_assessments.filter(owned_pairs) if section_subject else owned_assessments.none()
        published_attempts = Attempt.objects.filter(
            assessment__in=owned_assessments, status=Attempt.Status.PUBLISHED,
        )
        assessment_data["published_attempts"] = published_attempts.count()
        distribution = {}
        for grade in published_attempts.values_list("grade_label", flat=True):
            distribution[grade] = distribution.get(grade, 0) + 1
        assessment_data["result_distribution"] = distribution
        return {
            "role": SchoolMembership.Role.TEACHER,
            "active_assignments": assignments.count(),
            "pending_submissions": pending_submissions,
            **assessment_data,
        }

    if has_school_role(user, school, SchoolMembership.Role.ACCOUNTANT):
        return {
            "role": SchoolMembership.Role.ACCOUNTANT,
            "balances_by_currency": accountant_finance_only(user, school),
        }

    if has_school_role(user, school, SchoolMembership.Role.STUDENT):
        from assessment.models import Attempt
        from learning.models import AttendanceRecord
        from students.models import Student

        student = Student.objects.filter(user=user, school=school).first()
        attendance_status_counts = {}
        result_distribution = {}
        published_attempts = 0
        if student is not None:
            for status in AttendanceRecord.objects.filter(
                enrollment__student=student,
                session__section__school_class__school=school,
            ).values_list("status", flat=True):
                attendance_status_counts[status] = attendance_status_counts.get(status, 0) + 1
            if get_school_policy(school, "student_results_visible", True):
                results = Attempt.objects.filter(
                    enrollment__student=student, assessment__school=school,
                    status=Attempt.Status.PUBLISHED,
                )
                published_attempts = results.count()
                for grade in results.values_list("grade_label", flat=True):
                    result_distribution[grade] = result_distribution.get(grade, 0) + 1
        return {
            "role": SchoolMembership.Role.STUDENT,
            "attendance_status_counts": attendance_status_counts,
            "published_attempts": published_attempts,
            "result_distribution": result_distribution,
        }

    raise PermissionDenied("This role has no oversight dashboard access.")
