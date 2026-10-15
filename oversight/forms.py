import json
from datetime import datetime, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import Section
from learning.models import TeacherAssignment
from schools.models import School
from .models import Notice, SchoolSetting, TimetableSlot


class LocalDateTimeField(forms.DateTimeField):
    """Parse an HTML datetime-local value in the selected school's IANA zone."""

    def __init__(self, *args, timezone_name, **kwargs):
        self.timezone_name = timezone_name
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime):
            result = value
        else:
            parsed = None
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    parsed = datetime.strptime(str(value), fmt)
                    break
                except (TypeError, ValueError):
                    continue
            if parsed is None:
                raise ValidationError("Enter a valid local date and time.")
            result = parsed
        if timezone.is_aware(result):
            return result
        try:
            zone = ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValidationError("The school's timezone is invalid.") from exc
        # Reject nonexistent and ambiguous local times rather than silently shifting
        # a notice's intended publication instant at a daylight-saving transition.
        candidates = []
        for fold in (0, 1):
            aware = result.replace(tzinfo=zone, fold=fold)
            round_trip = aware.astimezone(datetime_timezone.utc).astimezone(zone).replace(tzinfo=None)
            if round_trip == result:
                candidates.append(aware)
        if not candidates:
            raise ValidationError("This local time does not exist in the school's timezone.")
        if len(candidates) == 2 and candidates[0].utcoffset() != candidates[1].utcoffset():
            raise ValidationError("This local time occurs twice in the school's timezone; choose another time.")
        return candidates[0]


def _json_object_field(label, initial=None):
    return forms.CharField(
        label=label,
        required=False,
        initial=json.dumps(initial or {}, ensure_ascii=False, indent=2),
        widget=forms.Textarea(attrs={"rows": 5, "spellcheck": "false"}),
        help_text="Enter a JSON object. Leave blank for no overrides.",
    )


class SchoolSettingForm(forms.ModelForm):
    terminology_json = _json_object_field("Terminology overrides")
    report_branding_json = _json_object_field("Report branding")
    policy_values_json = _json_object_field("Policy values")

    class Meta:
        model = SchoolSetting
        fields = ["contact_name", "contact_email", "contact_phone", "contact_address", "timezone"]
        widgets = {"contact_address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, school, actor, **kwargs):
        self.school = school
        self.actor = actor
        instance = kwargs.get("instance")
        if instance:
            kwargs.setdefault("initial", {})
            kwargs["initial"].update({
                "terminology_json": json.dumps(instance.terminology or {}, ensure_ascii=False, indent=2),
                "report_branding_json": json.dumps(instance.report_branding or {}, ensure_ascii=False, indent=2),
                "policy_values_json": json.dumps(instance.policy_values or {}, ensure_ascii=False, indent=2),
            })
        super().__init__(*args, **kwargs)

    def _parse_json(self, field_name, label):
        raw = self.cleaned_data.get(field_name, "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{label} must be valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValidationError(f"{label} must be a JSON object.")
        return value

    def clean_terminology_json(self):
        return self._parse_json("terminology_json", "Terminology")

    def clean_report_branding_json(self):
        return self._parse_json("report_branding_json", "Report branding")

    def clean_policy_values_json(self):
        return self._parse_json("policy_values_json", "Policy values")

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.school = self.school
        obj.updated_by = self.actor
        obj.terminology = self.cleaned_data["terminology_json"]
        obj.report_branding = self.cleaned_data["report_branding_json"]
        obj.policy_values = self.cleaned_data["policy_values_json"]
        if commit:
            obj.save()
        return obj


class TimetableSlotForm(forms.ModelForm):
    class Meta:
        model = TimetableSlot
        fields = ["assignment", "weekday", "starts_at", "ends_at", "room", "is_active"]
        widgets = {
            "starts_at": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "ends_at": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }

    def __init__(self, *args, school, user, is_admin, **kwargs):
        super().__init__(*args, **kwargs)
        assignments = TeacherAssignment.objects.filter(
            section__school_class__school=school,
            section__school_class__school__is_active=True,
            section__academic_year__school=school,
            is_active=True,
            user__is_active=True,
        ).select_related("section__school_class", "section__academic_year", "subject", "user")
        if not is_admin:
            assignments = assignments.filter(user=user, user__school_memberships__school=school,
                user__school_memberships__role="teacher", user__school_memberships__is_active=True).distinct()
        self.fields["assignment"].queryset = assignments.order_by(
            "section__school_class__name", "section__name", "subject__name", "user__username"
        )
        self.fields.pop("is_active", None)
        self.timezone_label = getattr(getattr(school, "oversight_settings", None), "timezone", "Asia/Karachi")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("starts_at") and cleaned.get("ends_at") and cleaned["ends_at"] <= cleaned["starts_at"]:
            self.add_error("ends_at", "End time must be after start time.")
        return cleaned


class NoticeForm(forms.ModelForm):
    publish_at = forms.DateTimeField(widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}))
    expires_at = forms.DateTimeField(required=False, widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}))

    class Meta:
        model = Notice
        fields = ["section", "title", "body", "audience", "publish_at", "expires_at", "is_published"]
        widgets = {"body": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, school, timezone_name, user, is_admin, **kwargs):
        self.school = school
        self.timezone_name = timezone_name
        super().__init__(*args, **kwargs)
        self.fields["publish_at"] = LocalDateTimeField(
            timezone_name=timezone_name,
            widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            label=f"Publish at ({timezone_name})",
        )
        self.fields["expires_at"] = LocalDateTimeField(
            timezone_name=timezone_name, required=False,
            widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            label=f"Expires at ({timezone_name})",
        )
        sections = Section.objects.filter(
            school_class__school=school, academic_year__school=school,
        ).select_related("school_class", "academic_year").order_by("school_class__name", "name")
        if not is_admin:
            sections = sections.filter(teacher_assignments__user=user, teacher_assignments__is_active=True,
                teacher_assignments__subject__school=school).distinct()
        self.fields["section"].queryset = sections
        self.fields["section"].required = not is_admin
        if self.instance and self.instance.pk:
            zone = ZoneInfo(timezone_name)
            for name in ("publish_at", "expires_at"):
                value = getattr(self.instance, name)
                if value:
                    self.initial[name] = timezone.localtime(value, zone).strftime("%Y-%m-%dT%H:%M")
        self.timezone_label = timezone_name

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.school = self.school
        if commit:
            obj.save()
        return obj
