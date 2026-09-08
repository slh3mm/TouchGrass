import hashlib
import math
import secrets
import threading
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings

from adventures.models import Category, Collection, Location, Visit, background_geocode_and_assign
from worldtravel.models import Trip
from worldtravel.models import City, Country, Region

from .models import (
    JourneyCandidate,
    JourneyStop,
    LocationDevice,
    LocationSample,
    PrivacyEvent,
    PrivacyZone,
    StayCandidate,
)


def create_device(*, owner, profile, name, owntracks_username=None, device_identifier=None):
    token = secrets.token_urlsafe(32)
    slug = secrets.token_hex(4)
    requested_username = (owntracks_username or owner.username or "touchgrass")[:80]
    device_identifier = (device_identifier or name.lower().replace(" ", "-") or "iphone")[:100]
    device = LocationDevice(
        owner=owner,
        profile=profile,
        name=name,
        owntracks_username=f"{requested_username}-{slug}",
        device_identifier=device_identifier,
        auth_username=f"{requested_username}-{slug}",
    )
    device.set_token(token)
    device.save()
    return device, token


def _haversine_m(point_a, point_b):
    lon1, lat1 = map(math.radians, (point_a.x, point_a.y))
    lon2, lat2 = map(math.radians, (point_b.x, point_b.y))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(value))


def store_normalized_sample(device, normalized):
    point = Point(normalized.longitude, normalized.latitude, srid=4326)
    zones = PrivacyZone.objects.filter(
        owner=device.owner, enabled=True, center__distance_lte=(point, D(m=25000))
    )
    zone = next((item for item in zones if _haversine_m(item.center, point) <= item.radius_m), None)
    if zone:
        event = normalized.event_type if normalized.event_type in {"enter", "leave"} else "inside"
        PrivacyEvent.objects.get_or_create(
            device=device,
            zone=zone,
            event_type=event,
            captured_at=normalized.captured_at,
        )
        device.last_report_at = timezone.now()
        device.save(update_fields=["last_report_at", "updated_at"])
        if zone.is_home:
            JourneyCandidate.objects.filter(
                owner=device.owner,
                status=JourneyCandidate.STATUS_OPEN,
                ended_at__lte=normalized.captured_at - timedelta(hours=8),
            ).update(status=JourneyCandidate.STATUS_PENDING, updated_at=timezone.now())
        return None, False, True

    previous = device.samples.order_by("-captured_at").first()
    implausible = False
    if previous and normalized.captured_at > previous.captured_at:
        elapsed_hours = (normalized.captured_at - previous.captured_at).total_seconds() / 3600
        if elapsed_hours > 0:
            implausible = (_haversine_m(previous.point, point) / 1000) / elapsed_hours > 1200

    sample, created = LocationSample.objects.get_or_create(
        device=device,
        source_fingerprint=normalized.source_fingerprint,
        defaults={
            "captured_at": normalized.captured_at,
            "point": point,
            "accuracy_m": normalized.accuracy_m,
            "altitude_m": normalized.altitude_m,
            "velocity_mps": normalized.velocity_mps,
            "motion_state": normalized.motion_state,
            "event_type": normalized.event_type,
            "battery_percent": normalized.battery_percent,
            "battery_state": normalized.battery_state,
            "source_adapter": normalized.source,
            "implausible_jump": implausible,
        },
    )
    device.last_report_at = timezone.now()
    device.save(update_fields=["last_report_at", "updated_at"])
    return sample, created, False


def _stay_fingerprint(device_id, start, end, point):
    value = f"{device_id}|{start.isoformat()}|{end.isoformat()}|{point.x:.4f}|{point.y:.4f}"
    return hashlib.sha256(value.encode()).hexdigest()


def _mean_center(samples):
    return Point(
        sum(sample.point.x for sample in samples) / len(samples),
        sum(sample.point.y for sample in samples) / len(samples),
        srid=4326,
    )


