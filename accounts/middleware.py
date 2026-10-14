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
