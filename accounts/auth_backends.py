from django.contrib.auth.backends import ModelBackend

from .auth_security import auth_throttle_keys, clear_auth_failures, is_throttled, record_auth_failure


class ThrottleBackend(ModelBackend):
    """ModelBackend authentication with a shared database failure window."""
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email") or ""
        keys = auth_throttle_keys("login", identifier, request) if request is not None else ()
        if any(is_throttled(key) for key in keys):
            return None
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if keys:
            if user is None:
                record_auth_failure("login", identifier, request)
            else:
                clear_auth_failures("login", identifier, request)
        return user