def enrich_stay(stay):
    """Enrich one derived stay; raw samples are never sent to a provider."""
    if not getattr(settings, "GOOGLE_MAPS_API_KEY", None):
        return stay
    spatial_key = f"stay-enrichment:{stay.center.y:.3f}:{stay.center.x:.3f}"
    result = cache.get(spatial_key)
    if result is None:
        from adventures.geocoding import reverse_geocode_google
        result = reverse_geocode_google(stay.center.y, stay.center.x, stay.owner)
        cache.set(spatial_key, result, timeout=60 * 60 * 24 * 30)
    if not isinstance(result, dict) or result.get("error"):
        return stay
    stay.country = Country.objects.filter(country_code=result.get("country_id")).first()
    stay.region = Region.objects.filter(pk=result.get("region_id")).first()
    stay.city = City.objects.filter(pk=result.get("city_id")).first()
    stay.suggested_name = (result.get("location_name") or getattr(stay.city, "name", None) or "Possible place")[:200]
    stay.locality = ", ".join(
        item for item in [getattr(stay.city, "name", None), getattr(stay.region, "name", None), getattr(stay.country, "name", None)] if item
    )[:200]
    stay.enrichment_provider = "google"
    stay.evidence = {**stay.evidence, "enriched_at_stay_center": True}
    stay.save(update_fields=["country", "region", "city", "suggested_name", "locality", "enrichment_provider", "evidence", "updated_at"])
    return stay


def annotate_profile_overlap(stay):
    overlaps = StayCandidate.objects.filter(
        owner=stay.owner,
        arrived_at__lte=stay.departed_at,
        departed_at__gte=stay.arrived_at,
    ).exclude(profile=stay.profile)
    match = next((item for item in overlaps if _haversine_m(item.center, stay.center) <= 500), None)
    if not match:
        return
    overlap_start = max(stay.arrived_at, match.arrived_at)
    overlap_end = min(stay.departed_at, match.departed_at)
    overlap_minutes = max(0, int((overlap_end - overlap_start).total_seconds() / 60))
    stay.evidence = {
        **stay.evidence,
        "possible_joint_overlap": {
            "other_profile_id": str(match.profile_id),
            "other_profile_name": match.profile.name,
            "distance_m": round(_haversine_m(match.center, stay.center)),
            "overlap_minutes": overlap_minutes,
            "requires_confirmation": True,
        },
    }
    stay.save(update_fields=["evidence", "updated_at"])


