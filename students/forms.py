from django import forms
from django.core.exceptions import ValidationError

from academics.models import Section
from schools.models import AcademicYear
from .models import Enrollment


class RegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100, required=False)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    academic_year = forms.ModelChoiceField(queryset=AcademicYear.objects.none())
    section = forms.ModelChoiceField(queryset=Section.objects.none())
    roll_number = forms.CharField(max_length=40)
    guardian_name = forms.CharField(max_length=200, required=False)
    guardian_relationship = forms.CharField(max_length=40, required=False)
    guardian_phone = forms.CharField(max_length=40, required=False)
    guardian_email = forms.EmailField(required=False)

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(school=school).order_by("-starts_on")
        self.fields["section"].queryset = Section.objects.filter(school_class__school=school).select_related(
            "school_class", "academic_year"
        ).order_by("academic_year__starts_on", "school_class__sort_order", "school_class__name", "name")
        self.fields["section"].label_from_instance = lambda section: (
            f"{section.academic_year.name} · {section.school_class.name} · {section.name}"
        )

    def clean(self):
        cleaned = super().clean()
        year, section = cleaned.get("academic_year"), cleaned.get("section")
        if year and section and section.academic_year_id != year.pk:
            self.add_error("section", "Choose a section in the selected academic year.")
        return cleaned


class AdmissionApplicationForm(RegistrationForm):
    """Same scoped intake fields as legacy walk-in registration."""


class PromotionForm(forms.Form):
    outcome = forms.ChoiceField(choices=[
        (Enrollment.Status.PROMOTED, "Promote"),
        (Enrollment.Status.REPEATED, "Repeat year"),
        (Enrollment.Status.CONDITIONAL, "Conditional placement"),
        (Enrollment.Status.GRADUATED, "Graduate"),
    ])
    target_year = forms.ModelChoiceField(queryset=AcademicYear.objects.none(), required=False)
    target_section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False)
    roll_number = forms.CharField(max_length=40, required=False)
    condition_reason = forms.CharField(max_length=500, required=False)

    def __init__(self, *args, school, source_year, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.source_year = source_year
        years = AcademicYear.objects.filter(school=school, starts_on__gt=source_year.starts_on).order_by("starts_on")
        self.fields["target_year"].queryset = years
        self.fields["target_section"].queryset = Section.objects.filter(
            school_class__school=school, academic_year__in=years
        ).select_related("school_class", "academic_year").order_by(
            "academic_year__starts_on", "school_class__sort_order", "school_class__name", "name"
        )
        self.fields["target_section"].label_from_instance = lambda section: (
            f"{section.academic_year.name} · {section.school_class.name} · {section.name}"
        )

    def clean(self):
        cleaned = super().clean()
        outcome = cleaned.get("outcome")
        if outcome in {Enrollment.Status.PROMOTED, Enrollment.Status.REPEATED, Enrollment.Status.CONDITIONAL}:
            year, section = cleaned.get("target_year"), cleaned.get("target_section")
            if not year:
                self.add_error("target_year", "Select a target academic year.")
            if not section:
                self.add_error("target_section", "Select a target section.")
            elif year and section.academic_year_id != year.pk:
                self.add_error("target_section", "Choose a section in the selected year.")
            if not cleaned.get("roll_number"):
                cleaned["roll_number"] = ""
            if not cleaned.get("condition_reason", "").strip():
                if outcome == Enrollment.Status.CONDITIONAL:
                    self.add_error("condition_reason", "Explain the conditions for this placement.")
        elif cleaned.get("target_year") or cleaned.get("target_section"):
            raise ValidationError("Graduation does not take a target year or section.")
        return cleaned
