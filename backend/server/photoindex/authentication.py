import base64
import binascii

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import PhotoImportSource


class PhotoSourceAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            raise AuthenticationFailed("Photo poller credentials are required.")
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
            username, token = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationFailed("Invalid photo poller authorization header.") from exc
        try:
            source = PhotoImportSource.objects.select_related("owner", "profile").get(auth_username=username)
        except PhotoImportSource.DoesNotExist as exc:
            raise AuthenticationFailed("Unknown photo source.") from exc
        if source.is_revoked or not source.enabled or not source.check_token(token):
            source.last_auth_failure_at = timezone.now()
            source.save(update_fields=["last_auth_failure_at", "updated_at"])
            raise AuthenticationFailed("Photo source is paused, revoked, or invalid.")
        return source.owner, source

    def authenticate_header(self, request):
        return 'Basic realm="TouchGrass iCloud Photos"'
