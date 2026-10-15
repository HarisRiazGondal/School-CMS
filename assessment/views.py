from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from academics.models import Section, Subject
from accounts.models import SchoolMembership, has_school_role
from learning.services import teacher_sections
from students.models import Enrollment
from .forms import AnswerForm, AssessmentForm, AttachQuestionsForm, GradeAnswerForm, QuestionForm, ReportCardSelectForm
from .models import Answer, Assessment, Attempt, Question
from students.models import Student
from oversight.services import get_school_policy
from .services import (
    attach_question, begin_attempt, can_manage_assessment, create_assessment,
    create_question, finalize_attempt, grade_answer, open_assessment,
    publish_attempt, require_assessment_manager, save_answer,
    student_assessments, student_enrollment_for_assessment, submit_attempt,
    teacher_assessments,
)


def _authoring_subjects(user):
    from django.db.models import F
    memberships = SchoolMembership.objects.filter(
        user=user, user__is_active=True, is_active=True,
        school__is_active=True, role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).values_list("school_id", flat=True)
    assigned = Subject.objects.filter(
        teacher_assignments__user=user, teacher_assignments__is_active=True,
        teacher_assignments__section__school_class__school__is_active=True,
        teacher_assignments__user__school_memberships__school=F("school"),
        teacher_assignments__user__school_memberships__role=SchoolMembership.Role.TEACHER,
        teacher_assignments__user__school_memberships__is_active=True,
    )
    return (Subject.objects.filter(school_id__in=memberships) | assigned).distinct().order_by("school__name", "name")


@login_required
def assessment_home(request):
    if getattr(request.user, "student_profile", None):
        if not SchoolMembership.objects.filter(
            user=request.user, school_id=request.user.student_profile.school_id,
            role=SchoolMembership.Role.STUDENT, is_active=True, school__is_active=True,
        ).exists():
            raise PermissionDenied
        now = timezone.now()
        assessments = student_assessments(request.user).filter(opens_at__lte=now, closes_at__gt=now)
        return render(request, "assessment/student_home.html", {"assessments": assessments})
    assessments = teacher_assessments(request.user)
    return render(request, "assessment/teacher_home.html", {"assessments": assessments})


