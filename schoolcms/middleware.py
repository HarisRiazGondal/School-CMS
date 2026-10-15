class PrivateResponseMiddleware:
    """Keep account/student data out of shared caches and browser referrers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated or request.path.startswith(("/accounts/", "/admin/", "/private-files/", "/health/")):
            response["Cache-Control"] = "no-store, private"
            response["Referrer-Policy"] = "no-referrer"
        response.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
