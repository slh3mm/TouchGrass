import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from typing import Optional

from django.utils import timezone


class InvalidLocationPayload(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedLocationSample:
    source: str
    external_device_id: str
    captured_at: datetime
    latitude: float
    longitude: float
    accuracy_m: Optional[float]
    altitude_m: Optional[float]
    velocity_mps: Optional[float]
    motion_state: str
    event_type: str
    battery_percent: Optional[int]
    battery_state: str
    source_fingerprint: str


def _optional_float(payload, key):
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidLocationPayload(f"{key} must be numeric") from exc


def parse_owntracks(payload, device):
    message_type = payload.get("_type", "location")
    if message_type not in {"location", "transition"}:
        return None

    topic = str(payload.get("topic") or "").strip("/")
    if topic:
        parts = topic.split("/")
        if len(parts) >= 3 and (parts[-2] != device.owntracks_username or parts[-1] != device.device_identifier):
            raise InvalidLocationPayload("OwnTracks username/device does not match the paired phone")

    try:
        latitude = float(payload["lat"])
        longitude = float(payload["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidLocationPayload("lat and lon are required") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise InvalidLocationPayload("coordinates are outside valid ranges")

    timestamp = payload.get("tst")
    try:
        captured_at = datetime.fromtimestamp(float(timestamp), tz=datetime_timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise InvalidLocationPayload("tst must be a Unix timestamp") from exc
    if captured_at > timezone.now() + timezone.timedelta(minutes=10):
        raise InvalidLocationPayload("location timestamp is too far in the future")

    event_type = payload.get("event") or payload.get("t") or message_type
    battery = payload.get("batt")
    try:
        battery = max(0, min(100, int(battery))) if battery is not None else None
    except (TypeError, ValueError):
        battery = None
    fingerprint_material = "|".join(
        [device.device_identifier, str(int(captured_at.timestamp())), f"{latitude:.6f}", f"{longitude:.6f}", str(event_type)]
    )
    fingerprint = hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest()
    return NormalizedLocationSample(
        source="owntracks",
        external_device_id=device.device_identifier,
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=_optional_float(payload, "acc"),
        altitude_m=_optional_float(payload, "alt"),
        velocity_mps=_optional_float(payload, "vel"),
        motion_state=str(payload.get("motion") or ""),
        event_type=str(event_type)[:32],
        battery_percent=battery,
        battery_state=str(payload.get("bs") or "")[:20],
        source_fingerprint=fingerprint,
    )
