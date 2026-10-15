from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

from academics.models import Section, Subject
from .models import AttendanceRecord


class AttendanceEntryForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, roster, **kwargs):
        super().__init__(*args, **kwargs)
        self.roster = roster
        for enrollment in roster:
            self.fields[f"status_{enrollment.pk}"] = forms.ChoiceField(
                label=f"{enrollment.student} ({enrollment.roll_number})",
                choices=AttendanceRecord.Status.choices,
                initial=AttendanceRecord.Status.PRESENT,
            )

    def statuses(self):
        return {str(enrollment.pk): self.cleaned_data[f"status_{enrollment.pk}"] for enrollment in self.roster}


class AttendanceCorrectionForm(forms.Form):
    new_status = forms.ChoiceField(choices=AttendanceRecord.Status.choices, label="Correct status")
    new_note = forms.CharField(required=False, max_length=240, label="Corrected note")
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}),
                             help_text="Explain why this attendance record needs correction.")


class AttendanceCorrectionReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=(("approve", "Approve"), ("reject", "Reject")))
    review_note = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))


class AssignmentForm(forms.Form):
    section = forms.ModelChoiceField(queryset=Section.objects.none())
    subject = forms.ModelChoiceField(queryset=Subject.objects.none())
    title = forms.CharField(max_length=180)
    instructions = forms.CharField(required=False, widget=forms.Textarea)
    due_at = forms.DateTimeField(required=False, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    publish = forms.BooleanField(required=False, initial=True, label="Publish to students")


class SubmissionForm(forms.Form):
    response = forms.CharField(widget=forms.Textarea, label="Your response")


class GradeSubmissionForm(forms.Form):
    grade = forms.DecimalField(required=False, max_digits=6, decimal_places=2,
                               validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("9999.99"))])
    feedback = forms.CharField(required=False, widget=forms.Textarea)

