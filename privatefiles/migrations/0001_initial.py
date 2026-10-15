import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("learning", "0005_attendancecorrectionrequest_attendance_correction_review_attribution_valid"),
    ]
    operations = [
        migrations.CreateModel(
            name="PrivateAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("storage_key", models.CharField(editable=False, max_length=80, unique=True)),
                ("original_name", models.CharField(max_length=180)),
                ("content_type", models.CharField(max_length=80)),
                ("size", models.PositiveBigIntegerField()),
                ("sha256", models.CharField(max_length=64)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("scan_status", models.CharField(choices=[("clean", "Clean"), ("quarantined", "Quarantined")], max_length=16)),
                ("assignment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="private_attachments", to="learning.assignment")),
                ("submission", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="private_attachments", to="learning.submission")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="private_attachments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["uploaded_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="privateattachment",
            constraint=models.CheckConstraint(condition=(models.Q(("assignment__isnull", False), ("submission__isnull", True)) | models.Q(("assignment__isnull", True), ("submission__isnull", False))), name="private_attachment_one_owner"),
        ),
    ]
