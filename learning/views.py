from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from academics.models import Section, Subject
from accounts.models import SchoolMembership
from students.models import Enrollment
from .forms import (AssignmentForm, AttendanceCorrectionForm, AttendanceCorrectionReviewForm,
                    AttendanceEntryForm, GradeSubmissionForm, SubmissionForm)
from .models import Assignment, AttendanceCorrectionRequest, AttendanceRecord, AttendanceSession, Submission
from .services import (auto_reject_stale_attendance_corrections, create_assignment, create_attendance,
                       grade_submission, require_grade_access, request_attendance_correction,
                       review_attendance_correction, student_enrollment_for_assignment,
                       teacher_sections, submit_assignment, _school_policy)


def _can_view_section(user, section, subject=None):
    from .services import can_manage_section
    return can_manage_section(user, section, subject)


@login_required
def learning_home(request):
    if getattr(request.user, "student_profile", None):
        student_school_memberships = SchoolMembership.objects.filter(
            user=request.user, school_id=request.user.student_profile.school_id,
            user__is_active=True, role=SchoolMembership.Role.STUDENT, is_active=True, school__is_active=True,
        )
        if not student_school_memberships.exists():
            raise PermissionDenied
        enrollments = Enrollment.objects.filter(
            student__user=request.user, student__school_id=request.user.student_profile.school_id,
            student__school__is_active=True, status="active",
        ).select_related(
            "section__school_class", "section__academic_year", "student"
        )
        assignments = Assignment.objects.filter(
            section__enrollments__student__user=request.user,
            section__enrollments__status="active", is_published=True,
            section__school_class__school__is_active=True,
            section__school_class__school_id=request.user.student_profile.school_id,
            section__enrollments__student__school_id=request.user.student_profile.school_id,
            section__enrollments__academic_year=F("section__academic_year"),
        ).select_related("section", "subject", "teacher").distinct()
        now = timezone.now()
        workload = {"upcoming": [], "overdue": [], "completed": [], "graded": []}
        for assignment in assignments:
            enrollment = next((e for e in enrollments if e.section_id == assignment.section_id), None)
            if enrollment is None:
                continue
            submission = Submission.objects.filter(assignment=assignment, enrollment=enrollment).first()
            if submission and submission.graded_at:
                category = "graded"
            elif submission:
                category = "completed"
            elif assignment.due_at and assignment.due_at < now:
                category = "overdue"
            else:
                category = "upcoming"
            workload[category].append({"assignment": assignment, "submission": submission})
        return render(request, "learning/student_home.html", {
            "enrollments": enrollments, "assignments": assignments, "workload": workload,
        })
    sections = teacher_sections(request.user)
    return render(request, "learning/home.html", {"sections": sections})


@login_required
@require_http_methods(["GET", "POST"])
def attendance_entry(request, section_id):
    section = get_object_or_404(Section.objects.select_related("school_class__school", "academic_year"), pk=section_id)
    if not _can_view_section(request.user, section):
        raise PermissionDenied
    roster = list(Enrollment.objects.filter(section=section, academic_year=section.academic_year, status="active").select_related("student").order_by("roll_number"))
    form = AttendanceEntryForm(request.POST or None, roster=roster)
    if request.method == "POST" and form.is_valid():
        try:
            create_attendance(request.user, section, form.cleaned_data["date"], form.statuses())
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Attendance recorded.")
            return redirect("learning:attendance-list", section_id=section.pk)
    return render(request, "learning/attendance_entry.html", {"section": section, "form": form})


