import json
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


MAX_DETAILS_BYTES = 4096
SENSITIVE_KEY_PARTS = ("password", "passwd", "token", "session", "cookie", "secret", "authorization", "apikey")


def validate_details(details):
    """Validate and bound event details, rejecting credential-like keys at any depth."""
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise ValidationError("Audit details must be a JSON object.")

    def inspect(value, path="details"):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                    raise ValidationError(f"Sensitive key '{key}' is not allowed in audit details.")
                inspect(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, f"{path}[{index}]")

    inspect(details)
    try:
        encoded = json.dumps(details, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("Audit details must contain JSON-compatible values.") from exc
    if len(encoded) > MAX_DETAILS_BYTES:
        raise ValidationError(f"Audit details must not exceed {MAX_DETAILS_BYTES} bytes.")
    return details


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit events are append-only and cannot be updated.")

    def delete(self):
        raise ValidationError("Audit events are append-only and cannot be deleted.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Audit events are append-only and cannot be updated.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Create validated audit events individually through record_event.")


class AuditEvent(models.Model):
    objects = AuditEventQuerySet.as_manager()
    school = models.ForeignKey("schools.School", on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=128)
    details = models.JSONField(default=dict, blank=True, validators=[validate_details])
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp", "-pk"]
        indexes = [models.Index(fields=["school", "-timestamp"], name="audit_school_time_idx")]

    def clean(self):
        super().clean()
        validate_details(self.details)

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit events are append-only and cannot be updated.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are append-only and cannot be deleted.")

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id} ({self.timestamp})"
