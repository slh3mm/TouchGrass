from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta

from worldtravel.models import TravelProfile, Trip

from .models import PhotoAsset, PhotoImportSource, PhotoMatchSuggestion, PhotoScanRun, TripPhotoLink


class PhotoImportSourceSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name", read_only=True)
    profile_color = serializers.CharField(source="profile.color", read_only=True)
    status = serializers.SerializerMethodField()
    indexed_count = serializers.IntegerField(source="assets.count", read_only=True)
    ready_count = serializers.SerializerMethodField()
    unavailable_count = serializers.SerializerMethodField()
    mount_available = serializers.SerializerMethodField()
    newly_discovered_count = serializers.SerializerMethodField()
    historical_progress = serializers.SerializerMethodField()

    class Meta:
        model = PhotoImportSource
        fields = [
            "id", "name", "root_alias", "profile", "profile_name", "profile_color", "status",
            "last_report_at", "last_scan_at", "backlog_count", "error_count", "indexed_count",
            "ready_count", "unavailable_count", "created_at",
            "mount_available",
            "newly_discovered_count", "historical_progress",
        ]
        read_only_fields = fields

    def get_status(self, obj):
        if obj.is_revoked:
            return "revoked"
        if not obj.enabled:
            return "paused"
        from pathlib import Path
        from django.conf import settings
        if not Path(settings.ICLOUD_PHOTOS_MOUNT).is_dir():
            return "unavailable"
        if obj.last_report_at is None:
            return "waiting"
        if obj.last_auth_failure_at and obj.last_auth_failure_at > obj.last_report_at:
            return "authentication failure"
        if obj.error_count:
            return "error"
        if obj.last_report_at < timezone.now() - timedelta(minutes=5):
            return "delayed"
        if obj.backlog_count:
            return "scanning"
        return "connected"

    def get_ready_count(self, obj):
        return obj.assets.filter(processing_state=PhotoAsset.STATE_READY).count()

    def get_unavailable_count(self, obj):
        return obj.assets.filter(available=False).count()

    def get_mount_available(self, obj):
        from pathlib import Path
        from django.conf import settings
        return Path(settings.ICLOUD_PHOTOS_MOUNT).is_dir()

    def get_newly_discovered_count(self, obj):
        latest = obj.scan_runs.order_by("-started_at").only("discovered_count").first()
        return latest.discovered_count if latest else 0

    def get_historical_progress(self, obj):
        indexed = obj.assets.count()
        total = indexed + obj.backlog_count
        return round(indexed / total * 100, 1) if total else 0


class PhotoAssetSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name", read_only=True)
    profile_color = serializers.CharField(source="profile.color", read_only=True)
    country_name = serializers.CharField(source="country.name", read_only=True, allow_null=True)
    region_name = serializers.CharField(source="region.name", read_only=True, allow_null=True)
    trip_links = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    original_url = serializers.SerializerMethodField()
    match_suggestion = serializers.SerializerMethodField()

    class Meta:
        model = PhotoAsset
        fields = [
            "id", "filename", "media_kind", "mime_type", "size_bytes", "captured_at", "captured_local",
            "timezone_offset", "locality", "country_name", "region_name", "width", "height", "orientation",
            "duration_seconds", "camera_make", "camera_model", "live_photo_identifier", "available",
            "live_photo_pair",
            "processing_state", "error_message", "profile", "profile_name", "profile_color", "trip_links",
            "preview_url", "original_url", "first_seen_at", "last_seen_at",
            "match_suggestion",
        ]
        read_only_fields = fields

    def get_trip_links(self, obj):
        return [{"id": str(link.id), "trip_id": str(link.trip_id), "trip_title": link.trip.title, "origin": link.origin,
                 "confidence": link.confidence, "explanation": link.explanation} for link in obj.trip_links.all()]

    def get_preview_url(self, obj):
        return f"/api/photo-assets/{obj.id}/preview/"

    def get_original_url(self, obj):
        return f"/api/photo-assets/{obj.id}/original/"

    def get_match_suggestion(self, obj):
        try:
            suggestion = obj.match_suggestion
        except PhotoMatchSuggestion.DoesNotExist:
            return None
        if suggestion.status != PhotoMatchSuggestion.STATUS_PENDING:
            return None
        return {
            "id": str(suggestion.id),
            "reason": suggestion.reason,
            "confidence": suggestion.confidence,
            "candidate_trips": [
                {"id": str(trip.id), "title": trip.title}
                for trip in suggestion.candidate_trips.all()
            ],
        }


class PhotoAssetIngestSerializer(serializers.Serializer):
    source_key = serializers.RegexField(r"^[0-9a-fA-F]{32,64}$", max_length=64)
    relative_path = serializers.CharField(max_length=2000)
    mime_type = serializers.CharField(max_length=100, required=False, allow_blank=True)
    size_bytes = serializers.IntegerField(min_value=0, required=False)
    file_modified_at = serializers.DateTimeField(required=False, allow_null=True)
    captured_at = serializers.DateTimeField(required=False, allow_null=True)
    captured_local = serializers.CharField(max_length=40, required=False, allow_blank=True)
    timezone_offset = serializers.CharField(max_length=10, required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    width = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    height = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    orientation = serializers.CharField(max_length=60, required=False, allow_blank=True)
    duration_seconds = serializers.FloatField(min_value=0, required=False, allow_null=True)
    camera_make = serializers.CharField(max_length=100, required=False, allow_blank=True)
    camera_model = serializers.CharField(max_length=100, required=False, allow_blank=True)
    live_photo_identifier = serializers.CharField(max_length=200, required=False, allow_blank=True)
    content_hash = serializers.RegexField(r"^[0-9a-fA-F]{64}$", required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise serializers.ValidationError("latitude and longitude must be supplied together")
        return attrs


class TripPhotoLinkSerializer(serializers.ModelSerializer):
    trip_title = serializers.CharField(source="trip.title", read_only=True)

    class Meta:
        model = TripPhotoLink
        fields = ["id", "asset", "trip", "trip_title", "confidence", "explanation", "origin", "profile_evidence", "created_at"]
        read_only_fields = ["id", "asset", "trip_title", "origin", "created_at"]


class LinkTripSerializer(serializers.Serializer):
    trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["trip"].queryset = Trip.objects.filter(owner=self.context["request"].user)