@login_required
def attendance_list(request, section_id):
    section = get_object_or_404(Section.objects.select_related("school_class__school"), pk=section_id)
    if not _can_view_section(request.user, section):
        raise PermissionDenied
    sessions = AttendanceSession.objects.filter(section=section).prefetch_related("records__enrollment__student")
    pending_ids = AttendanceCorrectionRequest.objects.filter(
        attendance_record__session__section=section, status=AttendanceCorrectionRequest.Status.PENDING,
    ).values_list("attendance_record_id", flat=True)
    return render(request, "learning/attendance_list.html", {
        "section": section, "sessions": sessions, "pending_correction_ids": set(pending_ids),
        "is_school_admin": SchoolMembership.objects.filter(
            user=request.user, user__is_active=True, school=section.school_class.school,
            school__is_active=True, is_active=True, role=SchoolMembership.Role.SCHOOL_ADMIN,
        ).exists(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def attendance_correction_request(request, record_id):
    record = get_object_or_404(AttendanceRecord.objects.select_related("session__section__school_class__school"), pk=record_id)
    if not _can_view_section(request.user, record.session.section):
        raise PermissionDenied
    form = AttendanceCorrectionForm(request.POST or None, initial={"new_status": record.status, "new_note": record.note})
    if request.method == "POST" and form.is_valid():
        try:
            correction = request_attendance_correction(
                request.user, record, new_status=form.cleaned_data["new_status"],
                new_note=form.cleaned_data["new_note"], reason=form.cleaned_data["reason"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Correction request sent for school administrator review.")
            return redirect("learning:attendance-list", section_id=record.session.section_id)
    return render(request, "learning/attendance_correction_form.html", {"record": record, "form": form})


@login_required
def attendance_correction_queue(request):
    school_ids = list(SchoolMembership.objects.filter(
        user=request.user, user__is_active=True, is_active=True, school__is_active=True,
        role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).values_list("school_id", flat=True))
    if not school_ids:
        raise PermissionDenied
    for school_id in school_ids:
        auto_reject_stale_attendance_corrections(school_id)
    corrections = AttendanceCorrectionRequest.objects.filter(
        status=AttendanceCorrectionRequest.Status.PENDING,
        attendance_record__session__section__school_class__school_id__in=school_ids,
    ).select_related("attendance_record__session__section__school_class", "attendance_record__enrollment__student", "requested_by")
    return render(request, "learning/attendance_correction_queue.html", {"corrections": corrections})


@login_required
@require_http_methods(["GET", "POST"])
def attendance_correction_review(request, correction_id):
    correction = get_object_or_404(AttendanceCorrectionRequest.objects.select_related(
        "attendance_record__session__section__school_class__school"
    ), pk=correction_id)
    school = correction.attendance_record.session.section.school_class.school
    if not SchoolMembership.objects.filter(
        user=request.user, user__is_active=True, school=school, school__is_active=True,
        is_active=True, role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).exists():
        raise PermissionDenied
    if correction.status != AttendanceCorrectionRequest.Status.PENDING:
        return redirect("learning:attendance-correction-queue")
    form = AttendanceCorrectionReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            review_attendance_correction(
                request.user, correction, approve=form.cleaned_data["decision"] == "approve",
                review_note=form.cleaned_data["review_note"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Correction decision recorded.")
            return redirect("learning:attendance-correction-queue")
    return render(request, "learning/attendance_correction_review.html", {"correction": correction, "form": form})


@login_required
def student_attendance_history(request):
    profile = getattr(request.user, "student_profile", None)
    if profile is None or not SchoolMembership.objects.filter(
        user=request.user, user__is_active=True, school_id=profile.school_id, school__is_active=True,
        role=SchoolMembership.Role.STUDENT, is_active=True,
    ).exists():
        raise PermissionDenied
    records = AttendanceRecord.objects.filter(
        enrollment__student_id=profile.pk,
        enrollment__student__school__is_active=True,
        session__section__school_class__school_id=profile.school_id,
    ).select_related("session__section__school_class", "enrollment__academic_year").order_by("-session__date", "-pk")
    return render(request, "learning/student_attendance_history.html", {"records": records})


@login_required
@require_http_methods(["GET", "POST"])
def assignment_create(request):
    sections = teacher_sections(request.user)
    form = AssignmentForm(request.POST or None)
    form.fields["section"].queryset = sections
    # Bound subject choices to sections the caller is permitted to manage.
    form.fields["subject"].queryset = Subject.objects.filter(
        school__in=sections.values("school_class__school")
    ).order_by("name")
    if request.method == "POST" and form.is_valid():
        try:
            assignment = create_assignment(request.user, form.cleaned_data["section"], form.cleaned_data["subject"],
                                           title=form.cleaned_data["title"], instructions=form.cleaned_data["instructions"],
                                           due_at=form.cleaned_data["due_at"], publish=form.cleaned_data["publish"])
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            return redirect("learning:assignment-detail", assignment_id=assignment.pk)
    return render(request, "learning/assignment_form.html", {"form": form})


@login_required
def assignment_detail(request, assignment_id):
    from privatefiles.models import PrivateAttachment
    assignment = get_object_or_404(Assignment.objects.select_related("section__school_class__school", "teacher", "subject"), pk=assignment_id)
    student_access = assignment.is_published and student_enrollment_for_assignment(request.user, assignment) is not None
    if not _can_view_section(request.user, assignment.section, assignment.subject) and not student_access:
        raise PermissionDenied
    if getattr(request.user, "student_profile", None) and assignment.is_published:
        own_submission = Submission.objects.filter(assignment=assignment, enrollment__student__user=request.user).first()
        show_results = bool(_school_policy(assignment.section.school_class.school, "student_results_visible", True))
        late_allowed = bool(_school_policy(assignment.section.school_class.school, "late_submission_allowed", True))
        return render(request, "learning/assignment_detail.html", {
            "assignment": assignment, "own_submission": own_submission, "show_results": show_results,
            "can_submit": not assignment.due_at or assignment.due_at >= timezone.now() or late_allowed,
            "assignment_files": assignment.private_attachments.filter(scan_status=PrivateAttachment.ScanStatus.CLEAN),
            "submission_files": own_submission.private_attachments.filter(scan_status=PrivateAttachment.ScanStatus.CLEAN) if own_submission else [],
        })
    submissions = assignment.submissions.select_related("enrollment__student").prefetch_related("private_attachments") if _can_view_section(request.user, assignment.section, assignment.subject) else None
    return render(request, "learning/assignment_detail.html", {
        "assignment": assignment, "submissions": submissions, "can_upload_material": True,
        "assignment_files": assignment.private_attachments.filter(scan_status=PrivateAttachment.ScanStatus.CLEAN),
    })


@login_required
@require_http_methods(["GET", "POST"])
def assignment_submit(request, assignment_id):
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    enrollment = student_enrollment_for_assignment(request.user, assignment)
    if not assignment.is_published or enrollment is None:
        raise PermissionDenied
    existing = Submission.objects.filter(assignment=assignment, enrollment=enrollment).first()
    if existing and existing.graded_at:
        return redirect("learning:assignment-detail", assignment_id=assignment.pk)
    form = SubmissionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            submission = submit_assignment(request.user, assignment, form.cleaned_data["response"])
        except PermissionDenied as exc:
            raise PermissionDenied from exc
        except ValidationError as exc:
            form.add_error(None, exc)
            return render(request, "learning/submission_form.html", {"assignment": assignment, "form": form})
        return redirect("learning:assignment-detail", assignment_id=assignment.pk)
    return render(request, "learning/submission_form.html", {"assignment": assignment, "form": form})


@login_required
@require_http_methods(["GET", "POST"])
def submission_grade(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("assignment__section__school_class__school", "assignment__subject"),
        pk=submission_id,
    )
    require_grade_access(request.user, submission)
    form = GradeSubmissionForm(request.POST or None, initial={"grade": submission.grade, "feedback": submission.feedback})
    if request.method == "POST" and form.is_valid():
        try:
            grade_submission(request.user, submission, grade=form.cleaned_data["grade"], feedback=form.cleaned_data["feedback"])
        except PermissionDenied:
            raise PermissionDenied
        messages.success(request, "Feedback saved.")
        return redirect("learning:assignment-detail", assignment_id=submission.assignment_id)
    return render(request, "learning/grade_submission.html", {"submission": submission, "form": form})

