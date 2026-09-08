from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PhotoAssetIngestView, PhotoAssetViewSet, PhotoImportSourceViewSet, PhotoReconcileView, PhotoTokenRotateView


router = DefaultRouter()
router.register("photo-sources", PhotoImportSourceViewSet, basename="photo-source")
router.register("photo-assets", PhotoAssetViewSet, basename="photo-asset")

urlpatterns = [
    path("photo-ingest/icloud/assets/", PhotoAssetIngestView.as_view(), name="icloud-photo-ingest"),
    path("photo-ingest/icloud/reconcile/", PhotoReconcileView.as_view(), name="icloud-photo-reconcile"),
    path("photo-ingest/icloud/rotate-token/", PhotoTokenRotateView.as_view(), name="icloud-photo-rotate-token"),
    path("", include(router.urls)),
]
