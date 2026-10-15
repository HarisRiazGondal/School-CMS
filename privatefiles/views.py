from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from learning.models import Assignment, Submission
from learning.services import can_manage_section, student_enrollment_for_assignment
from .forms import PrivateAttachmentForm
from .models import PrivateAttachment
from .services import create_attachment, open_attachment


@login_required
@require_http_methods(["GET", "POST"])
def assignment_upload(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("section__school_class__school", "subject"), pk=assignment_id)
    if not can_manage_section(request.user, assignment.section, assignment.subject):
        raise PermissionDenied
    form = PrivateAttachmentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_attachment(request.user, form.cleaned_data["file"], assignment=assignment)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Attachment uploaded and scanned.")
            return redirect("privatefiles:assignment-upload", assignment_id=assignment.pk)
    return render(request, "privatefiles/upload.html", {
        "form": form, "heading": "Assignment attachments",
        "attachments": assignment.private_attachments.filter(scan_status=PrivateAttachment.ScanStatus.CLEAN),
    })


@login_required
@require_http_methods(["GET", "POST"])
def submission_upload(request, submission_id):
    submission = get_object_or_404(Submission.objects.select_related(
        "assignment__section__school_class__school", "assignment__subject", "enrollment__student"
    ), pk=submission_id)
    active_enrollment = student_enrollment_for_assignment(request.user, submission.assignment)
    if active_enrollment is None or active_enrollment.pk != submission.enrollment_id or submission.enrollment.student.user_id != request.user.pk:
        raise PermissionDenied
    if submission.graded_at:
        raise PermissionDenied("Attachments cannot be added after grading.")
    form = PrivateAttachmentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_attachment(request.user, form.cleaned_data["file"], submission=submission)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Attachment uploaded and scanned.")
            return redirect("privatefiles:submission-upload", submission_id=submission.pk)
    return render(request, "privatefiles/upload.html", {
        "form": form, "heading": "Submission attachments",
        "attachments": submission.private_attachments.filter(scan_status=PrivateAttachment.ScanStatus.CLEAN),
    })


@login_required
@require_GET
def download(request, attachment_id):
    attachment = get_object_or_404(PrivateAttachment.objects.select_related(
        "assignment__section__school_class__school", "assignment__subject",
        "submission__assignment__section__school_class__school", "submission__assignment__subject",
    ), pk=attachment_id)
    try:
        source = open_attachment(request.user, attachment)
    except ValidationError as exc:
        raise Http404 from exc
    response = FileResponse(source, as_attachment=True, filename=attachment.original_name,
                            content_type=attachment.content_type.split(";", 1)[0])
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Content-Length"] = str(attachment.size)
    return response


@login_required
@require_GET
def my_files(request):
    profile = getattr(request.user, "student_profile", None)
    if profile is None or not request.user.is_active:
        raise PermissionDenied
    from accounts.models import SchoolMembership
    if not SchoolMembership.objects.filter(
        user=request.user, user__is_active=True, school_id=profile.school_id,
        school__is_active=True, role=SchoolMembership.Role.STUDENT, is_active=True,
    ).exists():
        raise PermissionDenied
    attachments = PrivateAttachment.objects.filter(
        submission__enrollment__student_id=profile.pk,
        submission__enrollment__student__school_id=profile.school_id,
        scan_status=PrivateAttachment.ScanStatus.CLEAN,
    ).select_related("submission__assignment__section__school_class", "submission__assignment__subject")
    return render(request, "privatefiles/my_files.html", {"attachments": attachments})
