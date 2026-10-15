from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy
from django.views.generic import TemplateView

from accounts import views as account_views
from . import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", account_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/mfa/challenge/", account_views.mfa_challenge, name="mfa_challenge"),
    path("accounts/mfa/enroll/", account_views.mfa_enroll, name="mfa_enroll"),
    path("accounts/mfa/disable/", account_views.mfa_disable, name="mfa_disable"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="logged_out"), name="logout"),
    path("accounts/logged-out/", TemplateView.as_view(template_name="registration/logged_out.html"), name="logged_out"),
    path("accounts/password-reset/", account_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.html",
        subject_template_name="registration/password_reset_subject.txt",
        success_url=reverse_lazy("password_reset_done"),
    ), name="password_reset"),
    path("accounts/password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html",
    ), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
        success_url=reverse_lazy("password_reset_complete"),
    ), name="password_reset_confirm"),
    path("accounts/reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html",
    ), name="password_reset_complete"),
    path("", account_views.home, name="home"),
    path("students/", include("students.urls")),
    path("learning/", include("learning.urls")),
    path("assessments/", include("assessment.urls")),
    path("finance/", include("finance.urls")),
    path("oversight/", include("oversight.urls")),
    path("private-files/", include("privatefiles.urls")),
    path("health/live/", health.live, name="health_live"),
    path("health/ready/", health.ready, name="health_ready"),
]
