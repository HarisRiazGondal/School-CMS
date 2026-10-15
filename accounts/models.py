from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class User(AbstractUser):
    email = models.EmailField(unique=True)

class SchoolMembership(models.Model):
    class Role(models.TextChoices):
        SCHOOL_ADMIN = "school_admin", "School admin"
        REGISTRAR = "registrar", "Registrar"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"
        ACCOUNTANT = "accountant", "Accountant"

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="school_memberships")
    school = models.ForeignKey("schools.School", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=24, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "role"],
                name="uniq_user_school_role",
            )
        ]

    def __str__(self):
        return f"{self.user} / {self.school} / {self.get_role_display()}"


class AuthThrottle(models.Model):
    """Database-backed fixed-window throttle shared by all application workers."""
    key = models.CharField(max_length=64, primary_key=True)
    window_started = models.DateTimeField()
    failures = models.PositiveSmallIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["window_started", "blocked_until"], name="auththr_stale_idx"),
        ]


class MFADevice(models.Model):
    """TOTP configuration; the encrypted secret is unusable without a separate key."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_device")
    encrypted_secret = models.TextField()
    enabled = models.BooleanField(default=False)
    last_accepted_step = models.BigIntegerField(default=-1)
    created_at = models.DateTimeField(auto_now_add=True)


class MFARecoveryCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_recovery_codes")
    code_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

def has_school_role(user, school, *roles):
    return bool(
        user.is_authenticated
        and user.is_active
        and school.is_active
        and SchoolMembership.objects.filter(
            user=user, user__is_active=True, school=school, school__is_active=True, is_active=True, role__in=roles
        ).exists()
    )


def active_school_memberships(user):
    """Return the user's currently usable school roles, with active schools only."""
    if not user.is_authenticated or not user.is_active:
        return SchoolMembership.objects.none()
    return SchoolMembership.objects.filter(
        user=user, user__is_active=True, is_active=True, school__is_active=True
    ).select_related("school").order_by("school__name", "role")
