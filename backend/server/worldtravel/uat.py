"""Deterministic, private fixtures for the isolated TouchGrass UAT stack.

This module is deliberately not imported by normal application code.  The
``prepare_uat`` management command is the sole entry point and refuses to run
unless ``UAT_MODE=true`` is present in the process environment.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models.signals import pre_delete
from django.utils import timezone

from adventures.models import Category, Collection, ContentAttachment, ContentImage, Location, Visit
from integrations.models import ImmichIntegration, StravaToken, WandererIntegration
from locationtracking.models import (
    JourneyCandidate,
    LocationDevice,
    LocationTrackingAuditEvent,
    PrivacyEvent,
    PrivacyZone,
    StayCandidate,
)
from photoindex.models import PhotoAsset, PhotoImportSource, PhotoMatchSuggestion, TripPhotoLink
from users.models import APIKey
from worldtravel.models import (
    BallparkVisit,
    Country,
    ProfileCountryVisit,
    ProfileRegionVisit,
    ProfileTravelVisit,
    Region,
    SkylightConnection,
    SkylightEventReview,
    SkylightTripSuggestion,
    TravelProfile,
    Trip,
    TripDestination,
)


ANCHOR_DATE = date(2026, 8, 15)
UAT_PREFIX = "[UAT]"
ACCOUNT_NAMES = ("uat-owner", "uat-member", "uat-outsider", "uat-empty")


class UATConfigurationError(RuntimeError):
    pass


def require_uat_mode() -> None:
    if os.getenv("UAT_MODE", "").strip().lower() != "true":
        raise UATConfigurationError(
            "prepare_uat is destructive and can run only when UAT_MODE=true"
        )


def _model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _aware(day: date, hour: int = 12) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour=hour)))


@dataclass
class UATAccounts:
    owner: object
    member: object
    outsider: object
    empty: object
    generated_passwords: dict[str, str]


def _passwords(common_password: str | None) -> tuple[dict[str, str], dict[str, str]]:
    values = {}
    generated = {}
    for role in ("owner", "member", "outsider", "empty"):
        env_name = f"UAT_{role.upper()}_PASSWORD"
        password = os.getenv(env_name) or common_password
        if not password:
            password = secrets.token_urlsafe(18)
            generated[role] = password
        values[role] = password
    return values, generated


def _select_cloned_owner(owner_username: str | None):
    User = get_user_model()
    if not owner_username:
        # Re-running against an already prepared database must retain the same
        # owner instead of anonymizing it and creating another household.
        return User.objects.filter(username="uat-owner").first()
    requested = User.objects.filter(username=owner_username).first()
    existing_uat_owner = User.objects.filter(username="uat-owner").first()
    if requested and existing_uat_owner and requested.pk != existing_uat_owner.pk:
        raise UATConfigurationError(
            "Both the requested cloned owner and uat-owner exist; reset the UAT database before retrying."
        )
    if requested:
        return requested
    if existing_uat_owner:
        return existing_uat_owner
    raise UATConfigurationError(f"Cloned owner {owner_username!r} does not exist")


def scrub_database(owner_username: str | None, common_password: str | None) -> UATAccounts:
    """Remove operational credentials and anonymize every cloned login."""

    User = get_user_model()
    cloned_owner = _select_cloned_owner(owner_username)

    # Authentication/session material is never useful in UAT.
    Session.objects.all().delete()
    APIKey.objects.all().delete()
    token_model = _model("authtoken", "Token")
    if token_model:
        token_model.objects.all().delete()
    email_address_model = _model("account", "EmailAddress")
    if email_address_model:
        from users.signals import prevent_deleting_last_email

        pre_delete.disconnect(prevent_deleting_last_email, sender=email_address_model)
        try:
            email_address_model.objects.all().delete()
        finally:
            pre_delete.connect(prevent_deleting_last_email, sender=email_address_model)

    for app_label, model_name in (
        ("socialaccount", "SocialToken"),
        ("socialaccount", "SocialAccount"),
        ("socialaccount", "SocialApp"),
        ("invitations", "Invitation"),
    ):
        model = _model(app_label, model_name)
        if model:
            model.objects.all().delete()

    # Integration credentials and remote identifiers are deleted, not masked;
    # the seeded records below are explicitly inert mock states.
    ImmichIntegration.objects.all().delete()
    StravaToken.objects.all().delete()
    WandererIntegration.objects.all().delete()
    SkylightConnection.objects.all().delete()

    # Exact telemetry, privacy coordinates, device credentials and host paths
    # are discarded.  Cascades remove samples, scan history and photo metadata.
    LocationTrackingAuditEvent.objects.all().delete()
    JourneyCandidate.objects.all().delete()
    StayCandidate.objects.all().delete()
    PrivacyEvent.objects.all().delete()
    PrivacyZone.objects.all().delete()
    LocationDevice.objects.all().delete()
    PhotoImportSource.objects.all().delete()

    # UAT media is synthetic metadata.  Never carry copied file names, Immich
    # identifiers, attachments, or image paths across from development.
    ContentImage.objects.all().delete()
    ContentAttachment.objects.all().delete()

    # First move every username/email into a collision-free namespace, then
    # assign stable anonymized identities.  Foreign keys remain untouched.
    users = list(User.objects.order_by("date_joined", "pk"))
    safe_users = {
        user.pk
        for user in users
        if user.username in ACCOUNT_NAMES or user.username.startswith("uat-clone-")
    }
    unsafe_users = [user for user in users if user.pk not in safe_users]
    for user in users:
        user.first_name = ""
        user.last_name = ""
        user.profile_pic = None
        user.set_unusable_password()
        user.save(update_fields=["first_name", "last_name", "profile_pic", "password"])
    for user in unsafe_users:
        token = uuid.uuid4().hex
        user.username = f"uat-tmp-{token}"
        user.email = f"uat-tmp-{token}@example.invalid"
        user.save(update_fields=["username", "email"])

    clone_index = 1
    used_names = set(User.objects.values_list("username", flat=True))
    for user in unsafe_users:
        if cloned_owner and user.pk == cloned_owner.pk:
            username = "uat-owner"
        else:
            while f"uat-clone-{clone_index:04d}" in used_names:
                clone_index += 1
            username = f"uat-clone-{clone_index:04d}"
            clone_index += 1
        used_names.add(username)
        user.username = username
        user.email = f"{username}@example.invalid"
        user.save(update_fields=["username", "email"])

    password_values, generated = _passwords(common_password)
    accounts = {}
    for role in ("owner", "member", "outsider", "empty"):
        username = f"uat-{role}"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.invalid"},
        )
        user.email = f"{username}@example.invalid"
        user.first_name = role.title()
        user.last_name = "UAT"
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.disable_password = False
        user.profile_pic = None
        user.set_password(password_values[role])
        user.save()
        accounts[role] = user

    return UATAccounts(generated_passwords=generated, **accounts)


def reset_generated_records(owner) -> None:
    """Remove only tagged/synthetic UAT scenarios, preserving cloned travel."""

    Trip.objects.filter(owner=owner, title__startswith=UAT_PREFIX).delete()
    Collection.objects.filter(user=owner, name__startswith=UAT_PREFIX).delete()
    Location.objects.filter(user=owner, name__startswith=UAT_PREFIX).delete()
    SkylightConnection.objects.filter(owner=owner).delete()
    PhotoImportSource.objects.filter(owner=owner, root_alias="uat-photos").delete()
    LocationDevice.objects.filter(owner=owner, auth_username__startswith="uat-").delete()


def _countries_and_regions():
    us, _ = Country.objects.update_or_create(
        country_code="US", defaults={"name": "United States", "subregion": "Northern America"}
    )
    ca, _ = Country.objects.update_or_create(
        country_code="CA", defaults={"name": "Canada", "subregion": "Northern America"}
    )
    gb, _ = Country.objects.update_or_create(
        country_code="GB", defaults={"name": "United Kingdom", "subregion": "Northern Europe"}
    )
    fr, _ = Country.objects.update_or_create(
        country_code="FR", defaults={"name": "France", "subregion": "Western Europe"}
    )
    regions = {}
    for code, name, country in (
        ("US-CA", "California", us),
        ("US-MA", "Massachusetts", us),
        ("US-PA", "Pennsylvania", us),
        ("CA-ON", "Ontario", ca),
        ("CA-QC", "Quebec", ca),
    ):
        regions[code], _ = Region.objects.update_or_create(
            id=code, defaults={"name": name, "country": country}
        )
    return {"US": us, "CA": ca, "GB": gb, "FR": fr}, regions


def _profiles(accounts: UATAccounts):
    specs = (
        ("Spencer", "#F9C846", "S", accounts.owner, True),
        ("Ashley", "#F381AC", "A", accounts.member, False),
        ("Joint", "#38D39F", "J", None, False),
    )
    profiles = {}
    for name, color, avatar, linked_user, is_default in specs:
        profile, _ = TravelProfile.objects.update_or_create(
            owner=accounts.owner,
            name=name,
            defaults={
                "color": color,
                "avatar": avatar,
                "linked_user": linked_user,
                "is_default": is_default,
            },
        )
        profile.shared_with.add(accounts.member)
        profiles[name] = profile
    return profiles


def _trip(owner, profiles, title, start_date, end_date, profile_names, notes="", link=None):
    collection, _ = Collection.objects.update_or_create(
        user=owner,
        name=title,
        defaults={
            "description": notes,
            "start_date": start_date,
            "end_date": end_date,
            "link": link,
            "is_public": False,
        },
    )
    collection.shared_with.set([profiles["Ashley"].linked_user])
    trip, _ = Trip.objects.update_or_create(
        collection=collection,
        defaults={
            "owner": owner,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "notes": notes,
        },
    )
    trip.profiles.set([profiles[name] for name in profile_names])
    return trip


def _destination(trip, country, region=None):
    lookup = {"trip": trip, "country": country, "region": region}
    if region:
        TripDestination.objects.get_or_create(trip=trip, region=region, defaults=lookup)
    else:
        TripDestination.objects.get_or_create(trip=trip, region__isnull=True, country=country, defaults=lookup)


def seed_core(accounts: UATAccounts, anchor: date) -> dict:
    profiles = _profiles(accounts)
    countries, regions = _countries_and_regions()
    trips = []
    trip_specs = (
        ("[UAT] Past California", -120, -116, ("Spencer",), "Short manual note", None, "US-CA"),
        ("[UAT] Joint Boston Weekend", -60, -58, ("Joint",), "", None, "US-MA"),
        ("[UAT] Current Ontario", -1, 2, ("Spencer", "Ashley", "Joint"), "", None, "CA-ON"),
        ("[UAT] Future United Kingdom", 40, 48, ("Ashley",), "", None, "GB"),
        ("[UAT] Multi-destination", 75, 86, ("Spencer", "Ashley"), "A deliberately long note for card alignment and wrapping checks. " * 3, None, "US-PA"),
        ("[UAT] No destination", 100, 101, ("Spencer",), "", None, None),
        ("[UAT] Valid Google Doc", 130, 134, ("Joint",), "", "https://docs.google.com/document/d/uat-valid-document-id/edit", "FR"),
        ("[UAT] Inaccessible Google Doc", 160, 162, ("Ashley",), "", "https://docs.google.com/document/d/uat-private-document-id/edit", "CA-QC"),
        ("[UAT] Malformed planner link", 190, 191, ("Spencer",), "", "https://example.invalid/not-a-google-doc", "US-CA"),
    )
    for title, start_offset, end_offset, names, notes, link, destination in trip_specs:
        trip = _trip(
            accounts.owner,
            profiles,
            title,
            anchor + timedelta(days=start_offset),
            anchor + timedelta(days=end_offset),
            names,
            notes,
            link,
        )
        trips.append(trip)
        if destination:
            if destination in regions:
                _destination(trip, regions[destination].country, regions[destination])
            else:
                _destination(trip, countries[destination])
    # Add a second destination to exercise the multi-chip state.
    _destination(trips[4], countries["FR"])

    category, _ = Category.objects.update_or_create(
        user=accounts.owner,
        name="uat-place",
        defaults={"display_name": "UAT Place", "icon": "📍"},
    )
    place_specs = (
        ("[UAT] Saved Place", countries["FR"], None, None, ("Spencer",)),
        ("[UAT] Upcoming Place", countries["GB"], None, trips[3], ("Ashley",)),
        ("[UAT] California Place", countries["US"], regions["US-CA"], trips[0], ("Spencer",)),
        ("[UAT] Joint Boston Place", countries["US"], regions["US-MA"], trips[1], ("Joint",)),
        ("[UAT] Independent Boston Place", countries["US"], regions["US-MA"], None, ("Spencer", "Ashley")),
        ("[UAT] Ontario Place", countries["CA"], regions["CA-ON"], trips[2], ("Spencer", "Ashley", "Joint")),
    )
    places = []
    for index, (name, country, region, trip, names) in enumerate(place_specs):
        location, _ = Location.objects.update_or_create(
            user=accounts.owner,
            name=name,
            defaults={
                "category": category,
                "country": country,
                "region": region,
                "location": region.name if region else country.name,
                "description": "Synthetic UAT fixture",
            },
        )
        location.profiles.set([profiles[n] for n in names])
        places.append(location)
        if index >= 2:
            start = anchor + timedelta(days=(-120 + index * 12))
            visit, _ = Visit.objects.update_or_create(
                location=location,
                trip=trip,
                defaults={
                    "start_date": _aware(start),
                    "end_date": None if index == 2 else _aware(start + timedelta(days=2)),
                    "source": "manual",
                    "notes": "Synthetic UAT visit",
                },
            )
            visit.profiles.set([profiles[n] for n in names])
            for profile_name in names:
                profile = profiles[profile_name]
                ProfileTravelVisit.objects.update_or_create(
                    profile=profile,
                    place_visit=visit,
                    defaults={
                        "country": country,
                        "region": region,
                        "visit_date": start,
                        "end_date": start if index == 2 else start + timedelta(days=2),
                        "notes": "",
                    },
                )

    # Explicit polygon state: independent Spencer/Ashley in California must not
    # imply Joint; Massachusetts has explicit Joint plus later Spencer history.
    for profile_name in ("Spencer", "Ashley"):
        ProfileRegionVisit.objects.get_or_create(profile=profiles[profile_name], region=regions["US-CA"])
    ProfileRegionVisit.objects.get_or_create(profile=profiles["Joint"], region=regions["US-MA"])
    ProfileRegionVisit.objects.get_or_create(profile=profiles["Spencer"], region=regions["US-MA"])
    ProfileCountryVisit.objects.get_or_create(profile=profiles["Ashley"], country=countries["GB"])
    ProfileCountryVisit.objects.get_or_create(profile=profiles["Spencer"], country=countries["FR"])

    for profile_name, park_id, first_offset, count in (
        ("Spencer", "LAD", -300, 2),
        ("Ashley", "BOS", -80, 1),
        ("Joint", "PHI", -40, 1),
    ):
        BallparkVisit.objects.update_or_create(
            profile=profiles[profile_name],
            ballpark_id=park_id,
            defaults={
                "first_visit_date": anchor + timedelta(days=first_offset),
                "last_visit_date": anchor + timedelta(days=first_offset + count),
                "visit_count": count,
                "notes": "Synthetic UAT ballpark visit",
            },
        )

    connection = SkylightConnection.objects.create(
        owner=accounts.owner,
        encrypted_credentials="UAT_MOCK_CREDENTIAL_NOT_VALID",
        frame_id="uat-frame",
        frame_name="UAT Family Calendar",
        timezone="America/New_York",
        connected_at=timezone.now(),
        last_sync_at=timezone.now(),
    )
    suggestion_specs = (
        ("pending", "[UAT] Pending Skylight Trip", 20, None),
        ("accepted", "[UAT] Existing Trip Must Not Resuggest", -60, trips[1]),
        ("dismissed", "[UAT] Dismissed Skylight Trip", 24, None),
    )
    for status, title, offset, linked_trip in suggestion_specs:
        suggestion = SkylightTripSuggestion.objects.create(
            connection=connection,
            skylight_event_id=f"uat-{status}",
            title=title,
            start_date=anchor + timedelta(days=offset),
            end_date=anchor + timedelta(days=offset + 2),
            location="Synthetic destination",
            detection_score=90,
            detection_reasons=["UAT mock state"],
            status=status,
            trip=linked_trip,
        )
        suggestion.profiles.set([profiles["Joint"]])
        review = SkylightEventReview.objects.create(
            connection=connection,
            skylight_event_id=f"uat-review-{status}",
            title=title,
            start_date=suggestion.start_date,
            end_date=suggestion.end_date,
            location=suggestion.location,
            predicted_is_trip=True,
            detection_score=90,
            detection_reasons=["UAT mock state"],
            human_label=("trip" if status == "accepted" else "unreviewed"),
        )
        review.profiles.set([profiles["Joint"]])

    # Collector-neutral synthetic suggestions.  The token hash cannot
    # authenticate because it is intentionally not a usable password hash.
    device = LocationDevice.objects.create(
        owner=accounts.owner,
        profile=profiles["Spencer"],
        name="UAT OwnTracks device",
        auth_username="uat-owntracks",
        token_hash="!uat-unusable",
        owntracks_username="uat-spencer",
        device_identifier="uat-phone",
        last_report_at=timezone.now(),
    )
    stays = []
    stay_specs = (
        ("potential", "pending", {"type": "potential_place"}),
        ("accepted", "accepted", {"type": "potential_place"}),
        ("dismissed", "dismissed", {"type": "potential_place"}),
        ("ambiguous", "pending", {"type": "possible_joint_overlap", "ambiguous": True}),
        ("duplicate", "ignored", {"type": "potential_place", "duplicate_of": "uat-stay-accepted"}),
    )
    for index, (label, status, extra_evidence) in enumerate(stay_specs):
        stay = StayCandidate.objects.create(
            owner=accounts.owner,
            device=device,
            profile=profiles["Spencer"],
            fingerprint=f"uat-stay-{label}",
            center=Point(-20.0 + index, 0.0, srid=4326),
            arrived_at=_aware(anchor - timedelta(days=10 - index), 10),
            departed_at=_aware(anchor - timedelta(days=10 - index), 14),
            sample_count=4,
            confidence=0.55 + index * 0.1,
            suggested_name=f"[UAT] {label.title()} Place Suggestion",
            locality="Synthetic locality",
            evidence={"source": "uat", "explanation": f"{label} fixture", **extra_evidence},
            status=status,
        )
        stays.append(stay)
    for index, status in enumerate(("pending", "accepted", "dismissed")):
        journey = JourneyCandidate.objects.create(
            owner=accounts.owner,
            fingerprint=f"uat-journey-{status}",
            title=f"[UAT] {status.title()} Journey",
            started_at=_aware(anchor - timedelta(days=30 - index * 5)),
            ended_at=_aware(anchor - timedelta(days=27 - index * 5)),
            status=status,
            confidence=0.75,
            evidence={"source": "uat"},
            accepted_trip=trips[0] if status == "accepted" else None,
        )
        journey.profiles.set([profiles["Spencer"]])

    source = PhotoImportSource.objects.create(
        owner=accounts.owner,
        profile=profiles["Spencer"],
        name="UAT iCloud Photos",
        root_alias="uat-photos",
        auth_username="uat-icloud",
        token_hash="!uat-unusable",
        last_report_at=timezone.now(),
        last_scan_at=timezone.now(),
        backlog_count=1,
        error_count=1,
    )
    asset_specs = (
        ("ready", True, "uat-placeholder.png", "ready"),
        ("processing", True, "uat-processing.heic", "discovered"),
        ("unavailable", False, "uat-unavailable.jpg", "ready"),
        ("failed", True, "uat-failed.mov", "error"),
    )
    assets = []
    for index, (label, available, filename, state) in enumerate(asset_specs):
        media_kind = "video" if filename.endswith(".mov") else "image"
        asset = PhotoAsset.objects.create(
            source=source,
            profile=profiles["Spencer"],
            source_key=f"uat-{label}",
            relative_path=filename if label == "ready" else f"fixtures/{filename}",
            filename=filename,
            extension=f".{filename.rsplit('.', 1)[-1].lower()}",
            media_kind=media_kind,
            mime_type=(
                "video/quicktime"
                if media_kind == "video"
                else "image/png" if filename.endswith(".png") else "image/jpeg"
            ),
            size_bytes=1024 + index,
            captured_at=_aware(anchor - timedelta(days=index)),
            locality="Synthetic locality",
            metadata={"fixture": True},
            available=available,
            processing_state=state,
            error_message="Synthetic processing failure" if state == "error" else "",
        )
        assets.append(asset)
    TripPhotoLink.objects.create(
        asset=assets[0], trip=trips[0], confidence=1.0, explanation="UAT manual link", origin="manual"
    )
    photo_suggestion = PhotoMatchSuggestion.objects.create(
        asset=assets[1], reason="Date-only UAT match", confidence=0.5, status="pending"
    )
    photo_suggestion.candidate_trips.set([trips[0], trips[1]])

    return {"profiles": profiles, "trips": trips, "places": places}


def seed_stress(accounts: UATAccounts, anchor: date) -> dict:
    profiles = _profiles(accounts)
    category, _ = Category.objects.update_or_create(
        user=accounts.owner,
        name="uat-stress",
        defaults={"display_name": "UAT Stress", "icon": "🧪"},
    )
    trips = []
    for index in range(100):
        trips.append(
            _trip(
                accounts.owner,
                profiles,
                f"[UAT] Stress Trip {index:03d}",
                anchor + timedelta(days=index * 3 - 300),
                anchor + timedelta(days=index * 3 - 298),
                ("Spencer",) if index % 3 else ("Joint",),
                "Stress fixture",
            )
        )

    existing_names = set(
        Location.objects.filter(user=accounts.owner, name__startswith="[UAT] Stress Place ").values_list("name", flat=True)
    )
    missing_places = [
        Location(
            user=accounts.owner,
            category=category,
            name=f"[UAT] Stress Place {index:04d}",
            location=f"Synthetic locality {index % 25}",
            description="Stress fixture",
        )
        for index in range(500)
        if f"[UAT] Stress Place {index:04d}" not in existing_names
    ]
    Location.objects.bulk_create(missing_places, batch_size=100)

    source, _ = PhotoImportSource.objects.get_or_create(
        owner=accounts.owner,
        root_alias="uat-photos",
        defaults={
            "profile": profiles["Spencer"],
            "name": "UAT iCloud Photos",
            "auth_username": "uat-icloud",
            "token_hash": "!uat-unusable",
        },
    )
    existing_keys = set(
        PhotoAsset.objects.filter(source=source, source_key__startswith="uat-stress-").values_list("source_key", flat=True)
    )
    assets = []
    for index in range(1000):
        key = f"uat-stress-{index:04d}"
        if key in existing_keys:
            continue
        assets.append(
            PhotoAsset(
                source=source,
                profile=profiles["Spencer"],
                source_key=key,
                relative_path=f"fixtures/stress/{index:04d}.jpg",
                filename=f"{index:04d}.jpg",
                extension=".jpg",
                media_kind="image",
                mime_type="image/jpeg",
                size_bytes=2048,
                captured_at=_aware(anchor - timedelta(days=index % 365)),
                metadata={"fixture": True, "stress": True},
                available=index % 20 != 0,
                processing_state="ready",
            )
        )
    PhotoAsset.objects.bulk_create(assets, batch_size=100)
    return {"trips": trips}


def build_manifest(accounts: UATAccounts, anchor: date, scenario: str) -> dict:
    owner = accounts.owner
    uat_trips = Trip.objects.filter(owner=owner, title__startswith=UAT_PREFIX)
    uat_places = Location.objects.filter(user=owner, name__startswith=UAT_PREFIX)
    source = PhotoImportSource.objects.filter(owner=owner, root_alias="uat-photos").first()
    return {
        "schema_version": 1,
        "seed_version": "touchgrass-uat-v1",
        "anchor_date": anchor.isoformat(),
        "scenario": scenario,
        "accounts": [
            {"username": f"uat-{role}", "email": f"uat-{role}@example.invalid", "role": role}
            for role in ("owner", "member", "outsider", "empty")
        ],
        "expected": {
            "profiles": list(
                TravelProfile.objects.filter(owner=owner, name__in=("Spencer", "Ashley", "Joint"))
                .order_by("name")
                .values_list("name", flat=True)
            ),
            "uat_trip_count": uat_trips.count(),
            "uat_place_count": uat_places.count(),
            "photo_asset_count": source.assets.count() if source else 0,
            "pending_skylight_suggestions": SkylightTripSuggestion.objects.filter(
                connection__owner=owner, status="pending"
            ).count(),
            "ballpark_visit_count": BallparkVisit.objects.filter(profile__owner=owner).count(),
            "stay_suggestion_count": StayCandidate.objects.filter(owner=owner).count(),
            "journey_suggestion_count": JourneyCandidate.objects.filter(owner=owner).count(),
        },
        "fixtures": {
            "trips": list(uat_trips.order_by("title").values_list("title", flat=True)[:25]),
            "places": list(uat_places.order_by("name").values_list("name", flat=True)[:25]),
        },
        "security": {
            "contains_passwords": False,
            "contains_tokens": False,
            "contains_absolute_paths": False,
            "real_integrations_connected": False,
        },
    }


@transaction.atomic
def prepare(
    *,
    owner_username: str | None,
    common_password: str | None,
    anchor: date,
    scenario: str,
    reset: bool,
) -> tuple[dict, dict[str, str]]:
    require_uat_mode()
    accounts = scrub_database(owner_username, common_password)
    if reset:
        reset_generated_records(accounts.owner)
    if scenario in ("core", "all"):
        seed_core(accounts, anchor)
    if scenario in ("stress", "all"):
        seed_stress(accounts, anchor)
    # The household member should see both preserved cloned trips and seeded
    # UAT trips.  Collection sharing is the access-control source of truth for
    # the planner UI.
    for collection in Collection.objects.filter(user=accounts.owner).iterator():
        collection.shared_with.add(accounts.member)
    return build_manifest(accounts, anchor, scenario), accounts.generated_passwords


def write_manifest(manifest: dict, destination: str) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