@transaction.atomic
def process_device_samples(device_id, max_samples=500):
    device = LocationDevice.objects.select_related("owner", "profile").get(pk=device_id)
    samples = list(
        LocationSample.objects.filter(device=device, processed_at__isnull=True, implausible_jump=False)
        .filter(Q(accuracy_m__isnull=True) | Q(accuracy_m__lte=500))
        .order_by("captured_at")[:max_samples]
    )
    if not samples:
        JourneyCandidate.objects.filter(
            owner=device.owner, status=JourneyCandidate.STATUS_OPEN, ended_at__lte=timezone.now() - timedelta(hours=24)
        ).update(status=JourneyCandidate.STATUS_PENDING, updated_at=timezone.now())
        return {"samples": 0, "stays": 0, "journeys": 0}

    clusters = []
    current = []
    for sample in samples:
        if not current:
            current = [sample]
            continue
        center = _mean_center(current)
        gap = sample.captured_at - current[-1].captured_at
        radius = max(200, int(sample.accuracy_m or 0), int(current[-1].accuracy_m or 0))
        if gap <= timedelta(minutes=30) and _haversine_m(center, sample.point) <= radius:
            current.append(sample)
        else:
            clusters.append(current)
            current = [sample]
    if current:
        clusters.append(current)

    stays = []
    now = timezone.now()
    for cluster in clusters:
        duration = cluster[-1].captured_at - cluster[0].captured_at
        if len(cluster) >= 2 and duration >= timedelta(minutes=20):
            center = _mean_center(cluster)
            ignored_matches = StayCandidate.objects.filter(
                device=device, status=StayCandidate.STATUS_IGNORED
            ).order_by("-departed_at")[:100]
            if any(_haversine_m(item.center, center) <= 250 for item in ignored_matches):
                LocationSample.objects.filter(pk__in=[sample.pk for sample in cluster]).update(processed_at=now)
                continue
            fingerprint = _stay_fingerprint(device.id, cluster[0].captured_at, cluster[-1].captured_at, center)
            overnight = cluster[-1].captured_at.date() > cluster[0].captured_at.date()
            prior_visits = sum(
                1 for item in StayCandidate.objects.filter(owner=device.owner).exclude(status=StayCandidate.STATUS_IGNORED)[:500]
                if _haversine_m(item.center, center) <= 250
            )
            confidence = min(
                0.97,
                0.42 + min(duration.total_seconds() / 14400, 0.3) + min(len(cluster) / 50, 0.12)
                + (0.08 if overnight else 0) + min(prior_visits * 0.03, 0.09),
            )
            recent_candidates = StayCandidate.objects.filter(
                device=device,
                status=StayCandidate.STATUS_PENDING,
                departed_at__gte=cluster[0].captured_at - timedelta(minutes=30),
                departed_at__lte=cluster[0].captured_at,
            ).order_by("-departed_at")[:20]
            merge_target = next((item for item in recent_candidates if _haversine_m(item.center, center) <= 250), None)
            if merge_target:
                combined_count = merge_target.sample_count + len(cluster)
                merge_target.center = Point(
                    (merge_target.center.x * merge_target.sample_count + center.x * len(cluster)) / combined_count,
                    (merge_target.center.y * merge_target.sample_count + center.y * len(cluster)) / combined_count,
                    srid=4326,
                )
                merge_target.departed_at = cluster[-1].captured_at
                merge_target.sample_count = combined_count
                merge_target.radius_m = max(merge_target.radius_m, int(max((item.accuracy_m or 0) for item in cluster)), 200)
                merge_target.confidence = max(merge_target.confidence, confidence)
                merge_target.evidence = {
                    **merge_target.evidence,
                    "duration_minutes": int((merge_target.departed_at - merge_target.arrived_at).total_seconds() / 60),
                    "sample_count": combined_count,
                    "overnight": merge_target.departed_at.date() > merge_target.arrived_at.date(),
                    "separate_visits_nearby": prior_visits,
                    "merged_adjacent_stay": True,
                }
                merge_target.save(update_fields=["center", "departed_at", "sample_count", "radius_m", "confidence", "evidence", "updated_at"])
                stay = merge_target
            else:
                stay, _ = StayCandidate.objects.get_or_create(
                    device=device,
                    fingerprint=fingerprint,
                    defaults={
                        "owner": device.owner,
                        "profile": device.profile,
                        "center": center,
                        "radius_m": max(200, int(max((item.accuracy_m or 0) for item in cluster))),
                        "arrived_at": cluster[0].captured_at,
                        "departed_at": cluster[-1].captured_at,
                        "sample_count": len(cluster),
                        "confidence": confidence,
                        "suggested_name": "Possible place",
                        "evidence": {
                            "duration_minutes": int(duration.total_seconds() / 60),
                            "sample_count": len(cluster),
                            "overnight": overnight,
                            "separate_visits_nearby": prior_visits,
                            "reason": "The phone remained in this area for at least 20 minutes.",
                        },
                    },
                )
            LocationSample.objects.filter(pk__in=[sample.pk for sample in cluster]).update(
                stay_candidate=stay, processed_at=now
            )
            stays.append(stay)
            enrich_stay(stay)
            annotate_profile_overlap(stay)
        elif cluster[-1].captured_at < now - timedelta(minutes=30):
            LocationSample.objects.filter(pk__in=[sample.pk for sample in cluster]).update(processed_at=now)

    journeys = build_journey_candidates(device.owner, stays)
    device.last_processed_at = now
    device.save(update_fields=["last_processed_at", "updated_at"])
    return {"samples": len(samples), "stays": len(stays), "journeys": journeys}


