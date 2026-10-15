from django.contrib.auth import logout
from django.shortcuts import redirect

from .auth_security import requires_mfa, start_mfa_pending
from .models import MFADevice


class MFARequiredMiddleware:
    """Keep privileged sessions out of every portal/admin view until MFA succeeds."""
    allowed_paths = {"/accounts/mfa/challenge/", "/accounts/mfa/enroll/"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and requires_mfa(user) and not request.session.get("mfa_verified"):
            if request.path_info in self.allowed_paths:
                return self.get_response(request)
            return self._send_to_mfa(request, user)
        response = self.get_response(request)
        # Django admin's stock login calls auth.login() in the view. Catch it in this
        # response phase so the response never leaves with an authenticated session.
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and requires_mfa(user) and not request.session.get("mfa_verified"):
            return self._send_to_mfa(request, user)
        return response

    @staticmethod
    def _send_to_mfa(request, user):
        user_id = user.pk
        backend = getattr(user, "backend", "accounts.auth_backends.ThrottleBackend")
        if request.path_info == "/admin/login/":
            next_url = "/admin/"
        else:
            next_url = request.get_full_path()
        logout(request)
        start_mfa_pending(request, user, backend, next_url)
        name = "mfa_challenge" if MFADevice.objects.filter(user_id=user_id, enabled=True).exists() else "mfa_enroll"
        return redirect(name)


from django.contrib.auth import logout
from django.contrib.auth import get_user_model


class ActiveUserMiddleware:
    """Invalidate sessions immediately when an account is deactivated."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_user_id = request.session.get("_auth_user_id")
        if session_user_id is not None and not get_user_model()._default_manager.filter(
            pk=session_user_id, is_active=True
        ).exists():
            logout(request)
        return self.get_response(request)
