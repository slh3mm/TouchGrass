from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
import os


class UATExternalIntegrationGuardMiddleware:
    """Prevent a disposable UAT stack from contacting live integrations.

    The guard is intentionally path-and-method based.  Read-only status pages,
    seeded suggestions, local accept/dismiss actions, and disconnect actions
    remain testable, while operations that would initiate OAuth, synchronize a
    remote account, or query a remote media/activity server are stopped before
    their view code can perform network I/O.
    """

    _SKYLIGHT_BLOCKED = {
        "/api/skylight/connect/",
        "/api/skylight/login/",
        "/api/skylight/complete/",
        "/api/skylight/sync/",
        "/api/skylight/events/refresh/",
    }
    _REMOTE_PREFIXES = (
        "/api/integrations/strava/authorize/",
        "/api/integrations/strava/callback/",
        "/api/integrations/strava/activities/",
        "/api/integrations/immich/search/",
        "/api/integrations/immich/albums/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_blocked(request):
            return JsonResponse(
                {
                    "error": "Live integrations are disabled in the UAT environment.",
                    "code": "uat.external_integrations_disabled",
                },
                status=409,
            )
        return self.get_response(request)

    @classmethod
    def _is_blocked(cls, request):
        if not getattr(settings, "UAT_MODE", False):
            return False
        if getattr(settings, "UAT_ALLOW_EXTERNAL_INTEGRATIONS", False):
            return False

        path = request.path
        if path in cls._SKYLIGHT_BLOCKED:
            return True
        if any(path.startswith(prefix) for prefix in cls._REMOTE_PREFIXES):
            return True

        # Creating or updating these integrations validates credentials against
        # the supplied remote server.  Listing and deleting local mock records
        # are safe and remain available to the UAT reviewer.
        if request.method in {"POST", "PUT", "PATCH"}:
            if path.startswith("/api/integrations/immich/"):
                return True
            if path.startswith("/api/integrations/wanderer/"):
                return True
        return False

class OverrideHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        public_url = os.getenv('PUBLIC_URL', None)
        if public_url:
            # Extract host and scheme
            scheme, host = public_url.split("://")
            request.META['HTTP_HOST'] = host
            request.META['wsgi.url_scheme'] = scheme

            # Set X-Forwarded-Proto for Django
            request.META['HTTP_X_FORWARDED_PROTO'] = scheme

        response = self.get_response(request)
        return response

class XSessionTokenMiddleware(MiddlewareMixin):
    def process_request(self, request):
        session_token = request.headers.get('X-Session-Token')
        if session_token:
            request.COOKIES[settings.SESSION_COOKIE_NAME] = session_token

class DisableCSRFForSessionTokenMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if 'X-Session-Token' in request.headers:
            setattr(request, '_dont_enforce_csrf_checks', True)

class DisableCSRFForMobileLoginSignup(MiddlewareMixin):
    def process_request(self, request):
        is_mobile = request.headers.get('X-Is-Mobile', '').lower() == 'true'
        is_login_or_signup = request.path in ['/auth/browser/v1/auth/login', '/auth/browser/v1/auth/signup']
        if is_mobile and is_login_or_signup:
            setattr(request, '_dont_enforce_csrf_checks', True)

class DisableCSRFForAPIKeyMiddleware(MiddlewareMixin):
    """Exempt requests carrying an AdventureLog API key from CSRF enforcement.

    DRF's own SessionAuthentication is the only built-in class that enforces
    CSRF, so this middleware is mainly a safety net for non-DRF views and to
    ensure the Django CSRF middleware itself doesn't reject API-key requests
    before they reach DRF.
    """

    def process_request(self, request):
        # Never skip CSRF for requests that also include a Django session.
        if settings.SESSION_COOKIE_NAME in request.COOKIES:
            return

        if request.headers.get('X-API-Key'):
            setattr(request, '_dont_enforce_csrf_checks', True)
            return

        auth_header = request.headers.get('Authorization', '')
        if auth_header.lower().startswith('api-key '):
            setattr(request, '_dont_enforce_csrf_checks', True)
