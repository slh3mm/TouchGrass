import base64
import binascii

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone

from .models import LocationDevice


class OwnTracksDeviceAuthentication(BaseAuthentication):
    keyword = "Basic"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} "):
            raise AuthenticationFailed("OwnTracks device credentials are required.")
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
            username, token = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationFailed("Invalid OwnTracks authorization header.") from exc
        try:
            device = LocationDevice.objects.select_related("owner", "profile").get(auth_username=username)
        except LocationDevice.DoesNotExist as exc:
            raise AuthenticationFailed("Unknown OwnTracks device.") from exc
        if device.is_revoked or not device.enabled or not device.check_token(token):
            device.last_auth_failure_at = timezone.now()
            device.save(update_fields=["last_auth_failure_at", "updated_at"])
            from .models import LocationTrackingAuditEvent
            LocationTrackingAuditEvent.objects.create(owner=device.owner, device=device, action="authentication_failed")
            raise AuthenticationFailed("OwnTracks device is paused, revoked, or invalid.")
        return device.owner, device

    def authenticate_header(self, request):
        return 'Basic realm="TouchGrass OwnTracks"'
