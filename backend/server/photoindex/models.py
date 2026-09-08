import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.gis.db import models as gis_models
from django.db import models


User = get_user_model()


class PhotoImportSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="photo_import_sources")
    profile = models.ForeignKey("worldtravel.TravelProfile", on_delete=models.CASCADE, related_name="photo_sources")
    name = models.CharField(max_length=100, default="iCloud Photos")
    root_alias = models.SlugField(max_length=60, default="icloud-photos")
    auth_username = models.CharField(max_length=120, unique=True)
    token_hash = models.CharField(max_length=256)
    enabled = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_report_at = models.DateTimeField(null=True, blank=True)
    last_scan_at = models.DateTimeField(null=True, blank=True)
    last_auth_failure_at = models.DateTimeField(null=True, blank=True)
    scan_requested_at = models.DateTimeField(null=True, blank=True)
    retry_requested_at = models.DateTimeField(null=True, blank=True)
    backlog_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "root_alias"], condition=models.Q(revoked_at__isnull=True), name="unique_owner_photo_root"
            )
        ]

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    def set_token(self, token):
        self.token_hash = make_password(token)

    def check_token(self, token):
        return bool(token) and check_password(token, self.token_hash)


class PhotoAsset(models.Model):
    KIND_IMAGE = "image"
    KIND_VIDEO = "video"
    KIND_CHOICES = ((KIND_IMAGE, "Image"), (KIND_VIDEO, "Video"))
    STATE_DISCOVERED = "discovered"
    STATE_READY = "ready"
    STATE_ERROR = "error"
    STATE_CHOICES = ((STATE_DISCOVERED, "Discovered"), (STATE_READY, "Ready"), (STATE_ERROR, "Error"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(PhotoImportSource, on_delete=models.CASCADE, related_name="assets")
    profile = models.ForeignKey("worldtravel.TravelProfile", on_delete=models.CASCADE, related_name="photo_assets")
    source_key = models.CharField(max_length=64)
    relative_path = models.TextField()
    filename = models.CharField(max_length=255)
    extension = models.CharField(max_length=12)
    media_kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField(default=0)
    file_modified_at = models.DateTimeField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    captured_local = models.CharField(max_length=40, blank=True, default="")
    timezone_offset = models.CharField(max_length=10, blank=True, default="")
    point = gis_models.PointField(srid=4326, geography=True, null=True, blank=True)
    privacy_zone = models.ForeignKey(
        "locationtracking.PrivacyZone", on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_assets"
    )
    country = models.ForeignKey("worldtravel.Country", on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_assets")
    region = models.ForeignKey("worldtravel.Region", on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_assets")
    city = models.ForeignKey("worldtravel.City", on_delete=models.SET_NULL, null=True, blank=True, related_name="photo_assets")
    locality = models.CharField(max_length=200, blank=True, default="")
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    orientation = models.CharField(max_length=60, blank=True, default="")
    duration_seconds = models.FloatField(null=True, blank=True)
    camera_make = models.CharField(max_length=100, blank=True, default="")
    camera_model = models.CharField(max_length=100, blank=True, default="")
    live_photo_identifier = models.CharField(max_length=200, blank=True, default="")
    live_photo_pair = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="paired_live_photo_assets"
    )
    content_hash = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    available = models.BooleanField(default=True)
    processing_state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STATE_DISCOVERED)
    error_message = models.TextField(blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-captured_at", "-first_seen_at"]
        constraints = [models.UniqueConstraint(fields=["source", "source_key"], name="unique_photo_source_key")]
        indexes = [
            models.Index(fields=["source", "available", "processing_state"], name="photo_source_state"),
            models.Index(fields=["profile", "captured_at"], name="photo_profile_time"),
            models.Index(fields=["live_photo_identifier"], name="photo_live_identifier"),
        ]


class TripPhotoLink(models.Model):
    ORIGIN_AUTOMATIC = "automatic"
    ORIGIN_MANUAL = "manual"
    ORIGIN_CHOICES = ((ORIGIN_AUTOMATIC, "Automatic"), (ORIGIN_MANUAL, "Manual"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(PhotoAsset, on_delete=models.CASCADE, related_name="trip_links")
    trip = models.ForeignKey("worldtravel.Trip", on_delete=models.CASCADE, related_name="photo_links")
    confidence = models.FloatField(default=1.0)
    explanation = models.CharField(max_length=300, blank=True, default="")
    origin = models.CharField(max_length=12, choices=ORIGIN_CHOICES, default=ORIGIN_MANUAL)
    profile_evidence = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset__captured_at", "created_at"]
        constraints = [models.UniqueConstraint(fields=["asset", "trip"], name="unique_trip_photo_link")]


class PhotoMatchSuppression(models.Model):
    asset = models.ForeignKey(PhotoAsset, on_delete=models.CASCADE, related_name="match_suppressions")
    trip = models.ForeignKey("worldtravel.Trip", on_delete=models.CASCADE, related_name="photo_match_suppressions")
    metadata_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["asset", "trip"], name="unique_photo_match_suppression")]


class PhotoMatchSuggestion(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = ((STATUS_PENDING, "Pending"), (STATUS_ACCEPTED, "Accepted"), (STATUS_DISMISSED, "Dismissed"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.OneToOneField(PhotoAsset, on_delete=models.CASCADE, related_name="match_suggestion")
    candidate_trips = models.ManyToManyField("worldtravel.Trip", blank=True, related_name="photo_match_suggestions")
    reason = models.CharField(max_length=300)
    confidence = models.FloatField(default=0.5)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-asset__captured_at", "-created_at"]


class PhotoScanRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(PhotoImportSource, on_delete=models.CASCADE, related_name="scan_runs")
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    discovered_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    missing_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
