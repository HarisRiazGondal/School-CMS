import hmac
import pyotp
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.views import LoginView as DjangoLoginView, PasswordResetView as DjangoPasswordResetView
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .auth_security import (
    auth_throttle_keys, clear_mfa_failures, clear_mfa_pending, consume_recovery_code, decrypt_secret, encrypt_secret,
    hash_recovery_codes, is_throttled, make_recovery_codes,
    mfa_attempt_blocked, new_totp_secret, record_auth_failure, record_mfa_failure,
    requires_mfa, start_mfa_pending,
)
from .models import MFADevice, User

from .models import active_school_memberships


@login_required
def home(request):
    return render(request, "accounts/home.html", {
        "memberships": active_school_memberships(request.user),
        "mfa_enabled": MFADevice.objects.filter(user=request.user, enabled=True).exists(),
        "mfa_required": requires_mfa(request.user),
    })


class LoginView(DjangoLoginView):
    """Password login that holds privileged accounts outside auth until MFA passes."""
    template_name = "registration/login.html"

    def form_valid(self, form):
        user = form.get_user()
        if requires_mfa(user):
            start_mfa_pending(self.request, user, user.backend, self.get_success_url())
            if MFADevice.objects.filter(user=user, enabled=True).exists():
                return redirect("mfa_challenge")
            return redirect("mfa_enroll")
        response = super().form_valid(form)
        clear_mfa_pending(self.request)
        self.request.session["mfa_verified"] = False
        return response


class PasswordResetView(DjangoPasswordResetView):
    """Enumeration-safe Django reset flow with per-IP/email DB abuse throttling."""
    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "")
        keys = auth_throttle_keys("reset", email, request)
        if any(is_throttled(key) for key in keys):
            return HttpResponseRedirect(self.get_success_url())
        record_auth_failure("reset", email, request)
        return super().post(request, *args, **kwargs)


def _pending_user(request):
    user_id = request.session.get("mfa_pending_user_id")
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    created = request.session.get("mfa_pending_at")
    expected_hash = request.session.get("mfa_pending_auth_hash", "")
    valid = bool(
        user and created and timezone.now().timestamp() - float(created) < 300
        and expected_hash and hmac.compare_digest(expected_hash, user.get_session_auth_hash())
    )
    if not valid:
        clear_mfa_pending(request)
        return None
    return user


