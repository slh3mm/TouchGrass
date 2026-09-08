import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils import timezone


User = get_user_model()


class LocationDevice(models.Model):
    COLLECTOR_OWNTRACKS = "owntracks"
    COLLECTOR_OVERLAND = "overland"
    COLLECTOR_CHOICES = (
        (COLLECTOR_OWNTRACKS, "OwnTracks"),
        (COLLECTOR_OVERLAND, "Overland (reserved)"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="location_devices")
    profile = models.ForeignKey(
        "worldtravel.TravelProfile", on_delete=models.CASCADE, related_name="location_devices"
    )
    name = models.CharField(max_length=100)
    collector_type = models.CharField(max_length=20, choices=COLLECTOR_CHOICES, default=COLLECTOR_OWNTRACKS)
    auth_username = models.CharField(max_length=120, unique=True)
    token_hash = models.CharField(max_length=256)
    owntracks_username = models.CharField(max_length=100)
    device_identifier = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_report_at = models.DateTimeField(null=True, blank=True)
    last_auth_failure_at = models.DateTimeField(null=True, blank=True)
    last_processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "owntracks_username", "device_identifier"],
                name="unique_owner_location_device",
            )
        ]

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    def set_token(self, token):
        self.token_hash = make_password(token)

    def check_token(self, token):
        return bool(token) and check_password(token, self.token_hash)

    def __str__(self):
        return f"{self.name} ({self.profile.name})"


class PrivacyZone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="location_privacy_zones")
    name = models.CharField(max_length=100)
    center = gis_models.PointField(srid=4326, geography=True)
    radius_m = models.PositiveIntegerField(default=500)
    is_home = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_home", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner"], condition=models.Q(is_home=True), name="one_home_privacy_zone_per_owner"
            )
        ]


class PrivacyEvent(models.Model):
    EVENT_ENTER = "enter"
    EVENT_LEAVE = "leave"
    EVENT_INSIDE = "inside"
    EVENT_CHOICES = ((EVENT_ENTER, "Enter"), (EVENT_LEAVE, "Leave"), (EVENT_INSIDE, "Inside"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(LocationDevice, on_delete=models.CASCADE, related_name="privacy_events")
    zone = models.ForeignKey(PrivacyZone, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=12, choices=EVENT_CHOICES)
    captured_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_at"]
        indexes = [models.Index(fields=["device", "captured_at"], name="privacy_device_time")]


class LocationSample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(LocationDevice, on_delete=models.CASCADE, related_name="samples")
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    point = gis_models.PointField(srid=4326, geography=True)
    accuracy_m = models.FloatField(null=True, blank=True)
    altitude_m = models.FloatField(null=True, blank=True)
    velocity_mps = models.FloatField(null=True, blank=True)
    motion_state = models.CharField(max_length=40, blank=True, default="")
    event_type = models.CharField(max_length=32, blank=True, default="location")
    battery_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    battery_state = models.CharField(max_length=20, blank=True, default="")
    source_adapter = models.CharField(max_length=20, default=LocationDevice.COLLECTOR_OWNTRACKS)
    source_fingerprint = models.CharField(max_length=64)
    implausible_jump = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    stay_candidate = models.ForeignKey(
        "StayCandidate", on_delete=models.SET_NULL, null=True, blank=True, related_name="samples"
    )

    class Meta:
        ordering = ["captured_at"]
        constraints = [
            models.UniqueConstraint(fields=["device", "source_fingerprint"], name="unique_device_sample")
        ]
        indexes = [
            models.Index(fields=["device", "captured_at"], name="sample_device_time"),
            models.Index(fields=["device", "processed_at"], name="sample_processing"),
        ]


class StayCandidate(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DISMISSED = "dismissed"
    STATUS_IGNORED = "ignored"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DISMISSED, "Dismissed"),
        (STATUS_IGNORED, "Always ignore"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stay_candidates")
    device = models.ForeignKey(LocationDevice, on_delete=models.CASCADE, related_name="stay_candidates")
    profile = models.ForeignKey("worldtravel.TravelProfile", on_delete=models.CASCADE, related_name="stay_candidates")
    fingerprint = models.CharField(max_length=64)
    center = gis_models.PointField(srid=4326, geography=True)
    radius_m = models.PositiveIntegerField(default=200)
    arrived_at = models.DateTimeField()
    departed_at = models.DateTimeField()
    sample_count = models.PositiveIntegerField(default=0)
    confidence = models.FloatField(default=0.5)
    suggested_name = models.CharField(max_length=200, blank=True, default="")
    locality = models.CharField(max_length=200, blank=True, default="")
    country = models.ForeignKey(
        "worldtravel.Country", on_delete=models.SET_NULL, null=True, blank=True, related_name="stay_candidates"
    )
    region = models.ForeignKey(
        "worldtravel.Region", on_delete=models.SET_NULL, null=True, blank=True, related_name="stay_candidates"
    )
    city = models.ForeignKey(
        "worldtravel.City", on_delete=models.SET_NULL, null=True, blank=True, related_name="stay_candidates"
    )
    enrichment_provider = models.CharField(max_length=30, blank=True, default="")
    external_place_id = models.CharField(max_length=200, blank=True, default="")
    evidence = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    accepted_location = models.ForeignKey(
        "adventures.Location", on_delete=models.SET_NULL, null=True, blank=True, related_name="source_stays"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-arrived_at"]
        constraints = [
            models.UniqueConstraint(fields=["device", "fingerprint"], name="unique_device_stay")
        ]
        indexes = [models.Index(fields=["owner", "status", "arrived_at"], name="stay_owner_status_time")]


class JourneyCandidate(models.Model):
    STATUS_OPEN = "open"
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = (
        (STATUS_OPEN, "In progress"),
        (STATUS_PENDING, "Needs review"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DISMISSED, "Dismissed"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="journey_candidates")
    fingerprint = models.CharField(max_length=64)
    title = models.CharField(max_length=200, blank=True, default="Possible trip")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    confidence = models.FloatField(default=0.5)
    evidence = models.JSONField(default=dict, blank=True)
    profiles = models.ManyToManyField("worldtravel.TravelProfile", blank=True, related_name="journey_candidates")
    accepted_trip = models.ForeignKey(
        "worldtravel.Trip", on_delete=models.SET_NULL, null=True, blank=True, related_name="source_journeys"
    )
    matched_trip = models.ForeignKey(
        "worldtravel.Trip", on_delete=models.SET_NULL, null=True, blank=True, related_name="matched_journeys"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "fingerprint"], name="unique_owner_journey")]


class JourneyStop(models.Model):
    journey = models.ForeignKey(JourneyCandidate, on_delete=models.CASCADE, related_name="stops")
    stay = models.ForeignKey(StayCandidate, on_delete=models.CASCADE, related_name="journey_stops")
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["journey", "stay"], name="unique_journey_stay"),
            models.UniqueConstraint(fields=["journey", "order"], name="unique_journey_stop_order"),
        ]


class LocationTrackingAuditEvent(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="location_tracking_audit_events")
    device = models.ForeignKey(
        LocationDevice, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    action = models.CharField(max_length=40)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
