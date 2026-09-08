from pathlib import Path
import secrets

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import PhotoSourceAuthentication
from .media import original_response, preview_response
from .models import PhotoAsset, PhotoImportSource, PhotoMatchSuggestion, PhotoMatchSuppression, PhotoScanRun, TripPhotoLink
from .serializers import (
    LinkTripSerializer,
    PhotoAssetIngestSerializer,
    PhotoAssetSerializer,
    PhotoImportSourceSerializer,
    TripPhotoLinkSerializer,
)
from .services import create_source, match_asset, metadata_fingerprint, upsert_asset


class PhotoPagination(PageNumberPagination):
    page_size = 48
    page_size_query_param = "page_size"
    max_page_size = 100


class PhotoImportSourceViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PhotoImportSourceSerializer

    def get_queryset(self):
        return PhotoImportSource.objects.filter(owner=self.request.user).select_related("profile")

    @action(detail=False, methods=["post"])
    def pair(self, request):
        from worldtravel.models import TravelProfile
        try:
            profile = TravelProfile.objects.get(pk=request.data.get("profile"), owner=request.user)
        except TravelProfile.DoesNotExist:
            return Response({"detail": "Choose a profile you own."}, status=400)
        root_alias = request.data.get("root_alias", "icloud-photos")
        if PhotoImportSource.objects.filter(owner=request.user, root_alias=root_alias, revoked_at__isnull=True).exists():
            return Response({"detail": "This iCloud source is already paired."}, status=400)
        source, token = create_source(owner=request.user, profile=profile, name=request.data.get("name") or "iCloud Photos", root_alias=root_alias)
        # Device/poller authentication must go directly to Django. The Svelte
        # session proxy intentionally requires a browser session and therefore
        # cannot accept standalone Basic-auth collectors.
        public_base = settings.PUBLIC_URL.rstrip("/")
        return Response({
            "source": PhotoImportSourceSerializer(source).data,
            "provisioning": {
                "url": f"{public_base}/api/photo-ingest/icloud/assets/",
                "reconcile_url": f"{public_base}/api/photo-ingest/icloud/reconcile/",
                "username": source.auth_username,
                "token": token,
                "root_alias": source.root_alias,
            },
        }, status=201)

    def _toggle(self, source, enabled, revoked=False):
        source.enabled = enabled
        if revoked:
            source.revoked_at = timezone.now()
        source.save(update_fields=["enabled", "revoked_at", "updated_at"])
        return Response(PhotoImportSourceSerializer(source).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._toggle(self.get_object(), False)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        source = self.get_object()
        if source.is_revoked:
            return Response({"detail": "Revoked sources must be paired again."}, status=400)
        return self._toggle(source, True)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        return self._toggle(self.get_object(), False, True)

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        return Response(PhotoImportSourceSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="scan-now")
    def scan_now(self, request, pk=None):
        source = self.get_object()
        source.scan_requested_at = timezone.now()
        source.save(update_fields=["scan_requested_at", "updated_at"])
        return Response({"requested": True})

    @action(detail=True, methods=["post"], url_path="retry-errors")
    def retry_errors(self, request, pk=None):
        source = self.get_object()
        source.retry_requested_at = timezone.now()
        source.save(update_fields=["retry_requested_at", "updated_at"])
        return Response({"requested": True})


class PhotoAssetIngestView(APIView):
    authentication_classes = [PhotoSourceAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "photo_ingest"

    def get(self, request):
        source = request.auth
        return Response({
            "enabled": source.enabled,
            "scan_requested_at": source.scan_requested_at,
            "retry_requested_at": source.retry_requested_at,
        })

    def post(self, request):
        source = request.auth
        items = request.data.get("assets")
        if not isinstance(items, list) or not items or len(items) > 100:
            return Response({"detail": "assets must contain between 1 and 100 records."}, status=400)
        serializer = PhotoAssetIngestSerializer(data=items, many=True)
        serializer.is_valid(raise_exception=True)
        created = updated = errors = 0
        results = []
        for item in serializer.validated_data:
            try:
                asset, was_created = upsert_asset(source, item)
                created += int(was_created)
                updated += int(not was_created)
                results.append({"source_key": item["source_key"], "id": str(asset.id), "status": "created" if was_created else "updated"})
            except (ValueError, OSError) as exc:
                errors += 1
                results.append({"source_key": item.get("source_key"), "status": "error", "detail": str(exc)})
        source.last_report_at = timezone.now()
        source.error_count = errors
        source.save(update_fields=["last_report_at", "error_count", "updated_at"])
        return Response({"created": created, "updated": updated, "errors": errors, "results": results})


class PhotoReconcileView(APIView):
    authentication_classes = [PhotoSourceAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "photo_ingest"

    def post(self, request):
        source = request.auth
        seen = request.data.get("seen_source_keys")
        if not isinstance(seen, list) or len(seen) > 100000:
            return Response({"detail": "seen_source_keys must be a list."}, status=400)
        valid = {str(item) for item in seen if isinstance(item, str) and 32 <= len(item) <= 64}
        missing = source.assets.filter(available=True).exclude(source_key__in=valid).update(available=False)
        restored = source.assets.filter(available=False, source_key__in=valid).update(available=True)
        source.last_scan_at = timezone.now()
        source.last_report_at = timezone.now()
        source.backlog_count = max(0, int(request.data.get("backlog_count") or 0))
        source.error_count = max(0, int(request.data.get("error_count") or 0))
        source.save(update_fields=["last_scan_at", "last_report_at", "backlog_count", "error_count", "updated_at"])
        PhotoScanRun.objects.create(
            source=source, started_at=request.data.get("started_at") or timezone.now(), completed_at=timezone.now(),
            discovered_count=max(0, int(request.data.get("discovered_count") or 0)),
            updated_count=max(0, int(request.data.get("updated_count") or 0)), missing_count=missing,
            error_count=source.error_count, diagnostics={"restored": restored},
        )
        return Response({"missing": missing, "restored": restored})


class PhotoTokenRotateView(APIView):
    authentication_classes = [PhotoSourceAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "photo_ingest"

    def post(self, request):
        source = request.auth
        token = secrets.token_urlsafe(32)
        source.set_token(token)
        source.last_auth_failure_at = None
        source.save(update_fields=["token_hash", "last_auth_failure_at", "updated_at"])
        return Response({"token": token})


class PhotoAssetViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PhotoAssetSerializer
    pagination_class = PhotoPagination

    def get_queryset(self):
        queryset = PhotoAsset.objects.filter(
            Q(source__owner=self.request.user) | Q(trip_links__trip__collection__shared_with=self.request.user)
        ).select_related("source", "profile", "privacy_zone", "country", "region", "city", "match_suggestion").prefetch_related(
            "trip_links__trip", "match_suggestion__candidate_trips"
        ).distinct()
        params = self.request.query_params
        if params.get("trip"):
            queryset = queryset.filter(trip_links__trip_id=params["trip"])
        if params.get("media_kind"):
            queryset = queryset.filter(media_kind=params["media_kind"])
        if params.get("availability") == "available":
            queryset = queryset.filter(available=True)
        elif params.get("availability") == "unavailable":
            queryset = queryset.filter(available=False)
        if params.get("state"):
            queryset = queryset.filter(processing_state=params["state"])
        if params.get("date_from"):
            queryset = queryset.filter(captured_at__date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(captured_at__date__lte=params["date_to"])
        if params.get("search"):
            value = params["search"].strip()
            queryset = queryset.filter(Q(filename__icontains=value) | Q(locality__icontains=value) | Q(trip_links__trip__title__icontains=value))
        return queryset

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        asset = self.get_object()
        try:
            return preview_response(asset)
        except FileNotFoundError:
            asset.available = False
            asset.save(update_fields=["available", "updated_at"])
            return Response({"detail": "The iCloud original is not currently available."}, status=404)
        except Exception:
            return Response({"detail": "The preview could not be generated."}, status=503)

    @action(detail=True, methods=["get"])
    def original(self, request, pk=None):
        asset = self.get_object()
        try:
            return original_response(request, asset)
        except FileNotFoundError:
            asset.available = False
            asset.save(update_fields=["available", "updated_at"])
            return Response({"detail": "The iCloud original is not currently available."}, status=404)

    @action(detail=True, methods=["post"], url_path="link-trip")
    def link_trip(self, request, pk=None):
        asset = self.get_object()
        serializer = LinkTripSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        link, _ = TripPhotoLink.objects.update_or_create(
            asset=asset, trip=serializer.validated_data["trip"],
            defaults={"origin": TripPhotoLink.ORIGIN_MANUAL, "confidence": 1, "explanation": "Linked manually"},
        )
        PhotoMatchSuggestion.objects.filter(asset=asset).delete()
        return Response(TripPhotoLinkSerializer(link).data, status=201)

    @action(detail=True, methods=["post"], url_path="dismiss-match")
    def dismiss_match(self, request, pk=None):
        asset = self.get_object()
        if asset.source.owner_id != request.user.id:
            return Response({"detail": "Only the media owner can dismiss a match."}, status=403)
        suggestion = PhotoMatchSuggestion.objects.filter(
            asset=asset, status=PhotoMatchSuggestion.STATUS_PENDING
        ).first()
        if not suggestion:
            return Response(status=204)
        suggestion.status = PhotoMatchSuggestion.STATUS_DISMISSED
        suggestion.save(update_fields=["status", "updated_at"])
        for trip in suggestion.candidate_trips.all():
            PhotoMatchSuppression.objects.update_or_create(
                asset=asset,
                trip=trip,
                defaults={"metadata_fingerprint": metadata_fingerprint(asset)},
            )
        return Response(status=204)

    @action(detail=True, methods=["delete"], url_path=r"trip-links/(?P<link_id>[^/.]+)")
    def unlink_trip(self, request, pk=None, link_id=None):
        asset = self.get_object()
        try:
            link = asset.trip_links.get(pk=link_id)
        except TripPhotoLink.DoesNotExist:
            return Response(status=404)
        if link.trip.owner_id != request.user.id:
            return Response({"detail": "Only the trip owner can unlink media."}, status=403)
        if link.origin == TripPhotoLink.ORIGIN_AUTOMATIC:
            PhotoMatchSuppression.objects.update_or_create(
                asset=asset, trip=link.trip, defaults={"metadata_fingerprint": metadata_fingerprint(asset)}
            )
        link.delete()
        return Response(status=204)

    @action(detail=False, methods=["post"])
    def rematch(self, request):
        queryset = self.get_queryset().filter(source__owner=request.user)
        if request.data.get("ids"):
            queryset = queryset.filter(pk__in=request.data["ids"])
        count = 0
        for asset in queryset[:1000]:
            count += int(match_asset(asset) is not None)
        return Response({"linked": count})
