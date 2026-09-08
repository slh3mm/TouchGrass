import base64
import hashlib
from datetime import timedelta
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from PIL import Image

from adventures.models import Collection, Location, Visit
from locationtracking.models import PrivacyZone
from worldtravel.models import TravelProfile, Trip

from .models import PhotoAsset, PhotoMatchSuggestion, TripPhotoLink
from .media import ensure_preview
from .services import create_source, resolve_asset_path


User = get_user_model()


class PhotoIndexApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="spencer-photo-test", password="test")
        self.profile = TravelProfile.objects.create(owner=self.user, name="Spencer", color="#f4c542")
        self.source, self.token = create_source(owner=self.user, profile=self.profile)
        self.client = APIClient()
        credentials = base64.b64encode(f"{self.source.auth_username}:{self.token}".encode()).decode()
        self.auth = {"HTTP_AUTHORIZATION": f"Basic {credentials}"}
        self.captured = timezone.now().replace(microsecond=0)

    def payload(self, path="IMG_1000.HEIC", latitude=39.9526, longitude=-75.1652):
        return {
            "source_key": hashlib.sha256(path.lower().encode()).hexdigest(),
            "relative_path": path,
            "mime_type": "image/heic",
            "size_bytes": 12345,
            "file_modified_at": self.captured.isoformat(),
            "captured_at": self.captured.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "width": 4032,
            "height": 3024,
            "camera_make": "Apple",
            "camera_model": "iPhone",
        }

    def test_ingest_is_authenticated_and_idempotent(self):
        url = "/api/photo-ingest/icloud/assets/"
        self.assertEqual(self.client.post(url, {"assets": [self.payload()]}, format="json").status_code, 401)
        first = self.client.post(url, {"assets": [self.payload()]}, format="json", **self.auth)
        second = self.client.post(url, {"assets": [self.payload()]}, format="json", **self.auth)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PhotoAsset.objects.count(), 1)

    def test_poller_can_rotate_its_one_time_credential(self):
        response = self.client.post("/api/photo-ingest/icloud/rotate-token/", {}, format="json", **self.auth)
        self.assertEqual(response.status_code, 200)
        replacement = response.data["token"]
        self.assertGreaterEqual(len(replacement), 32)

        old_response = self.client.get("/api/photo-ingest/icloud/assets/", **self.auth)
        self.assertEqual(old_response.status_code, 401)

        credentials = base64.b64encode(f"{self.source.auth_username}:{replacement}".encode()).decode()
        new_auth = {"HTTP_AUTHORIZATION": f"Basic {credentials}"}
        new_response = self.client.get("/api/photo-ingest/icloud/assets/", **new_auth)
        self.assertEqual(new_response.status_code, 200)

    def test_privacy_zone_discards_exact_gps(self):
        PrivacyZone.objects.create(owner=self.user, name="Home", center=Point(-75.1652, 39.9526, srid=4326), radius_m=500, is_home=True)
        response = self.client.post("/api/photo-ingest/icloud/assets/", {"assets": [self.payload()]}, format="json", **self.auth)
        self.assertEqual(response.status_code, 200)
        asset = PhotoAsset.objects.get()
        self.assertIsNone(asset.point)
        self.assertIsNotNone(asset.privacy_zone_id)

    def test_path_traversal_is_rejected(self):
        response = self.client.post(
            "/api/photo-ingest/icloud/assets/", {"assets": [self.payload("../secret.JPG")]}, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["errors"], 1)
        self.assertEqual(PhotoAsset.objects.count(), 0)

    def test_reconcile_marks_missing_without_deleting(self):
        payload = self.payload()
        self.client.post("/api/photo-ingest/icloud/assets/", {"assets": [payload]}, format="json", **self.auth)
        response = self.client.post(
            "/api/photo-ingest/icloud/reconcile/", {"seen_source_keys": [], "backlog_count": 0}, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PhotoAsset.objects.get().available)

    def test_unique_strong_trip_match_links_automatically(self):
        collection = Collection.objects.create(user=self.user, name="Philadelphia", start_date=self.captured.date(), end_date=self.captured.date())
        trip = Trip.objects.create(owner=self.user, collection=collection, title="Philadelphia", start_date=self.captured.date(), end_date=self.captured.date())
        trip.profiles.add(self.profile)
        location = Location(user=self.user, name="Philadelphia", latitude=39.9526, longitude=-75.1652)
        location.save(_skip_geocode=True)
        visit = Visit.objects.create(location=location, trip=trip, start_date=self.captured, end_date=self.captured)
        visit.profiles.add(self.profile)
        response = self.client.post("/api/photo-ingest/icloud/assets/", {"assets": [self.payload()]}, format="json", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TripPhotoLink.objects.filter(trip=trip, origin="automatic").exists())

    def test_date_only_match_becomes_suggestion(self):
        collection = Collection.objects.create(user=self.user, name="Possible trip", start_date=self.captured.date(), end_date=self.captured.date())
        trip = Trip.objects.create(owner=self.user, collection=collection, title="Possible trip", start_date=self.captured.date(), end_date=self.captured.date())
        trip.profiles.add(self.profile)
        payload = self.payload()
        payload.pop("latitude")
        payload.pop("longitude")
        self.client.post("/api/photo-ingest/icloud/assets/", {"assets": [payload]}, format="json", **self.auth)
        self.assertTrue(PhotoMatchSuggestion.objects.filter(asset__source=self.source, status="pending").exists())

    def test_live_photo_still_and_video_are_paired(self):
        identifier = "4D16796D-2921-42A1-80EE-123456789ABC"
        still = self.payload("IMG_2000.HEIC")
        still["live_photo_identifier"] = identifier
        video = self.payload("IMG_2000.MOV")
        video["mime_type"] = "video/quicktime"
        video["live_photo_identifier"] = identifier
        response = self.client.post(
            "/api/photo-ingest/icloud/assets/", {"assets": [still, video]}, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 200)
        still_asset = PhotoAsset.objects.get(media_kind="image")
        video_asset = PhotoAsset.objects.get(media_kind="video")
        self.assertEqual(still_asset.live_photo_pair_id, video_asset.id)
        self.assertEqual(video_asset.live_photo_pair_id, still_asset.id)

    def test_preview_is_metadata_stripped_and_path_contained(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as cache_root:
            original = Path(source_root) / "preview.JPG"
            image = Image.new("RGB", (2400, 1800), "#f4c542")
            image.save(original, "JPEG", exif=b"Exif\x00\x00test-private-metadata")
            payload = self.payload("preview.JPG", latitude=None, longitude=None)
            with override_settings(ICLOUD_PHOTOS_MOUNT=source_root, PHOTO_PREVIEW_CACHE=cache_root):
                response = self.client.post(
                    "/api/photo-ingest/icloud/assets/", {"assets": [payload]}, format="json", **self.auth
                )
                self.assertEqual(response.status_code, 200)
                asset = PhotoAsset.objects.get(filename="preview.JPG")
                self.assertEqual(resolve_asset_path(asset), original.resolve())
                preview = ensure_preview(asset)
                self.assertTrue(preview.is_file())
                with Image.open(preview) as generated:
                    self.assertLessEqual(max(generated.size), 1600)
                    self.assertFalse(generated.getexif())

    def test_original_supports_bounded_and_suffix_ranges(self):
        with tempfile.TemporaryDirectory() as source_root:
            original = Path(source_root) / "clip.MP4"
            original.write_bytes(b"0123456789")
            payload = self.payload("clip.MP4", latitude=None, longitude=None)
            payload["mime_type"] = "video/mp4"
            with override_settings(ICLOUD_PHOTOS_MOUNT=source_root):
                self.client.post(
                    "/api/photo-ingest/icloud/assets/", {"assets": [payload]}, format="json", **self.auth
                )
                asset = PhotoAsset.objects.get(filename="clip.MP4")
                self.client.force_authenticate(self.user)
                bounded = self.client.get(f"/api/photo-assets/{asset.id}/original/", HTTP_RANGE="bytes=2-5")
                self.assertEqual(bounded.status_code, 206)
                self.assertEqual(b"".join(bounded.streaming_content), b"2345")
                self.assertEqual(bounded["Content-Range"], "bytes 2-5/10")
                suffix = self.client.get(f"/api/photo-assets/{asset.id}/original/", HTTP_RANGE="bytes=-3")
                self.assertEqual(suffix.status_code, 206)
                self.assertEqual(b"".join(suffix.streaming_content), b"789")
