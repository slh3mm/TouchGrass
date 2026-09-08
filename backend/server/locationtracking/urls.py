from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    JourneyCandidateViewSet,
    LocationDeviceViewSet,
    LocationSuggestionListView,
    LocationSuggestionActionView,
    LocationTrackingCleanupView,
    OwnTracksIngestView,
    PrivacyZoneViewSet,
    PlaceViewSet,
    StayCandidateViewSet,
)

router = DefaultRouter()
router.register("location-devices", LocationDeviceViewSet, basename="location-device")
router.register("privacy-zones", PrivacyZoneViewSet, basename="privacy-zone")
router.register("stay-candidates", StayCandidateViewSet, basename="stay-candidate")
router.register("journey-candidates", JourneyCandidateViewSet, basename="journey-candidate")
router.register("places", PlaceViewSet, basename="place")

urlpatterns = [
    path("location-ingest/owntracks/", OwnTracksIngestView.as_view(), name="owntracks-ingest"),
    path("location-suggestions/", LocationSuggestionListView.as_view(), name="location-suggestions"),
    path(
        "location-suggestions/<uuid:pk>/split/",
        JourneyCandidateViewSet.as_view({"post": "split"}),
        name="location-suggestion-split",
    ),
    path(
        "location-suggestions/merge/",
        JourneyCandidateViewSet.as_view({"post": "merge"}),
        name="location-suggestion-merge",
    ),
    path("location-suggestions/<uuid:pk>/<str:decision>/", LocationSuggestionActionView.as_view(), name="location-suggestion-action"),
    path("location-tracking/cleanup/", LocationTrackingCleanupView.as_view(), name="location-cleanup"),
    path("", include(router.urls)),
]
