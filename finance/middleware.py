from django.conf import settings
from django.contrib.auth.views import redirect_to_login


class RequireLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "REQUIRE_LOGIN", True):
            return self.get_response(request)
        if request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        exempt_prefixes = (
            settings.LOGIN_URL,
            "/accounts/logout/",
            "/admin/",
            settings.STATIC_URL,
        )
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            return self.get_response(request)

        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

