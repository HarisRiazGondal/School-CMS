from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta

from accounts.models import SchoolMembership, active_school_memberships, has_school_role
from academics.models import Section
from learning.models import AttendanceSession, TeacherAssignment
from schools.models import School
from students.models import Enrollment
from .forms import NoticeForm, SchoolSettingForm, TimetableSlotForm
from .models import Notice, SchoolSetting, TimetableSlot
from .services import (
    create_notice, create_timetable_slot,
    get_school_policy, get_school_timezone, require_school_role,
    save_school_setting, scoped_dashboard_summary, teacher_assignments_for_school, teacher_timetable,
    require_notice_access, update_notice,
)

ROLE_ORDER = (
    SchoolMembership.Role.SCHOOL_ADMIN,
    SchoolMembership.Role.REGISTRAR,
    SchoolMembership.Role.TEACHER,
    SchoolMembership.Role.ACCOUNTANT,
    SchoolMembership.Role.STUDENT,
)


def _school_for_membership(user, slug):
    school = get_object_or_404(School, slug=slug, is_active=True)
    memberships = active_school_memberships(user).filter(school=school)
    if not memberships.exists():
        raise PermissionDenied
    roles = set(memberships.values_list("role", flat=True))
    role = next((candidate for candidate in ROLE_ORDER if candidate in roles), None)
    if role is None:
        raise PermissionDenied
    if role == SchoolMembership.Role.TEACHER:
        if not teacher_assignments_for_school(user, school).exists():
            raise PermissionDenied
    if role == SchoolMembership.Role.STUDENT:
        student = getattr(user, "student_profile", None)
        if not student or student.school_id != school.pk:
            raise PermissionDenied
    return school, role


def _visible_notices(user, school, role, sections):
    if role == SchoolMembership.Role.STUDENT:
        audiences = [Notice.Audience.ALL, Notice.Audience.STUDENTS]
    elif role == SchoolMembership.Role.TEACHER:
        audiences = [Notice.Audience.ALL, Notice.Audience.TEACHERS, Notice.Audience.STAFF]
    else:
        audiences = [Notice.Audience.ALL, Notice.Audience.STAFF]
    now = timezone.now()
    qs = Notice.objects.filter(
        school=school, is_published=True, publish_at__lte=now, audience__in=audiences,
    ).filter(
        models_q_expired(now)
    )
    return qs.filter(section__isnull=True) | qs.filter(section__in=sections)


def models_q_expired(now):
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def _branding_and_terms(school):
    setting = SchoolSetting.objects.filter(school=school).first()
    terms = (setting.terminology if setting else {}) or {}
    branding = (setting.report_branding if setting else {}) or {}
    student_term = terms.get("student", "Student")
    teacher_term = terms.get("teacher", "Teacher")
    section_term = terms.get("section", "Section")
    class_term = terms.get("class", "Class")
    return {
        "setting": setting,
        "terms": {"student": student_term, "students": terms.get("students", student_term + "s"),
                  "teacher": teacher_term, "teachers": terms.get("teachers", teacher_term + "s"),
                  "section": section_term, "sections": terms.get("sections", section_term + "s"),
                  "class": class_term, "classes": terms.get("classes", class_term + ("es" if class_term.lower().endswith("s") else "s")),
                  "school": terms.get("school", "School")},
        "branding": branding,
        "brand_name": branding.get("school_name") or school.name,
    }


@login_required
def oversight_home(request):
    memberships = active_school_memberships(request.user).filter(role__in=ROLE_ORDER)
    # A student must have the linked permanent profile as well as an active role.
    if getattr(request.user, "student_profile", None):
        memberships = memberships.filter(school_id=request.user.student_profile.school_id)
    return render(request, "oversight/home.html", {"memberships": memberships})


