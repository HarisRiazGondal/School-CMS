from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator

from academics.models import Section, Subject, Term
from students.models import Student
from .models import Question


class QuestionForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=Subject.objects.none())
    kind = forms.ChoiceField(choices=Question.Kind.choices)
    prompt = forms.CharField(widget=forms.Textarea)
    max_points = forms.DecimalField(max_digits=7, decimal_places=2, min_value=Decimal("0.01"))
    choices_text = forms.CharField(required=False, widget=forms.Textarea, label="Choices (one per line)")
    correct_answer = forms.CharField(required=False, widget=forms.Textarea, label="Private answer key")

    def clean(self):
        cleaned = super().clean()
        cleaned["choices"] = [line.strip() for line in cleaned.get("choices_text", "").splitlines() if line.strip()]
        kind = cleaned.get("kind")
        if kind == Question.Kind.MCQ and len(cleaned["choices"]) < 2:
            self.add_error("choices_text", "Add at least two choices for a multiple-choice question.")
        if kind == Question.Kind.MCQ and cleaned.get("correct_answer") not in cleaned["choices"]:
            self.add_error("correct_answer", "Choose an answer that exactly matches one of the choices.")
        if kind == Question.Kind.TRUE_FALSE and cleaned.get("correct_answer", "").lower() not in {"true", "false"}:
            self.add_error("correct_answer", "Enter True or False.")
        if kind == Question.Kind.SHORT_ANSWER and not cleaned.get("correct_answer", "").strip():
            self.add_error("correct_answer", "Add an expected answer for automatic scoring.")
        return cleaned


class AssessmentForm(forms.Form):
    section = forms.ModelChoiceField(queryset=Section.objects.none())
    subject = forms.ModelChoiceField(queryset=Subject.objects.none())
    term = forms.ModelChoiceField(queryset=Term.objects.none(), required=False)
    title = forms.CharField(max_length=180)
    opens_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    closes_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    attempt_limit = forms.IntegerField(min_value=1, max_value=10, initial=1)
    pass_percent = forms.DecimalField(min_value=Decimal("0"), max_value=Decimal("100"), max_digits=5, decimal_places=2, initial=Decimal("50"))

    def __init__(self, *args, sections, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].queryset = sections.select_related("school_class", "academic_year")
        school_ids = sections.values_list("school_class__school_id", flat=True).distinct()
        self.fields["subject"].queryset = Subject.objects.filter(school_id__in=school_ids).order_by("name")
        self.fields["term"].queryset = Term.objects.filter(academic_year__school_id__in=school_ids).order_by("name")

    def clean(self):
        cleaned = super().clean()
        section, subject, term = cleaned.get("section"), cleaned.get("subject"), cleaned.get("term")
        if section and subject and section.school_class.school_id != subject.school_id:
            self.add_error("subject", "Choose a subject from the section's school.")
        if term and section and term.academic_year_id != section.academic_year_id:
            self.add_error("term", "Choose a term from the section's academic year.")
        if cleaned.get("opens_at") and cleaned.get("closes_at") and cleaned["closes_at"] <= cleaned["opens_at"]:
            self.add_error("closes_at", "The closing time must be after the opening time.")
        return cleaned


class AttachQuestionsForm(forms.Form):
    questions = forms.ModelMultipleChoiceField(queryset=Question.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, assessment, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["questions"].queryset = Question.objects.filter(
            school=assessment.school, subject=assessment.subject, assessment__isnull=True,
        ).order_by("position", "pk")


class AnswerForm(forms.Form):
    def __init__(self, *args, questions, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = list(questions)
        for question in self.questions:
            name = f"answer_{question.pk}"
            if question.kind == Question.Kind.MCQ:
                self.fields[name] = forms.ChoiceField(label=question.prompt, choices=[(c, c) for c in question.choices], required=False)
            elif question.kind == Question.Kind.TRUE_FALSE:
                self.fields[name] = forms.ChoiceField(label=question.prompt, choices=[("true", "True"), ("false", "False")], required=False)
            else:
                self.fields[name] = forms.CharField(label=question.prompt, required=False, widget=forms.Textarea)

    def responses(self):
        return {question: self.cleaned_data.get(f"answer_{question.pk}", "") for question in self.questions}


class GradeAnswerForm(forms.Form):
    awarded_points = forms.DecimalField(min_value=Decimal("0"), max_digits=7, decimal_places=2)
    feedback = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, answer, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["awarded_points"].validators.append(MaxValueValidator(answer.question.max_points))


class ReportCardSelectForm(forms.Form):
    student = forms.ModelChoiceField(queryset=Student.objects.none(), label="Student")

    def __init__(self, *args, students, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = students.select_related("school").order_by("school__name", "first_name", "last_name")