@login_required
@require_http_methods(["GET", "POST"])
def question_create(request):
    form = QuestionForm(request.POST or None)
    form.fields["subject"].queryset = _authoring_subjects(request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            create_question(request.user, subject=data["subject"], kind=data["kind"],
                            prompt=data["prompt"], max_points=data["max_points"],
                            choices=data["choices"], correct_answer=data["correct_answer"])
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Question saved to the school and subject bank.")
            return redirect("assessment:home")
    return render(request, "assessment/question_form.html", {"form": form, "heading": "Add a question to the bank", "submit_label": "Save question"})


@login_required
@require_http_methods(["GET", "POST"])
def assessment_create(request):
    sections = teacher_sections(request.user).filter(school_class__school__is_active=True)
    form = AssessmentForm(request.POST or None, sections=sections)
    # Restrict subject choices to actively assigned teacher subjects and admin schools.
    allowed_subjects = _authoring_subjects(request.user)
    form.fields["subject"].queryset = allowed_subjects
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            assessment = create_assessment(
                request.user, section=data["section"], subject=data["subject"], title=data["title"],
                opens_at=data["opens_at"], closes_at=data["closes_at"],
                attempt_limit=data["attempt_limit"], pass_percent=data["pass_percent"], term=data["term"],
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Draft assessment created. Add questions before opening it.")
            return redirect("assessment:detail", assessment_id=assessment.pk)
    return render(request, "assessment/assessment_form.html", {"form": form, "heading": "Create a scheduled assessment", "submit_label": "Save draft"})


@login_required
def assessment_detail(request, assessment_id):
    assessment = get_object_or_404(Assessment.objects.select_related("school", "section", "subject", "academic_year"), pk=assessment_id)
    manager = can_manage_assessment(request.user, assessment)
    if manager:
        attempts = assessment.attempts.select_related("enrollment__student").prefetch_related("answers__question")
        can_moderate = has_school_role(request.user, assessment.school, SchoolMembership.Role.SCHOOL_ADMIN)
        return render(request, "assessment/detail.html", {"assessment": assessment, "questions": assessment.questions.all(), "attempts": attempts, "can_moderate": can_moderate})
    enrollment = student_enrollment_for_assessment(request.user, assessment)
    own_attempts = Attempt.objects.filter(assessment=assessment, enrollment=enrollment) if enrollment else Attempt.objects.none()
    if not enrollment or (assessment.status != Assessment.Status.OPEN and not own_attempts.exists()):
        raise PermissionDenied
    attempt_rows = list(own_attempts)
    can_start = (
        assessment.status == Assessment.Status.OPEN
        and assessment.opens_at <= timezone.now() < assessment.closes_at
        and len(attempt_rows) < assessment.attempt_limit
        and not any(attempt.status == Attempt.Status.IN_PROGRESS for attempt in attempt_rows)
    )
    return render(request, "assessment/student_detail.html", {
        "assessment": assessment, "attempts": attempt_rows, "can_start": can_start,
        "results_visible": get_school_policy(assessment.school, "student_results_visible", True),
    })


@login_required
@require_http_methods(["GET", "POST"])
def attach_questions(request, assessment_id):
    assessment = get_object_or_404(Assessment.objects.select_related("school", "subject"), pk=assessment_id)
    require_assessment_manager(request.user, assessment)
    if assessment.status != Assessment.Status.DRAFT:
        raise PermissionDenied("Questions are frozen after the assessment opens.")
    form = AttachQuestionsForm(request.POST or None, assessment=assessment)
    if request.method == "POST" and form.is_valid():
        try:
            for question in form.cleaned_data["questions"]:
                attach_question(request.user, assessment, question)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Selected questions were added to this assessment.")
            return redirect("assessment:detail", assessment_id=assessment.pk)
    return render(request, "assessment/attach_form.html", {"assessment": assessment, "form": form, "heading": f"Attach questions to {assessment.title}", "submit_label": "Attach selected questions"})


@login_required
@require_POST
def assessment_open(request, assessment_id):
    assessment = get_object_or_404(Assessment, pk=assessment_id)
    try:
        open_assessment(request.user, assessment)
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Assessment opened for its scheduled window.")
    return redirect("assessment:detail", assessment_id=assessment.pk)


@login_required
@require_POST
def assessment_start(request, assessment_id):
    assessment = get_object_or_404(Assessment, pk=assessment_id)
    enrollment = student_enrollment_for_assessment(request.user, assessment)
    if enrollment is None:
        raise PermissionDenied
    try:
        attempt = begin_attempt(assessment, enrollment, request.user)
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect("assessment:detail", assessment_id=assessment.pk)
    return redirect("assessment:attempt", attempt_id=attempt.pk)


@login_required
def attempt_detail(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("assessment__school", "assessment__section", "enrollment__student"), pk=attempt_id)
    is_owner = attempt.enrollment.student.user_id == request.user.pk
    manager = can_manage_assessment(request.user, attempt.assessment)
    if not is_owner and not manager:
        raise PermissionDenied
    if is_owner:
        enrollment = student_enrollment_for_assessment(request.user, attempt.assessment)
        if enrollment is None or enrollment.pk != attempt.enrollment_id:
            raise PermissionDenied
        if attempt.status != Attempt.Status.IN_PROGRESS:
            return redirect("assessment:detail", assessment_id=attempt.assessment_id)
        form = AnswerForm(questions=attempt.assessment.questions.all(), initial={
            f"answer_{a.question_id}": a.response for a in attempt.answers.all()
        })
        return render(request, "assessment/attempt.html", {"attempt": attempt, "form": form})
    return redirect("assessment:detail", assessment_id=attempt.assessment_id)


@login_required
@require_POST
def attempt_submit(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("assessment", "enrollment__student"), pk=attempt_id)
    if attempt.enrollment.student.user_id != request.user.pk:
        raise PermissionDenied
    enrollment = student_enrollment_for_assessment(request.user, attempt.assessment)
    if enrollment is None or enrollment.pk != attempt.enrollment_id:
        raise PermissionDenied
    form = AnswerForm(request.POST, questions=attempt.assessment.questions.all())
    if not form.is_valid():
        return render(request, "assessment/attempt.html", {"attempt": attempt, "form": form}, status=400)
    late_submit = timezone.now() >= attempt.assessment.closes_at
    try:
        if not late_submit:
            for question, response in form.responses().items():
                save_answer(attempt, question, response, request.user)
        submit_attempt(attempt, request.user)
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect("assessment:attempt", attempt_id=attempt.pk)
    if late_submit:
        messages.success(request, "Time ended. Your last saved answers were submitted; late responses were not saved.")
    else:
        messages.success(request, "Your answers have been submitted.")
    return redirect("assessment:detail", assessment_id=attempt.assessment_id)


@login_required
@require_POST
def attempt_save(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("assessment", "enrollment__student"), pk=attempt_id)
    if attempt.enrollment.student.user_id != request.user.pk:
        raise PermissionDenied
    enrollment = student_enrollment_for_assessment(request.user, attempt.assessment)
    if enrollment is None or enrollment.pk != attempt.enrollment_id:
        raise PermissionDenied
    form = AnswerForm(request.POST, questions=attempt.assessment.questions.all())
    if not form.is_valid():
        return render(request, "assessment/attempt.html", {"attempt": attempt, "form": form}, status=400)
    try:
        for question, response in form.responses().items():
            save_answer(attempt, question, response, request.user)
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))
        return redirect("assessment:attempt", attempt_id=attempt.pk)
    messages.success(request, "Answers saved. Submit them when you are ready.")
    return redirect("assessment:attempt", attempt_id=attempt.pk)


