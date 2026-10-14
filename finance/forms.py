import uuid
from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from academics.models import SchoolClass
from schools.models import AcademicYear, School
from students.models import Enrollment
from .models import FeePlan


class FeePlanForm(forms.Form):
    academic_year = forms.ModelChoiceField(queryset=AcademicYear.objects.none())
    grade = forms.ModelChoiceField(queryset=SchoolClass.objects.none(), required=False, empty_label="All grades")
    name = forms.CharField(max_length=120, initial="School fee")
    amount = forms.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = forms.CharField(max_length=3, initial="PKR", help_text="Three-letter currency code, such as PKR.")

    def __init__(self, *args, school: School, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(school=school).order_by("-starts_on")
        self.fields["grade"].queryset = SchoolClass.objects.filter(school=school).order_by("name")


class InvoiceIssueForm(forms.Form):
    enrollment = forms.ModelChoiceField(queryset=Enrollment.objects.none(), label="Student enrollment")
    fee_plan = forms.ModelChoiceField(queryset=FeePlan.objects.none())
    concession = forms.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal("0.00"), initial=Decimal("0.00"), help_text="Optional concession for this invoice.")

    def __init__(self, *args, school: School, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["enrollment"].queryset = Enrollment.objects.filter(student__school=school).select_related(
            "student", "academic_year", "section__school_class"
        ).order_by("-academic_year__starts_on", "student__student_code")
        self.fields["fee_plan"].queryset = FeePlan.objects.filter(school=school).select_related("academic_year", "grade").order_by("-academic_year__starts_on", "name")

    def clean(self):
        data = super().clean()
        enrollment, plan = data.get("enrollment"), data.get("fee_plan")
        if enrollment and plan and (enrollment.academic_year_id != plan.academic_year_id or (plan.grade_id and enrollment.section.school_class_id != plan.grade_id)):
            self.add_error("fee_plan", "Choose a plan matching this enrollment's historical year and grade.")
        return data


class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    idempotency_key = forms.CharField(max_length=100, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["idempotency_key"] = uuid.uuid4().hex


class ReversalForm(forms.Form):
    reason = forms.CharField(max_length=240, widget=forms.Textarea(attrs={"rows": 3}))
    confirm = forms.BooleanField(required=True, label="I confirm this payment reversal.")
    idempotency_key = forms.CharField(max_length=100, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["idempotency_key"] = uuid.uuid4().hex