@login_required
def school_dashboard(request, school_slug):
    school, role = _school_for_membership(request.user, school_slug)
    sections = Section.objects.none()
    slots = TimetableSlot.objects.none()
    if role == SchoolMembership.Role.SCHOOL_ADMIN:
        sections = Section.objects.filter(school_class__school=school, academic_year__school=school)
        slots = TimetableSlot.objects.filter(assignment__section__school_class__school=school, is_active=True)
    elif role == SchoolMembership.Role.TEACHER:
        assignments = teacher_assignments_for_school(request.user, school)
        sections = Section.objects.filter(pk__in=assignments.values("section_id")).distinct()
        slots = teacher_timetable(request.user, school)
    elif role == SchoolMembership.Role.STUDENT:
        enrollment = Enrollment.objects.filter(
            student__user=request.user, student__school=school, status=Enrollment.Status.ACTIVE,
        ).select_related("section").first()
        sections = Section.objects.filter(pk=enrollment.section_id) if enrollment else Section.objects.none()
        slots = TimetableSlot.objects.filter(
            assignment__section__in=sections, is_active=True,
            assignment__is_active=True, assignment__user__is_active=True,
            assignment__subject__school=school,
            assignment__section__school_class__school=school,
            assignment__section__academic_year__school=school,
            assignment__user__school_memberships__school=school,
            assignment__user__school_memberships__role=SchoolMembership.Role.TEACHER,
            assignment__user__school_memberships__is_active=True,
            assignment__user__school_memberships__school__is_active=True,
        ).select_related("assignment__section__school_class", "assignment__subject", "assignment__user").distinct()
    notices = _visible_notices(request.user, school, role, sections).select_related("section").distinct()[:20]
    result_visible = role == SchoolMembership.Role.STUDENT and bool(
        get_school_policy(school, "student_results_visible", True)
    )
    summary = {}
    if role in {SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.REGISTRAR,
                SchoolMembership.Role.TEACHER, SchoolMembership.Role.ACCOUNTANT,
                SchoolMembership.Role.STUDENT}:
        summary = scoped_dashboard_summary(request.user, school)
        if role in {SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.TEACHER}:
            summary["attendance_sessions_7d"] = AttendanceSession.objects.filter(
                section_id__in=sections.values_list("pk", flat=True),
                date__gte=timezone.localdate() - timedelta(days=7),
            ).count()
    context = _branding_and_terms(school)
    context.update({
        "school": school, "role": role, "notices": notices,
        "sections": sections.select_related("school_class", "academic_year")[:30],
        "timetable": slots.select_related("assignment__section__school_class", "assignment__subject", "assignment__user")[:60],
        "timezone_label": getattr(context["setting"], "timezone", "Asia/Karachi"),
        "result_visible": result_visible,
        "summary": summary,
        "finance_balances": summary.get("balances_by_currency"),
        "can_manage": role == SchoolMembership.Role.SCHOOL_ADMIN,
        "can_create_notice": role in {SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.TEACHER},
    })
    return render(request, "oversight/dashboard.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def school_settings(request, school_slug):
    school = get_object_or_404(School, slug=school_slug, is_active=True)
    require_school_role(request.user, school)
    setting = SchoolSetting.objects.filter(school=school).first()
    form = SchoolSettingForm(request.POST or None, instance=setting, school=school, actor=request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            setting = save_school_setting(
                request.user, school,
                terminology=data["terminology_json"],
                contact_name=data["contact_name"], contact_email=data["contact_email"],
                contact_phone=data["contact_phone"], contact_address=data["contact_address"],
                timezone=data["timezone"], report_branding=data["report_branding_json"],
                policy_values=data["policy_values_json"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"School settings saved as version {setting.version}.")
            return redirect("oversight:dashboard", school_slug=school.slug)
    context = _branding_and_terms(school)
    context.update({"school": school, "form": form, "heading": "School settings"})
    return render(request, "oversight/settings_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def timetable_create(request, school_slug):
    school = get_object_or_404(School, slug=school_slug, is_active=True)
    require_school_role(request.user, school)
    form = TimetableSlotForm(request.POST or None, school=school, user=request.user, is_admin=True)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            create_timetable_slot(
                request.user, assignment=data["assignment"], weekday=data["weekday"],
                starts_at=data["starts_at"], ends_at=data["ends_at"], room=data["room"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Timetable slot created.")
            return redirect("oversight:dashboard", school_slug=school.slug)
    context = _branding_and_terms(school)
    context.update({"school": school, "form": form, "heading": "Add a timetable slot", "timezone_label": getattr(getattr(school, "oversight_settings", None), "timezone", "Asia/Karachi")})
    return render(request, "oversight/timetable_form.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def notice_create(request, school_slug):
    school = get_object_or_404(School, slug=school_slug, is_active=True)
    is_admin = has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN)
    assignments = teacher_assignments_for_school(request.user, school) if not is_admin else None
    if not is_admin and (assignments is None or not assignments.exists()):
        raise PermissionDenied
    zone = get_school_timezone(school)
    form = NoticeForm(request.POST or None, school=school, timezone_name=zone.key, user=request.user, is_admin=is_admin)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            create_notice(
                request.user, school=school, title=data["title"], body=data["body"],
                section=data["section"], audience=data["audience"],
                publish_at=data["publish_at"], expires_at=data["expires_at"],
                publish=data["is_published"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Notice saved.")
            return redirect("oversight:notices", school_slug=school.slug)
    context = _branding_and_terms(school)
    context.update({"school": school, "form": form, "heading": "Create a notice", "timezone_label": zone.key})
    return render(request, "oversight/notice_form.html", context)


@login_required
def notices(request, school_slug):
    school, role = _school_for_membership(request.user, school_slug)
    if role == SchoolMembership.Role.STUDENT:
        enrollment = Enrollment.objects.filter(student__user=request.user, student__school=school, status=Enrollment.Status.ACTIVE).first()
        sections = Section.objects.filter(pk=enrollment.section_id) if enrollment else Section.objects.none()
    elif role == SchoolMembership.Role.TEACHER:
        assignments = teacher_assignments_for_school(request.user, school)
        sections = Section.objects.filter(pk__in=assignments.values("section_id")).distinct()
    else:
        sections = Section.objects.none()
    rows = _visible_notices(request.user, school, role, sections).select_related("section").distinct()
    context = _branding_and_terms(school)
    context.update({"school": school, "role": role, "notices": rows, "can_manage": role == SchoolMembership.Role.SCHOOL_ADMIN,
                    "can_create_notice": role in {SchoolMembership.Role.SCHOOL_ADMIN, SchoolMembership.Role.TEACHER},
                    "timezone_label": get_school_timezone(school).key})
    return render(request, "oversight/notices.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def notice_edit(request, school_slug, notice_id):
    school = get_object_or_404(School, slug=school_slug, is_active=True)
    notice = get_object_or_404(Notice, pk=notice_id, school=school)
    require_notice_access(request.user, school, notice.section)
    is_admin = has_school_role(request.user, school, SchoolMembership.Role.SCHOOL_ADMIN)
    zone = get_school_timezone(school)
    form = NoticeForm(request.POST or None, instance=notice, school=school, timezone_name=zone.key,
                      user=request.user, is_admin=is_admin)
    if request.method == "POST" and form.is_valid():
        try:
            update_notice(request.user, notice, **form.cleaned_data)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Notice updated; prior published content remains in its revision history.")
            return redirect("oversight:notices", school_slug=school.slug)
    context = _branding_and_terms(school)
    context.update({"school": school, "form": form, "notice": notice, "heading": "Edit notice", "timezone_label": zone.key})
    return render(request, "oversight/notice_form.html", context)