def build_journey_candidates(owner, stays):
    if not stays:
        return 0
    window_start = min(stay.arrived_at for stay in stays) - timedelta(days=2)
    stays = list(
        StayCandidate.objects.filter(owner=owner, arrived_at__gte=window_start)
        .exclude(status__in=[StayCandidate.STATUS_DISMISSED, StayCandidate.STATUS_IGNORED])
        .select_related("profile", "country", "region")
        .order_by("arrived_at")
    )
    if not stays:
        return 0
    groups, current = [], []
    for stay in stays:
        if not current or stay.arrived_at - current[-1].departed_at <= timedelta(hours=24):
            current.append(stay)
        else:
            groups.append(current)
            current = [stay]
    if current:
        groups.append(current)
    created_count = 0
    for group in groups:
        home = PrivacyZone.objects.filter(owner=owner, is_home=True, enabled=True).first()
        far_from_home = bool(home and any(_haversine_m(home.center, stay.center) >= 80_467 for stay in group))
        overnight = group[-1].departed_at.date() > group[0].arrived_at.date()
        boundary_crossing = len({stay.country_id for stay in group if stay.country_id}) > 1 or len(
            {stay.region_id for stay in group if stay.region_id}
        ) > 1
        if not (far_from_home or overnight or boundary_crossing or len(group) >= 2):
            continue
        material = f"{owner.pk}|{group[0].pk}"
        fingerprint = hashlib.sha256(material.encode()).hexdigest()
        profile_ids = {stay.profile_id for stay in group}
        possible_matches = Trip.objects.filter(
            owner=owner,
            start_date__lte=group[-1].departed_at.date(),
            end_date__gte=group[0].arrived_at.date(),
        ).prefetch_related("profiles")
        matching_trip = next(
            (trip for trip in possible_matches if profile_ids.intersection(trip.profiles.values_list("id", flat=True))),
            None,
        )
        journey_status = JourneyCandidate.STATUS_OPEN if group[-1].departed_at > timezone.now() - timedelta(hours=24) else JourneyCandidate.STATUS_PENDING
        journey, created = JourneyCandidate.objects.get_or_create(
            owner=owner,
            fingerprint=fingerprint,
            defaults={
                "started_at": group[0].arrived_at,
                "ended_at": group[-1].departed_at,
                "status": journey_status,
                "confidence": min(0.95, 0.55 + len(group) * 0.08),
                "evidence": {
                    "stop_count": len(group),
                    "reason": "Meaningful stays were detected during an away journey.",
                    "far_from_home": far_from_home,
                    "overnight": overnight,
                    "boundary_crossing": boundary_crossing,
                    "matching_trip_id": str(matching_trip.pk) if matching_trip else None,
                },
                "matched_trip": matching_trip,
            },
        )
        if created:
            journey.profiles.set({stay.profile for stay in group})
            JourneyStop.objects.bulk_create(
                [JourneyStop(journey=journey, stay=stay, order=index) for index, stay in enumerate(group)]
            )
            created_count += 1
        else:
            journey.ended_at = group[-1].departed_at
            journey.status = journey_status if journey.status == JourneyCandidate.STATUS_OPEN else journey.status
            journey.matched_trip = matching_trip or journey.matched_trip
            journey.save(update_fields=["ended_at", "status", "matched_trip", "updated_at"])
            existing_stays = set(journey.stops.values_list("stay_id", flat=True))
            next_order = journey.stops.count()
            for stay in group:
                if stay.pk not in existing_stays:
                    JourneyStop.objects.create(journey=journey, stay=stay, order=next_order)
                    next_order += 1
    return created_count


