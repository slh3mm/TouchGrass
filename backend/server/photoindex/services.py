import hashlib
import math
import mimetypes
import secrets
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.cache import cache
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from adventures.models import Visit
from locationtracking.models import PrivacyZone
from worldtravel.models import Trip
from worldtravel.models import City, Country, Region

from .models import (
    PhotoAsset,
    PhotoImportSource,
    PhotoMatchSuggestion,
    PhotoMatchSuppression,
    TripPhotoLink,
)


ALLOWED_EXTENSIONS = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".mov", ".mp4"}
VIDEO_EXTENSIONS = {".mov", ".mp4"}


def create_source(*, owner, profile, name="iCloud Photos", root_alias="icloud-photos"):
    token = secrets.token_urlsafe(32)
    auth_username = f"icloud-{owner.username[:50]}-{secrets.token_hex(4)}"
    source = PhotoImportSource(owner=owner, profile=profile, name=name, root_alias=root_alias, auth_username=auth_username)
    source.set_token(token)
    source.save()
    return source, token


def normalize_relative_path(value):
    raw = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or ":" in raw or raw.startswith(("/", "\\")):
        raise ValueError("relative_path must remain inside the configured iCloud root")
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported photo or video extension")
    return path.as_posix(), suffix


def metadata_fingerprint(asset):
    value = f"{asset.source_key}|{asset.captured_at}|{asset.point}|{asset.size_bytes}|{asset.file_modified_at}"
    return hashlib.sha256(value.encode()).hexdigest()


def _haversine_m(point_a, point_b):
    lon1, lat1 = map(math.radians, (point_a.x, point_a.y))
    lon2, lat2 = map(math.radians, (point_b.x, point_b.y))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(value))


def redact_privacy_zone(owner, point):
    if point is None:
        return None
    nearby = PrivacyZone.objects.filter(owner=owner, enabled=True, center__distance_lte=(point, D(m=25000)))
    return next((zone for zone in nearby if _haversine_m(zone.center, point) <= zone.radius_m), None)


def upsert_asset(source, data):
    relative_path, extension = normalize_relative_path(data["relative_path"])
    point = None
    latitude, longitude = data.get("latitude"), data.get("longitude")
    if latitude is not None and longitude is not None:
        latitude, longitude = float(latitude), float(longitude)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Invalid GPS coordinates")
        point = Point(longitude, latitude, srid=4326)
    zone = redact_privacy_zone(source.owner, point)
    if zone:
        point = None
    media_kind = PhotoAsset.KIND_VIDEO if extension in VIDEO_EXTENSIONS else PhotoAsset.KIND_IMAGE
    defaults = {
        "profile": source.profile,
        "relative_path": relative_path,
        "filename": Path(relative_path).name[:255],
        "extension": extension,
        "media_kind": media_kind,
        "mime_type": str(data.get("mime_type") or mimetypes.guess_type(relative_path)[0] or "application/octet-stream")[:100],
        "size_bytes": max(0, int(data.get("size_bytes") or 0)),
        "file_modified_at": data.get("file_modified_at"),
        "captured_at": data.get("captured_at"),
        "captured_local": str(data.get("captured_local") or "")[:40],
        "timezone_offset": str(data.get("timezone_offset") or "")[:10],
        "point": point,
        "privacy_zone": zone,
        "width": data.get("width"),
        "height": data.get("height"),
        "orientation": str(data.get("orientation") or "")[:60],
        "duration_seconds": data.get("duration_seconds"),
        "camera_make": str(data.get("camera_make") or "")[:100],
        "camera_model": str(data.get("camera_model") or "")[:100],
        "live_photo_identifier": str(data.get("live_photo_identifier") or "")[:200],
        "content_hash": str(data.get("content_hash") or "")[:64],
        "metadata": data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        "available": True,
        "processing_state": PhotoAsset.STATE_READY,
        "error_message": "",
    }
    with transaction.atomic():
        asset, created = PhotoAsset.objects.update_or_create(
            source=source, source_key=data["source_key"], defaults=defaults
        )
        if asset.live_photo_identifier:
            pair = (
                PhotoAsset.objects.filter(
                    source=source, live_photo_identifier=asset.live_photo_identifier
                )
                .exclude(pk=asset.pk)
                .exclude(media_kind=asset.media_kind)
                .first()
            )
            if pair:
                if asset.live_photo_pair_id != pair.id:
                    asset.live_photo_pair = pair
                    asset.save(update_fields=["live_photo_pair", "updated_at"])
                if pair.live_photo_pair_id != asset.id:
                    pair.live_photo_pair = asset
                    pair.save(update_fields=["live_photo_pair", "updated_at"])
    match_asset(asset)
    return asset, created