def _device_step(device, code):
    try:
        secret = decrypt_secret(device.encrypted_secret)
    except (ImproperlyConfigured, ValueError):
        # Fail closed without exposing key material or ciphertext in an error page.
        return None
    current = int(timezone.now().timestamp() // 30)
    try:
        for step in (current - 1, current, current + 1):
            if step > device.last_accepted_step and pyotp.TOTP(secret).verify(code, for_time=step * 30, valid_window=0):
                return step
    except ValueError:
        return None
    return None


@sensitive_post_parameters("code", "password")
@require_http_methods(["GET", "POST"])
def mfa_challenge(request):
    user = _pending_user(request)
    if not user or not requires_mfa(user):
        request.session.pop("mfa_pending_user_id", None)
        return redirect("login")
    device = MFADevice.objects.filter(user=user, enabled=True).first()
    if not device:
        return redirect("mfa_enroll")
    error = None
    if request.method == "POST":
        if mfa_attempt_blocked(request, user):
            return render(request, "accounts/mfa_challenge.html", {
                "error": "Too many verification attempts. Try again in 15 minutes."
            }, status=429)
        code = request.POST.get("code", "").strip()
        step = _device_step(device, code)
        if step is not None:
            with transaction.atomic():
                locked = MFADevice.objects.select_for_update().get(pk=device.pk)
                if step > locked.last_accepted_step:
                    locked.last_accepted_step = step
                    locked.save(update_fields=["last_accepted_step"])
                else:
                    step = None
        if step is None and consume_recovery_code(user, code):
            step = -1
        if step is not None:
            clear_mfa_failures(request, user)
            backend = request.session.get("mfa_pending_backend", "accounts.auth_backends.ThrottleBackend")
            target = request.session.get("mfa_next", "")
            clear_mfa_pending(request)
            auth_login(request, user, backend=backend)
            request.session["mfa_verified"] = True
            if target.startswith("/") and not target.startswith("//"):
                return redirect(target)
            return redirect("home")
        record_mfa_failure(request, user)
        error = "Enter a current authenticator code or an unused recovery code."
    return render(request, "accounts/mfa_challenge.html", {"error": error})


def _enrollment_user(request):
    if request.user.is_authenticated:
        return request.user, False
    return _pending_user(request), True


@sensitive_post_parameters("password", "code")
@require_http_methods(["GET", "POST"])
def mfa_enroll(request):
    user, pending = _enrollment_user(request)
    if not user or not user.is_active:
        return redirect("login")
    device = MFADevice.objects.filter(user=user).first()
    if device and device.enabled:
        return redirect("mfa_challenge") if pending else redirect("mfa_disable")
    error = None
    password_verified_at = request.session.get("mfa_enroll_password_verified_at")
    verified_recently = bool(
        password_verified_at
        and request.session.get("mfa_enroll_user_id") == user.pk
        and timezone.now().timestamp() - float(password_verified_at) < 300
    )
    if request.method == "POST" and not verified_recently:
        if mfa_attempt_blocked(request, user):
            error = "Too many verification attempts. Try again in 15 minutes."
        elif not user.check_password(request.POST.get("password", "")):
            record_mfa_failure(request, user)
            error = "Enter your current password to continue."
        else:
            clear_mfa_failures(request, user)
            request.session["mfa_enroll_password_verified_at"] = timezone.now().timestamp()
            request.session["mfa_enroll_user_id"] = user.pk
            verified_recently = True
            if not device:
                try:
                    device = MFADevice.objects.create(user=user, encrypted_secret=encrypt_secret(new_totp_secret()))
                except ImproperlyConfigured:
                    verified_recently = False
                    error = "Multi-factor setup is temporarily unavailable. Contact your administrator."
    if not device and verified_recently:
        try:
            device = MFADevice.objects.create(user=user, encrypted_secret=encrypt_secret(new_totp_secret()))
        except ImproperlyConfigured:
            verified_recently = False
            error = "Multi-factor setup is temporarily unavailable. Contact your administrator."
    secret = None
    if device and verified_recently:
        try:
            secret = decrypt_secret(device.encrypted_secret)
        except ImproperlyConfigured:
            verified_recently = False
            error = "Multi-factor setup is temporarily unavailable. Contact your administrator."
    if request.method == "POST" and verified_recently and request.POST.get("code"):
        if mfa_attempt_blocked(request, user):
            error = "Too many verification attempts. Try again in 15 minutes."
        elif not device or device.enabled:
            error = "MFA is already enabled."
        else:
            step = _device_step(device, request.POST.get("code", "").strip())
            if step is None:
                record_mfa_failure(request, user)
                error = "That code is not valid yet. Check your device clock and try again."
            else:
                clear_mfa_failures(request, user)
                codes = make_recovery_codes()
                with transaction.atomic():
                    locked = MFADevice.objects.select_for_update().get(pk=device.pk)
                    locked.enabled = True
                    locked.last_accepted_step = step
                    locked.save(update_fields=["enabled", "last_accepted_step"])
                    hash_recovery_codes(user, codes)
                request.session.pop("mfa_enroll_password_verified_at", None)
                request.session.pop("mfa_enroll_user_id", None)
                if pending:
                    backend = request.session.get("mfa_pending_backend", "accounts.auth_backends.ThrottleBackend")
                    target = request.session.get("mfa_next", "")
                    clear_mfa_pending(request)
                    auth_login(request, user, backend=backend)
                    request.session["mfa_verified"] = True
                else:
                    request.session["mfa_verified"] = True
                    target = ""
                return render(request, "accounts/mfa_recovery_codes.html", {"codes": codes, "next_url": target or reverse("home")})
    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(name=user.email or user.get_username(), issuer_name="School-CMS") if secret else ""
    return render(request, "accounts/mfa_enroll.html", {
        "error": error, "verified_recently": verified_recently, "secret": secret,
        "provisioning_uri": provisioning_uri,
    })


@login_required
@sensitive_post_parameters("password", "code")
@require_http_methods(["GET", "POST"])
def mfa_disable(request):
    error = None
    device = MFADevice.objects.filter(user=request.user, enabled=True).first()
    if request.method == "POST":
        if mfa_attempt_blocked(request, request.user):
            error = "Too many verification attempts. Try again in 15 minutes."
        elif not device or not request.user.check_password(request.POST.get("password", "")):
            record_mfa_failure(request, request.user)
            error = "The password or authenticator code is incorrect."
        else:
            step = _device_step(device, request.POST.get("code", "").strip())
            if step is None:
                record_mfa_failure(request, request.user)
                error = "The password or authenticator code is incorrect."
            else:
                clear_mfa_failures(request, request.user)
                MFADevice.objects.filter(pk=device.pk).delete()
                request.user.mfa_recovery_codes.all().delete()
                if requires_mfa(request.user):
                    auth_logout(request)
                    return redirect("login")
                request.session["mfa_verified"] = False
                messages.success(request, "Multi-factor authentication has been disabled.")
                return redirect("home")
    return render(request, "accounts/mfa_disable.html", {"error": error, "enabled": bool(device)})
