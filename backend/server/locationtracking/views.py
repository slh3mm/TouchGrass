from datetime import datetime

from django.db.models import Count, Max, Q
from django.db import transaction
from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from adventures.models import Category, ContentAttachment, ContentImage, Location, Visit

from .adapters import InvalidLocationPayload, parse_owntracks
from .authentication import OwnTracksDeviceAuthentication
from .models import (
    JourneyCandidate,
    JourneyStop,
    LocationDevice,
    LocationSample,
    LocationTrackingAuditEvent,
    PrivacyZone,
    StayCandidate,
)
from .serializers import (
    AcceptJourneySerializer,
    AcceptStaySerializer,
    JourneyCandidateSerializer,
    LocationDeviceSerializer,
    PlaceSerializer,
    PlaceVisitSerializer,
    PairDeviceSerializer,
    PrivacyZoneSerializer,
    StayCandidateSerializer,
)
from .services import (
    accept_journey,
    accept_stay,
    cleanup_expired_samples,
    create_device,
    process_device_samples,
    schedule_processing,
    store_normalized_sample,
)


class DeviceIngestThrottle(SimpleRateThrottle):
    scope = "owntracks_device"

    def get_cache_key(self, request, view):
        device = getattr(request, "auth", None)
        return self.cache_format % {"scope": self.scope, "ident": str(getattr(device, "pk", "unknown"))}


