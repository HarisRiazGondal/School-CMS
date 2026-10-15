from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.models import SchoolMembership, has_school_role
from academics.models import Section
from audit.services import record_event
from schools.models import School
from .forms import AdmissionApplicationForm, PromotionForm, RegistrationForm
from .models import AdmissionApplication, Enrollment, Student
from .services import (
    commit_batch_promotion, commit_promotion, decide_admission_application,
    preview_batch_promotion, preview_promotion, register_student,
    submit_admission_application,
)


def _school_for(user, slug):
    school = get_object_or_404(School, slug=slug, is_active=True)
    if not has_school_role(user, school, SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.REGISTRAR):
        raise PermissionDenied
    return school


@login_required
@require_http_methods(["GET"])
def student_list(request, school_slug):
    school = _school_for(request.user, school_slug)
    students = Student.objects.filter(school=school).prefetch_related("enrollments__section__school_class")
    record_event(school=school, actor=request.user, action="student.list_viewed",
                 object_type="student_list", object_id=school.slug,
                 details={"result_count": students.count()})
    return render(request, "students/list.html", {"school": school, "students": students})


@login_required
@require_http_methods(["GET", "POST"])
def student_register(request, school_slug):
    school = _school_for(request.user, school_slug)
    if request.method == "GET":
        record_event(school=school, actor=request.user, action="student.register_viewed",
                     object_type="student_registration", object_id=school.slug)
    form = RegistrationForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        try:
            student, enrollment = register_student(user=request.user, school=school, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Registered {student.student_code}.")
            return redirect("students:detail", school_slug=school.slug, student_code=student.student_code)
    return render(request, "students/register.html", {"school": school, "form": form})


@login_required
@require_http_methods(["GET"])
def admissions_list(request, school_slug):
    school = _school_for(request.user, school_slug)
    applications = AdmissionApplication.objects.filter(school=school).select_related(
        "academic_year", "section__school_class", "student"
    )
    return render(request, "students/admissions.html", {"school": school, "applications": applications})


@login_required
@require_http_methods(["GET", "POST"])
def admission_intake(request, school_slug):
    school = _school_for(request.user, school_slug)
    form = AdmissionApplicationForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        try:
            application = submit_admission_application(user=request.user, school=school, **form.cleaned_data)
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Admission application added to the pending queue.")
            return redirect("students:admissions", school_slug=school.slug)
    return render(request, "students/admission_intake.html", {"school": school, "form": form})


@login_required
@require_http_methods(["POST"])
def admission_decision(request, school_slug, application_id):
    school = _school_for(request.user, school_slug)
    application = get_object_or_404(AdmissionApplication, school=school, pk=application_id)
    decision = request.POST.get("decision", "")
    try:
        decided, student, enrollment = decide_admission_application(
            user=request.user, application=application, decision=decision, note=request.POST.get("note", "")
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Application {decided.get_status_display().lower()}." + (f" Student {student.student_code} registered." if student else ""))
    return redirect("students:admissions", school_slug=school.slug)


def _batch_rows_from_post(post):
    keys = ("source_id", "outcome", "target_year", "target_section", "roll_number", "condition_reason")
    values = {key: post.getlist(key) for key in keys}
    count = max((len(items) for items in values.values()), default=0)
    rows = []
    for index in range(count):
        rows.append({key: items[index] if index < len(items) else "" for key, items in values.items()})
    return rows


@login_required
@require_http_methods(["GET", "POST"])
def batch_promotion_view(request, school_slug):
    school = _school_for(request.user, school_slug)
    active = Enrollment.objects.filter(student__school=school, status=Enrollment.Status.ACTIVE).select_related(
        "student", "academic_year", "section__school_class"
    ).order_by("academic_year__starts_on", "section__school_class__sort_order", "section__name", "roll_number")
    plans = None
    rows = []
    if request.method == "POST":
        rows = _batch_rows_from_post(request.POST)
        if request.POST.get("confirm") == "1":
            if not has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN):
                raise PermissionDenied("Only a school admin can confirm batch outcomes.")
            try:
                results = commit_batch_promotion(user=request.user, school=school, rows=rows)
            except (ValidationError, PermissionDenied) as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Processed {len(results)} enrollment outcomes.")
                return redirect("students:batch-promotion", school_slug=school.slug)
        else:
            try:
                plans = preview_batch_promotion(user=request.user, school=school, rows=rows)
            except (ValidationError, PermissionDenied) as exc:
                messages.error(request, str(exc))
    sections = Section.objects.filter(school_class__school=school).select_related("school_class", "academic_year").order_by(
        "academic_year__starts_on", "school_class__sort_order", "name"
    )
    years = school.academic_years.order_by("starts_on")
    return render(request, "students/batch_promotion.html", {
        "school": school, "enrollments": active, "plans": plans, "rows": rows,
        "sections": sections, "years": years,
        "can_confirm": has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN),
        "can_confirm_batch": bool(plans) and all(plan.can_commit for plan in plans)
            and has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN),
    })


@login_required
@require_http_methods(["GET"])
def student_detail(request, school_slug, student_code):
    school = _school_for(request.user, school_slug)
    student = get_object_or_404(
        Student.objects.filter(school=school).prefetch_related(
            "enrollments__section__school_class", "enrollments__academic_year", "guardian_relations__guardian"
        ), student_code=student_code
    )
    record_event(school=school, actor=request.user, action="student.history_viewed",
                 object_type="student", object_id=student.student_code,
                 details={"enrollment_count": student.enrollments.count()})
    return render(request, "students/detail.html", {"school": school, "student": student})


def _source_enrollment(user, school, student_code, year_name):
    student = get_object_or_404(Student, school=school, student_code=student_code)
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student__school", "academic_year", "section__school_class"),
        student=student, academic_year__name=year_name,
    )
    return enrollment


@login_required
@require_http_methods(["GET", "POST"])
def promotion_preview_view(request, school_slug, student_code, year_name):
    school = _school_for(request.user, school_slug)
    source = _source_enrollment(request.user, school, student_code, year_name)
    form = PromotionForm(request.POST or None, school=school, source_year=source.academic_year)
    preview = None
    if request.method == "POST" and form.is_valid():
        try:
            preview = preview_promotion(
                user=request.user, source=source, outcome=form.cleaned_data["outcome"],
                target_year=form.cleaned_data.get("target_year"),
                target_section=form.cleaned_data.get("target_section"),
                target_roll_number=form.cleaned_data.get("roll_number"),
                condition_reason=form.cleaned_data.get("condition_reason", ""),
            )
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc)
    return render(request, "students/promotion_preview.html", {
        "school": school, "student": source.student, "source": source,
        "form": form, "preview": preview,
        "can_confirm": has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN),
    })


@login_required
@require_http_methods(["POST"])
def promotion_commit_view(request, school_slug, student_code, year_name):
    school = _school_for(request.user, school_slug)
    if not has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN):
        raise PermissionDenied("Only a school admin can confirm promotion.")
    source = _source_enrollment(request.user, school, student_code, year_name)
    form = PromotionForm(request.POST, school=school, source_year=source.academic_year)
    if not form.is_valid():
        messages.error(request, "Promotion details were invalid; review them and try again.")
        return redirect("students:promotion-preview", school_slug=school.slug, student_code=student_code, year_name=year_name)
    try:
        old, new = commit_promotion(user=request.user, source=source, **form.cleaned_data)
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
        return redirect("students:detail", school_slug=school.slug, student_code=student_code)
    messages.success(request, f"{old.get_status_display()} recorded for {student_code}.")
    return redirect("students:detail", school_slug=school.slug, student_code=student_code)