@login_required
@require_http_methods(["GET", "POST"])
def answer_mark(request, answer_id):
    answer = get_object_or_404(Answer.objects.select_related("attempt__assessment__section", "question"), pk=answer_id)
    require_assessment_manager(request.user, answer.attempt.assessment)
    if answer.question.kind != Question.Kind.MANUAL or answer.attempt.status != Attempt.Status.SUBMITTED:
        raise PermissionDenied
    form = GradeAnswerForm(request.POST or None, answer=answer, initial={"awarded_points": answer.awarded_points, "feedback": answer.feedback})
    if request.method == "POST" and form.is_valid():
        try:
            grade_answer(answer, form.cleaned_data["awarded_points"], request.user, form.cleaned_data["feedback"])
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Manual answer marked.")
            return redirect("assessment:detail", assessment_id=answer.attempt.assessment_id)
    return render(request, "assessment/mark_form.html", {"answer": answer, "form": form, "heading": "Mark manual response", "submit_label": "Save mark"})


@login_required
@require_POST
def attempt_finalize(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("assessment"), pk=attempt_id)
    try:
        finalize_attempt(attempt, request.user)
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Attempt finalized; its result is ready to publish.")
    return redirect("assessment:detail", assessment_id=attempt.assessment_id)


@login_required
@require_POST
def attempt_publish(request, attempt_id):
    attempt = get_object_or_404(Attempt.objects.select_related("assessment"), pk=attempt_id)
    try:
        publish_attempt(attempt, request.user)
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Result published to the student.")
    return redirect("assessment:detail", assessment_id=attempt.assessment_id)


@login_required
def report_card(request):
    student = getattr(request.user, "student_profile", None)
    from audit.services import record_event
    from .services import published_transcript
    admin_school_ids = SchoolMembership.objects.filter(
        user=request.user, user__is_active=True, is_active=True,
        school__is_active=True, role=SchoolMembership.Role.SCHOOL_ADMIN,
    ).values_list("school_id", flat=True)
    is_admin = admin_school_ids.exists()
    if not is_admin and student and SchoolMembership.objects.filter(
        user=request.user, school=student.school, role=SchoolMembership.Role.STUDENT,
        is_active=True, school__is_active=True,
    ).exists():
        transcript = published_transcript(student, request.user)
        record_event(school=student.school, actor=request.user, action="assessment.transcript_viewed",
                     object_type="student_transcript", object_id=student.student_code,
                     details={"published_result_count": sum(len(rows) for rows in transcript.values())})
        return render(request, "assessment/report_card.html", {"student": student, "transcript": transcript})

    students = Student.objects.filter(school_id__in=admin_school_ids, school__is_active=True)
    if not students.exists():
        raise PermissionDenied
    form = ReportCardSelectForm(request.GET or None, students=students)
    if not request.GET:
        return render(request, "assessment/report_card.html", {"form": form})
    if not form.is_valid():
        return render(request, "assessment/report_card.html", {"form": form}, status=400)
    selected = form.cleaned_data["student"]
    transcript = published_transcript(selected, request.user)
    record_event(school=selected.school, actor=request.user, action="assessment.transcript_viewed",
                 object_type="student_transcript", object_id=selected.student_code,
                 details={"published_result_count": sum(len(rows) for rows in transcript.values())})
    return render(request, "assessment/report_card.html", {"student": selected, "transcript": transcript, "form": form})