def accessible_trips_for_source(source, captured_date):
    return Trip.objects.filter(
        owner=source.owner,
        start_date__lte=captured_date,
        end_date__gte=captured_date,
    ).filter(Q(profiles=source.profile) | Q(profiles__name__iexact="Joint")).distinct()


def _trip_matches_location(asset, trip):
    if asset.point is None:
        return False, "Photo has no usable GPS"
    if asset.region_id and trip.destinations.filter(region_id=asset.region_id).exists():
        return True, "GPS region matches the trip destination"
    if asset.country_id and trip.destinations.filter(country_id=asset.country_id, region__isnull=True).exists():
        return True, "GPS country matches the trip destination"
    visits = Visit.objects.filter(trip=trip, location__point__isnull=False).select_related("location")
    for visit in visits:
        if _haversine_m(asset.point, visit.location.point) <= 50000:
            return True, f"GPS is near {visit.location.name}"
    return False, "GPS does not match an accepted trip destination or visit"


def _enrich_asset_location(asset):
    """Reverse geocode only a persisted photo center that overlaps a trip date.

    Raw files and raw tracking coordinates are never sent. Results are spatially
    cached so a burst of photos at one destination does not create one provider
    request per asset.
    """
    if asset.point is None or not getattr(settings, "GOOGLE_MAPS_API_KEY", None):
        return asset
    spatial_key = f"photo-enrichment:{asset.point.y:.3f}:{asset.point.x:.3f}"
    result = cache.get(spatial_key)
    if result is None:
        from adventures.geocoding import reverse_geocode_google

        result = reverse_geocode_google(asset.point.y, asset.point.x, asset.source.owner)
        cache.set(spatial_key, result, timeout=60 * 60 * 24 * 30)
    if not isinstance(result, dict) or result.get("error"):
        return asset
    asset.country = Country.objects.filter(country_code=result.get("country_id")).first()
    asset.region = Region.objects.filter(pk=result.get("region_id")).first()
    asset.city = City.objects.filter(pk=result.get("city_id")).first()
    asset.locality = ", ".join(
        value
        for value in [
            getattr(asset.city, "name", None),
            getattr(asset.region, "name", None),
            getattr(asset.country, "name", None),
        ]
        if value
    )[:200]
    asset.save(update_fields=["country", "region", "city", "locality", "updated_at"])
    return asset


def match_asset(asset):
    if not asset.captured_at or asset.privacy_zone_id:
        return None
    candidates = list(accessible_trips_for_source(asset.source, asset.captured_at.date()).prefetch_related("destinations", "profiles"))
    if candidates and asset.point is not None and not (asset.country_id or asset.region_id):
        _enrich_asset_location(asset)
    matches = []
    for trip in candidates:
        matched, reason = _trip_matches_location(asset, trip)
        if matched and not PhotoMatchSuppression.objects.filter(
            asset=asset, trip=trip, metadata_fingerprint=metadata_fingerprint(asset)
        ).exists():
            matches.append((trip, reason))
    if len(matches) == 1:
        trip, reason = matches[0]
        link, _ = TripPhotoLink.objects.get_or_create(
            asset=asset,
            trip=trip,
            defaults={
                "confidence": 0.98,
                "explanation": reason,
                "origin": TripPhotoLink.ORIGIN_AUTOMATIC,
                "profile_evidence": {"profile_id": str(asset.profile_id), "profile_name": asset.profile.name},
            },
        )
        PhotoMatchSuggestion.objects.filter(asset=asset).delete()
        return link
    if candidates:
        reason = "Multiple trips match this date and location" if len(matches) > 1 else "Date matches a trip, but location needs review"
        suggestion, _ = PhotoMatchSuggestion.objects.update_or_create(
            asset=asset, defaults={"reason": reason, "confidence": 0.6 if matches else 0.35, "status": "pending"}
        )
        suggestion.candidate_trips.set([item[0] for item in matches] or candidates)
    return None


def resolve_asset_path(asset):
    mount = Path(settings.ICLOUD_PHOTOS_MOUNT).resolve()
    candidate = (mount / PurePosixPath(asset.relative_path)).resolve()
    try:
        candidate.relative_to(mount)
    except ValueError as exc:
        raise ValueError("Indexed path escaped the configured photo root") from exc
    if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported media extension")
    return candidate