class OwnTracksIngestView(APIView):
    """Private telemetry ingress. Session CSRF is deliberately not used here."""

    authentication_classes = [OwnTracksDeviceAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [DeviceIngestThrottle]

    def post(self, request):
        device = request.auth
        try:
            normalized = parse_owntracks(request.data, device)
        except InvalidLocationPayload as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if normalized is None:
            # OwnTracks expects a successful JSON response for message types that
            # the recorder does not consume.
            return Response([])
        sample, created, redacted = store_normalized_sample(device, normalized)
        if created and sample:
            schedule_processing(device.pk)
        return Response([])


class LocationDeviceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LocationDeviceSerializer

    def get_queryset(self):
        return LocationDevice.objects.filter(owner=self.request.user).select_related("profile")

    @action(detail=False, methods=["post"])
    def pair(self, request):
        if not PrivacyZone.objects.filter(owner=request.user, is_home=True, enabled=True).exists():
            return Response({"detail": "Configure the Home privacy zone before pairing a phone."}, status=400)
        serializer = PairDeviceSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        device, token = create_device(owner=request.user, **serializer.validated_data)
        LocationTrackingAuditEvent.objects.create(owner=request.user, device=device, action="paired")
        ingest_url = f"{settings.FRONTEND_URL.rstrip('/')}/api/location-ingest/owntracks/"
        return Response(
            {
                "device": LocationDeviceSerializer(device).data,
                "provisioning": {
                    "url": ingest_url,
                    "username": device.auth_username,
                    "token": token,
                    "tracker_id": device.device_identifier,
                    "display_once": True,
                    "mode": "http",
                },
            },
            status=status.HTTP_201_CREATED,
        )

    def _set_state(self, request, *, enabled, revoked=False):
        device = self.get_object()
        if revoked:
            device.enabled = False
            device.revoked_at = timezone.now()
            action_name = "revoked"
        else:
            if device.revoked_at:
                return Response({"detail": "A revoked device must be paired again."}, status=409)
            device.enabled = enabled
            action_name = "resumed" if enabled else "paused"
        device.save(update_fields=["enabled", "revoked_at", "updated_at"])
        LocationTrackingAuditEvent.objects.create(owner=request.user, device=device, action=action_name)
        return Response(LocationDeviceSerializer(device).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._set_state(request, enabled=False)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._set_state(request, enabled=True)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        return self._set_state(request, enabled=False, revoked=True)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        return Response(LocationDeviceSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        return Response(process_device_samples(self.get_object().pk))

    @action(detail=True, methods=["delete"], url_path="raw-history")
    def raw_history(self, request, pk=None):
        device = self.get_object()
        queryset = device.samples.all()
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        try:
            if start:
                queryset = queryset.filter(captured_at__gte=datetime.fromisoformat(start))
            if end:
                queryset = queryset.filter(captured_at__lte=datetime.fromisoformat(end))
        except ValueError:
            return Response({"detail": "Use ISO-8601 start and end values."}, status=400)
        deleted, _ = queryset.delete()
        return Response({"deleted": deleted})

    @action(detail=False, methods=["delete"])
    def purge(self, request):
        scope = request.query_params.get("scope", "candidates")
        if request.data.get("confirm") != "DELETE":
            return Response({"detail": "Send confirm=DELETE to remove tracking data."}, status=400)
        devices = LocationDevice.objects.filter(owner=request.user)
        if scope == "raw":
            deleted, _ = LocationSample.objects.filter(device__in=devices).delete()
        elif scope == "candidates":
            deleted, _ = StayCandidate.objects.filter(owner=request.user).exclude(status="accepted").delete()
            journey_deleted, _ = JourneyCandidate.objects.filter(owner=request.user).exclude(status="accepted").delete()
            deleted += journey_deleted
        elif scope == "all":
            deleted, _ = devices.delete()
            zone_deleted, _ = PrivacyZone.objects.filter(owner=request.user).delete()
            deleted += zone_deleted
        else:
            return Response({"detail": "scope must be raw, candidates, or all"}, status=400)
        return Response({"deleted": deleted, "scope": scope})


class PrivacyZoneViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PrivacyZoneSerializer

    def get_queryset(self):
        return PrivacyZone.objects.filter(owner=self.request.user)


class StayCandidateViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StayCandidateSerializer

    def get_queryset(self):
        queryset = StayCandidate.objects.filter(owner=self.request.user).select_related("profile", "accepted_location")
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        return queryset

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        stay = self.get_object()
        serializer = AcceptStaySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        location = accept_stay(
            stay,
            name=data.get("name"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            profile_ids=[profile.pk for profile in data.get("profiles", [])] or None,
            trip=data.get("trip"),
        )
        return Response({"location_id": location.pk, "accepted": True})

    def _decide(self, request, value):
        stay = self.get_object()
        stay.status = value
        stay.evidence = {**stay.evidence, "dismissal_reason": request.data.get("reason", "")[:500]}
        stay.save(update_fields=["status", "evidence", "updated_at"])
        return Response(StayCandidateSerializer(stay).data)

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        return self._decide(request, StayCandidate.STATUS_DISMISSED)

    @action(detail=True, methods=["post"], url_path="always-ignore")
    def always_ignore(self, request, pk=None):
        return self._decide(request, StayCandidate.STATUS_IGNORED)


class JourneyCandidateViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = JourneyCandidateSerializer

    def get_queryset(self):
        queryset = JourneyCandidate.objects.filter(owner=self.request.user).prefetch_related(
            "profiles", "stops__stay__profile"
        )
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        return queryset

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        journey = self.get_object()
        serializer = AcceptJourneySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        trip = accept_journey(
            journey,
            title=data.get("title"),
            profile_ids=[profile.pk for profile in data.get("profiles", [])] or None,
            existing_trip=data.get("existing_trip"),
        )
        return Response({"trip_id": trip.pk, "accepted": True})

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        journey = self.get_object()
        journey.status = JourneyCandidate.STATUS_DISMISSED
        journey.evidence = {**journey.evidence, "dismissal_reason": request.data.get("reason", "")[:500]}
        journey.save(update_fields=["status", "evidence", "updated_at"])
        return Response(JourneyCandidateSerializer(journey).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def split(self, request, pk=None):
        journey = self.get_object()
        stops = list(journey.stops.select_related("stay").order_by("order"))
        split_at = int(request.data.get("at", 0) or 0)
        if split_at <= 0 or split_at >= len(stops):
            return Response({"detail": "at must split between two existing stops"}, status=400)
        second_stops = stops[split_at:]
        fingerprint = f"{journey.fingerprint[:48]}-split-{split_at}"
        second = JourneyCandidate.objects.create(
            owner=journey.owner,
            fingerprint=fingerprint,
            title=f"{journey.title} (part 2)",
            started_at=second_stops[0].stay.arrived_at,
            ended_at=second_stops[-1].stay.departed_at,
            status=JourneyCandidate.STATUS_PENDING,
            confidence=journey.confidence,
            evidence={**journey.evidence, "split_from": str(journey.pk)},
        )
        for index, stop in enumerate(second_stops):
            stop.journey = second
            stop.order = index
            stop.save(update_fields=["journey", "order"])
        second.profiles.set({stop.stay.profile for stop in second_stops})
        journey.ended_at = stops[split_at - 1].stay.departed_at
        journey.save(update_fields=["ended_at", "updated_at"])
        return Response({"first": JourneyCandidateSerializer(journey).data, "second": JourneyCandidateSerializer(second).data})

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def merge(self, request):
        ids = request.data.get("ids") or []
        journeys = list(self.get_queryset().filter(pk__in=ids).order_by("started_at"))
        if len(journeys) < 2:
            return Response({"detail": "Select at least two journeys."}, status=400)
        if any(item.status == JourneyCandidate.STATUS_ACCEPTED for item in journeys):
            return Response({"detail": "Accepted journeys cannot be merged."}, status=409)
        primary = journeys[0]
        stays = []
        seen = set()
        for journey in journeys:
            for stop in journey.stops.select_related("stay").all():
                if stop.stay_id not in seen:
                    seen.add(stop.stay_id)
                    stays.append(stop.stay)
        stays.sort(key=lambda stay: stay.arrived_at)
        primary.stops.all().delete()
        JourneyStop.objects.bulk_create([JourneyStop(journey=primary, stay=stay, order=index) for index, stay in enumerate(stays)])
        primary.started_at = stays[0].arrived_at
        primary.ended_at = stays[-1].departed_at
        primary.evidence = {**primary.evidence, "merged_journeys": [str(item.pk) for item in journeys]}
        primary.save(update_fields=["started_at", "ended_at", "evidence", "updated_at"])
        primary.profiles.set({stay.profile for stay in stays})
        JourneyCandidate.objects.filter(pk__in=[item.pk for item in journeys[1:]]).delete()
        return Response(JourneyCandidateSerializer(primary).data)


class LocationSuggestionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        kind = request.query_params.get("type")
        status_filter = request.query_params.get("status", "pending")
        data = []
        if kind in (None, "place"):
            stays = StayCandidate.objects.filter(owner=request.user, status=status_filter).select_related("profile")[:100]
            data.extend({"type": "place", **StayCandidateSerializer(item).data} for item in stays)
        if kind in (None, "trip"):
            journeys = JourneyCandidate.objects.filter(owner=request.user, status=status_filter).prefetch_related(
                "profiles", "stops__stay__profile"
            )[:100]
            data.extend({"type": "trip", **JourneyCandidateSerializer(item).data} for item in journeys)
        return Response({"count": len(data), "results": data})


class LocationSuggestionActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, decision):
        journey = JourneyCandidate.objects.filter(owner=request.user, pk=pk).first()
        stay = None if journey else StayCandidate.objects.filter(owner=request.user, pk=pk).first()
        if not journey and not stay:
            return Response({"detail": "Suggestion not found."}, status=404)
        if decision == "dismiss":
            candidate = journey or stay
            candidate.status = JourneyCandidate.STATUS_DISMISSED if journey else StayCandidate.STATUS_DISMISSED
            candidate.evidence = {**candidate.evidence, "dismissal_reason": request.data.get("reason", "")[:500]}
            candidate.save(update_fields=["status", "evidence", "updated_at"])
            return Response({"dismissed": True})
        if decision != "accept":
            return Response({"detail": "Unsupported decision."}, status=400)
        if journey:
            serializer = AcceptJourneySerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            trip = accept_journey(
                journey, title=values.get("title"),
                profile_ids=[profile.pk for profile in values.get("profiles", [])] or None,
                existing_trip=values.get("existing_trip"),
            )
            return Response({"accepted": True, "trip_id": trip.pk})
        serializer = AcceptStaySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        place = accept_stay(
            stay, name=values.get("name"), start_date=values.get("start_date"), end_date=values.get("end_date"),
            profile_ids=[profile.pk for profile in values.get("profiles", [])] or None, trip=values.get("trip"),
        )
        return Response({"accepted": True, "location_id": place.pk})


class LocationTrackingCleanupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"deleted": cleanup_expired_samples()})


class PlacePagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100


class PlaceViewSet(viewsets.ReadOnlyModelViewSet):
    """TouchGrass-owned, accepted-Place interface.

    This intentionally exposes AdventureLog Locations only. Raw telemetry and
    candidates use separate serializers and can never leak through this API.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PlaceSerializer
    pagination_class = PlacePagination

    def get_queryset(self):
        queryset = (
            Location.objects.filter(user=self.request.user)
            .select_related("category", "city", "region", "country")
            .prefetch_related("profiles", "images", "visits__profiles", "visits__trip")
            .annotate(visit_count=Count("visits", distinct=True), most_recent_visit=Max("visits__start_date"))
        )
        params = self.request.query_params
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(category__display_name__icontains=search)
                | Q(city__name__icontains=search)
                | Q(region__name__icontains=search)
                | Q(country__name__icontains=search)
                | Q(visits__trip__title__icontains=search)
            )
        if params.get("profile"):
            queryset = queryset.filter(Q(profiles=params["profile"]) | Q(visits__profiles=params["profile"]))
        if params.get("category"):
            queryset = queryset.filter(category_id=params["category"])
        if params.get("country"):
            queryset = queryset.filter(country_id=params["country"])
        if params.get("region"):
            queryset = queryset.filter(region_id=params["region"])
        if params.get("trip"):
            queryset = queryset.filter(visits__trip_id=params["trip"])
        if params.get("source"):
            queryset = queryset.filter(visits__source=params["source"])
        if params.get("date_from"):
            queryset = queryset.filter(visits__end_date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(visits__start_date__lte=params["date_to"])
        now = timezone.now()
        status_filter = params.get("status")
        if status_filter == "visited":
            queryset = queryset.filter(visits__start_date__lte=now)
        elif status_filter == "upcoming":
            queryset = queryset.filter(visits__start_date__gt=now)
        elif status_filter == "saved":
            queryset = queryset.filter(visits__isnull=True)
        ordering = {
            "recent": "-most_recent_visit",
            "oldest": "most_recent_visit",
            "name": "name",
            "most_visited": "-visit_count",
            "distance": "distance_from_home",
        }.get(params.get("sort", "recent"), "-most_recent_visit")
        if params.get("sort") == "distance":
            home = PrivacyZone.objects.filter(owner=self.request.user, is_home=True, enabled=True).first()
            if home:
                queryset = queryset.exclude(point__isnull=True).annotate(distance_from_home=Distance("point", home.center))
            else:
                ordering = "name"
        return queryset.distinct().order_by(ordering, "name")

    @action(detail=False, methods=["get"])
    def facets(self, request):
        base = Location.objects.filter(user=request.user)
        now = timezone.now()
        return Response(
            {
                "total": base.count(),
                "visited": base.filter(visits__start_date__lte=now).distinct().count(),
                "upcoming": base.filter(visits__start_date__gt=now).distinct().count(),
                "saved": base.filter(visits__isnull=True).count(),
                "needs_review": StayCandidate.objects.filter(owner=request.user, status="pending").count()
                + JourneyCandidate.objects.filter(owner=request.user, status="pending").count(),
                "categories": list(
                    Category.objects.filter(user=request.user)
                    .annotate(count=Count("location"))
                    .values("id", "display_name", "icon", "count")
                ),
            }
        )

    @action(detail=False, methods=["get"])
    def pins(self, request):
        queryset = self.get_queryset().exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        bbox = request.query_params.get("bbox", "")
        if bbox:
            try:
                west, south, east, north = [float(value) for value in bbox.split(",")]
                queryset = queryset.filter(
                    longitude__gte=west, longitude__lte=east, latitude__gte=south, latitude__lte=north
                )
            except (TypeError, ValueError):
                return Response({"detail": "bbox must be west,south,east,north"}, status=400)
        payload = []
        selected_trip = request.query_params.get("trip")
        for place in queryset[:2000]:
            trip_visit = min(
                (visit for visit in place.visits.all() if not selected_trip or str(visit.trip_id) == selected_trip),
                key=lambda visit: visit.start_date or timezone.now(),
                default=None,
            )
            payload.append(
                {
                    "id": str(place.pk),
                    "name": place.name,
                    "latitude": place.latitude,
                    "longitude": place.longitude,
                    "status": PlaceSerializer(place, context={"request": request}).data["status"],
                    "profiles": [
                        {"id": str(profile.pk), "color": profile.color} for profile in place.profiles.all()
                    ],
                    "trip_visit_at": trip_visit.start_date if selected_trip and trip_visit else None,
                }
            )
        return Response(payload)

    @action(detail=True, methods=["post", "patch", "delete"], url_path="visits")
    def visits(self, request, pk=None):
        place = self.get_object()
        instance = None
        if request.method in {"PATCH", "DELETE"}:
            visit_id = request.data.get("id") or request.data.get("visit_id")
            instance = place.visits.filter(pk=visit_id).first()
            if not instance:
                return Response({"detail": "Visit not found."}, status=404)
        if request.method == "DELETE":
            instance.delete()
            return Response(status=204)
        serializer = PlaceVisitSerializer(
            instance, data=request.data, partial=request.method == "PATCH",
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        visit = serializer.save(location=place)
        if not visit.profiles.exists():
            visit.profiles.set(place.profiles.all())
        return Response(PlaceVisitSerializer(visit).data, status=200 if instance else 201)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def merge(self, request, pk=None):
        primary = self.get_object()
        duplicate_ids = request.data.get("duplicate_ids") or []
        duplicates = list(Location.objects.filter(user=request.user, pk__in=duplicate_ids).exclude(pk=primary.pk))
        if not duplicates:
            return Response({"detail": "Choose at least one duplicate Place."}, status=400)
        primary.profiles.add(*(profile for item in duplicates for profile in item.profiles.all()))
        primary.collections.add(*(collection for item in duplicates for collection in item.collections.all()))
        location_type = ContentType.objects.get_for_model(Location)
        for duplicate in duplicates:
            duplicate.visits.update(location=primary)
            ContentImage.objects.filter(content_type=location_type, object_id=duplicate.pk).update(object_id=primary.pk)
            ContentAttachment.objects.filter(content_type=location_type, object_id=duplicate.pk).update(object_id=primary.pk)
            duplicate.delete()
        primary.refresh_from_db()
        return Response(PlaceSerializer(primary, context={"request": request}).data)
