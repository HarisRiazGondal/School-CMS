from django.contrib.auth.models import AbstractUser
from django.db import models

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

def has_school_role(user, school, *roles):
    return bool(
        user.is_authenticated
        and SchoolMembership.objects.filter(
            user=user, school=school, is_active=True, role__in=roles
        ).exists()
    )
