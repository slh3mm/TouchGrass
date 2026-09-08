from django.contrib.gis.geos import Point
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from adventures.models import Location, Visit
from worldtravel.models import TravelProfile, Trip

from .models import JourneyCandidate, LocationDevice, PrivacyZone, StayCandidate


class LocationDeviceSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name", read_only=True)
    profile_color = serializers.CharField(source="profile.color", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = LocationDevice
        fields = [
            "id", "name", "collector_type", "owntracks_username", "device_identifier", "profile",
            "profile_name", "profile_color", "enabled", "revoked_at", "last_report_at", "last_processed_at",
            "last_auth_failure_at", "created_at", "status",
        ]
        read_only_fields = ["id", "collector_type", "revoked_at", "last_report_at", "last_processed_at", "last_auth_failure_at", "created_at"]

    def get_status(self, obj):
        if obj.revoked_at:
            return "revoked"
        if not obj.enabled:
            return "paused"
        if not obj.last_report_at:
            if obj.last_auth_failure_at:
                return "authentication_failure"
            return "waiting"
        if obj.last_auth_failure_at and obj.last_auth_failure_at > obj.last_report_at:
            return "authentication_failure"
        if obj.last_report_at < timezone.now() - timezone.timedelta(hours=12):
            return "delayed"
        return "connected"


class PairDeviceSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    profile = serializers.PrimaryKeyRelatedField(queryset=TravelProfile.objects.none())
    owntracks_username = serializers.CharField(max_length=100, required=False)
    device_identifier = serializers.CharField(max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context["request"]
        self.fields["profile"].queryset = TravelProfile.objects.filter(owner=request.user)


class PrivacyZoneSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(write_only=True)
    longitude = serializers.FloatField(write_only=True)

    class Meta:
        model = PrivacyZone
        fields = ["id", "name", "latitude", "longitude", "radius_m", "is_home", "enabled", "created_at"]
        read_only_fields = ["id", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Exact zone centers are intentionally not returned after creation.
        data["configured"] = True
        return data

    def create(self, validated_data):
        lat = validated_data.pop("latitude")
        lon = validated_data.pop("longitude")
        return PrivacyZone.objects.create(
            owner=self.context["request"].user, center=Point(lon, lat, srid=4326), **validated_data
        )

    def update(self, instance, validated_data):
        lat = validated_data.pop("latitude", None)
        lon = validated_data.pop("longitude", None)
        if lat is not None and lon is not None:
            instance.center = Point(lon, lat, srid=4326)
        return super().update(instance, validated_data)


class StayCandidateSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name", read_only=True)
    profile_color = serializers.CharField(source="profile.color", read_only=True)
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    duration_minutes = serializers.SerializerMethodField()

    class Meta:
        model = StayCandidate
        fields = [
            "id", "suggested_name", "locality", "arrived_at", "departed_at", "duration_minutes",
            "sample_count", "confidence", "evidence", "status", "profile", "profile_name", "profile_color",
            "latitude", "longitude", "country", "region", "city", "enrichment_provider", "accepted_location",
        ]
        read_only_fields = fields

    def get_latitude(self, obj):
        return obj.center.y

    def get_longitude(self, obj):
        return obj.center.x

    def get_duration_minutes(self, obj):
        return int((obj.departed_at - obj.arrived_at).total_seconds() / 60)


class JourneyCandidateSerializer(serializers.ModelSerializer):
    profile_details = serializers.SerializerMethodField()
    stops = serializers.SerializerMethodField()

    class Meta:
        model = JourneyCandidate
        fields = [
            "id", "title", "started_at", "ended_at", "status", "confidence", "evidence",
            "profile_details", "stops", "accepted_trip",
            "matched_trip",
        ]
        read_only_fields = fields

    def get_profile_details(self, obj):
        return [{"id": str(p.id), "name": p.name, "color": p.color} for p in obj.profiles.all()]

    def get_stops(self, obj):
        return [StayCandidateSerializer(stop.stay).data for stop in obj.stops.select_related("stay__profile").all()]


class AcceptStaySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    profiles = serializers.PrimaryKeyRelatedField(many=True, queryset=TravelProfile.objects.none(), required=False)
    trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.none(), required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["profiles"].child_relation.queryset = TravelProfile.objects.filter(owner=user)
        self.fields["trip"].queryset = Trip.objects.filter(owner=user)


class AcceptJourneySerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160, required=False)
    profiles = serializers.PrimaryKeyRelatedField(many=True, queryset=TravelProfile.objects.none(), required=False)
    existing_trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.none(), required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context["request"].user
        self.fields["profiles"].child_relation.queryset = TravelProfile.objects.filter(owner=user)
        self.fields["existing_trip"].queryset = Trip.objects.filter(owner=user)


class PlaceVisitSerializer(serializers.ModelSerializer):
    profile_details = serializers.SerializerMethodField()
    trip_title = serializers.CharField(source="trip.title", read_only=True)
    profiles = serializers.PrimaryKeyRelatedField(many=True, queryset=TravelProfile.objects.none(), required=False)
    trip = serializers.PrimaryKeyRelatedField(queryset=Trip.objects.none(), required=False, allow_null=True)

    class Meta:
        model = Visit
        fields = [
            "id", "start_date", "end_date", "notes", "profiles", "profile_details",
            "trip", "trip_title", "source",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            allowed_profiles = TravelProfile.objects.filter(
                Q(owner=request.user) | Q(shared_with=request.user)
            ).distinct()
            self.fields["profiles"].child_relation.queryset = allowed_profiles
            self.fields["trip"].queryset = Trip.objects.filter(
                Q(owner=request.user)
                | Q(collection__shared_with=request.user)
                | Q(profiles__owner=request.user)
                | Q(profiles__shared_with=request.user)
            ).distinct()

    def get_profile_details(self, obj):
        return [{"id": str(p.id), "name": p.name, "color": p.color} for p in obj.profiles.all()]


class PlaceSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    profiles = serializers.SerializerMethodField()
    visits = PlaceVisitSerializer(many=True, read_only=True)
    status = serializers.SerializerMethodField()
    visit_count = serializers.IntegerField(read_only=True)
    most_recent_visit = serializers.DateTimeField(read_only=True)
    locality = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()
    distance_from_home_km = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = [
            "id", "name", "description", "location", "category", "profiles", "status",
            "visit_count", "most_recent_visit", "locality", "cover", "country", "region", "city",
            "latitude", "longitude", "visits", "created_at", "updated_at",
            "distance_from_home_km",
        ]
        read_only_fields = fields

    def get_category(self, obj):
        if not obj.category:
            return None
        return {"id": str(obj.category_id), "name": obj.category.display_name, "icon": obj.category.icon}

    def get_profiles(self, obj):
        return [{"id": str(p.id), "name": p.name, "color": p.color} for p in obj.profiles.all()]

    def get_status(self, obj):
        now = timezone.now()
        visits = list(obj.visits.all())
        if any(visit.start_date and visit.start_date <= now for visit in visits):
            return "visited"
        if any(visit.start_date and visit.start_date > now for visit in visits):
            return "upcoming"
        return "saved"

    def get_locality(self, obj):
        names = [getattr(obj.city, "name", None), getattr(obj.region, "name", None), getattr(obj.country, "name", None)]
        return ", ".join(name for name in names if name) or obj.location or ""

    def get_cover(self, obj):
        image = next((item for item in obj.images.all() if item.is_primary), None) or next(iter(obj.images.all()), None)
        if not image:
            return None
        if image.image:
            request = self.context.get("request")
            return request.build_absolute_uri(image.image.url) if request else image.image.url
        if image.immich_id:
            return f"/api/images/{image.id}/proxy/"
        return None

    def get_distance_from_home_km(self, obj):
        distance = getattr(obj, "distance_from_home", None)
        return round(distance.km, 1) if distance else None