def schedule_processing(device_id):
    thread = threading.Thread(target=_safe_process, args=(device_id,), daemon=True)
    thread.start()


def _safe_process(device_id):
    try:
        process_device_samples(device_id)
        cleanup_key = f"location-retention-{timezone.localdate().isoformat()}"
        if cache.add(cleanup_key, True, timeout=60 * 60 * 26):
            cleanup_expired_samples()
    except Exception:
        # Ingestion must remain successful even when deferred processing needs a retry.
        import logging

        logging.getLogger(__name__).exception("Location processing failed for device %s", device_id)


@transaction.atomic
def accept_stay(stay, *, name=None, start_date=None, end_date=None, profile_ids=None, trip=None):
    if stay.accepted_location_id:
        return stay.accepted_location
    defaults = [
        ("general", "General", "⌖"), ("lodging", "Lodging", "⌂"), ("attractions", "Attractions", "★"),
        ("food", "Food & drink", "◉"), ("nature", "Parks & nature", "♧"), ("transit", "Transit", "↝"),
        ("sports", "Sports & venues", "⚾"), ("personal", "Personal place", "⌂"),
    ]
    for slug, display_name, icon in defaults:
        Category.objects.get_or_create(user=stay.owner, name=slug, defaults={"display_name": display_name, "icon": icon})
    location = Location.objects.create(
        user=stay.owner,
        name=(name or stay.suggested_name or "Saved place")[:200],
        latitude=stay.center.y,
        longitude=stay.center.x,
    )
    profiles = stay.owner.travel_profiles.filter(id__in=(profile_ids or [stay.profile_id]))
    location.profiles.set(profiles)
    visit = Visit.objects.create(
        location=location,
        start_date=start_date or stay.arrived_at,
        end_date=end_date or stay.departed_at,
        source="location_tracking",
        trip=trip,
    )
    visit.profiles.set(profiles)
    threading.Thread(target=background_geocode_and_assign, args=(str(location.pk),), daemon=True).start()
    stay.accepted_location = location
    stay.status = StayCandidate.STATUS_ACCEPTED
    stay.save(update_fields=["accepted_location", "status", "updated_at"])
    return location


@transaction.atomic
def accept_journey(journey, *, title=None, profile_ids=None, existing_trip=None):
    if journey.accepted_trip_id:
        return journey.accepted_trip
    profiles = journey.owner.travel_profiles.filter(id__in=(profile_ids or journey.profiles.values_list("id", flat=True)))
    existing_trip = existing_trip or journey.matched_trip
    if existing_trip:
        trip = existing_trip
    else:
        title = (title or journey.title or "Detected trip")[:160]
        collection = Collection.objects.create(
            user=journey.owner,
            name=title,
            start_date=journey.started_at.date(),
            end_date=journey.ended_at.date(),
        )
        trip = Trip.objects.create(
            owner=journey.owner,
            collection=collection,
            title=title,
            start_date=journey.started_at.date(),
            end_date=journey.ended_at.date(),
            notes="Created from reviewed OwnTracks location history.",
        )
        trip.profiles.set(profiles)
    for stop in journey.stops.select_related("stay").all():
        accept_stay(stop.stay, profile_ids=[stop.stay.profile_id], trip=trip)
    journey.accepted_trip = trip
    journey.status = JourneyCandidate.STATUS_ACCEPTED
    journey.save(update_fields=["accepted_trip", "status", "updated_at"])
    return trip


def cleanup_expired_samples():
    now = timezone.now()
    unresolved_stay_ids = StayCandidate.objects.filter(status=StayCandidate.STATUS_PENDING).values_list("id", flat=True)
    protected = LocationSample.objects.filter(stay_candidate_id__in=unresolved_stay_ids, captured_at__gte=now - timedelta(days=90))
    ordinary = LocationSample.objects.filter(captured_at__lt=now - timedelta(days=30)).exclude(pk__in=protected.values("pk"))
    deleted, _ = ordinary.delete()
    return deleted
