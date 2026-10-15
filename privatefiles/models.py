import uuid

from django.core.exceptions import ValidationError
from django.db import models


class PrivateAttachment(models.Model):
    class ScanStatus(models.TextChoices):
        CLEAN = "clean", "Clean"
        QUARANTINED = "quarantined", "Quarantined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        "learning.Assignment", null=True, blank=True, on_delete=models.PROTECT, related_name="private_attachments",
    )
    submission = models.ForeignKey(
        "learning.Submission", null=True, blank=True, on_delete=models.PROTECT, related_name="private_attachments",
    )
    storage_key = models.CharField(max_length=80, unique=True, editable=False)
    original_name = models.CharField(max_length=180)
    content_type = models.CharField(max_length=80)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="private_attachments")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    scan_status = models.CharField(max_length=16, choices=ScanStatus.choices)

    class Meta:
        ordering = ["uploaded_at", "id"]
        constraints = [models.CheckConstraint(
            condition=(models.Q(assignment__isnull=False, submission__isnull=True)
                       | models.Q(assignment__isnull=True, submission__isnull=False)),
            name="private_attachment_one_owner",
        )]

    def clean(self):
        if bool(self.assignment_id) == bool(self.submission_id):
            raise ValidationError("A private attachment must belong to exactly one assignment or submission.")
        if self.submission_id and self.assignment_id and self.submission.assignment_id != self.assignment_id:
            raise ValidationError("The submission must belong to the same assignment.")

    def __str__(self):
        return f"Private attachment {self.pk}"
