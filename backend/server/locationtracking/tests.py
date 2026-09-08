import base64
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from adventures.models import Collection, Location

from worldtravel.models import TravelProfile, Trip

from .adapters import NormalizedLocationSample
from .models import LocationSample, PrivacyEvent, PrivacyZone, StayCandidate
from .services import create_device, process_device_samples, store_normalized_sample


class LocationTrackingTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="spencer", password="test-password")
        self.profile = TravelProfile.objects.create(owner=self.user, name="Spencer", color="#F5C84C")
        self.device, self.token = create_device(owner=self.user, profile=self.profile, name="Spencer iPhone")
        raw = f"{self.device.auth_username}:{self.token}".encode()
        self.basic = f"Basic {base64.b64encode(raw).decode()}"

    def payload(self, *, timestamp=None, latitude=39.9526, longitude=-75.1652):
        return {
            "_type": "location",
            "tst": int((timestamp or timezone.now()).timestamp()),
            "lat": latitude,
            "lon": longitude,
            "acc": 20,
            "batt": 82,
            "topic": f"owntracks/{self.device.owntracks_username}/{self.device.device_identifier}",
        }

    @patch("locationtracking.views.schedule_processing")
    def test_ingestion_is_authenticated_and_idempotent(self, schedule):
        url = reverse("owntracks-ingest")
        payload = self.payload()
        response = self.client.post(url, payload, format="json", HTTP_AUTHORIZATION=self.basic)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.client.post(url, payload, format="json", HTTP_AUTHORIZATION=self.basic)
        self.assertEqual(LocationSample.objects.count(), 1)
        schedule.assert_called_once()

    def test_paused_device_is_rejected(self):
        self.device.enabled = False
        self.device.save(update_fields=["enabled"])
        response = self.client.post(
            reverse("owntracks-ingest"), self.payload(), format="json", HTTP_AUTHORIZATION=self.basic
        )
        self.assertEqual(response.status_code, 401)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_auth_failure_at)

    @patch("locationtracking.views.schedule_processing")
    def test_home_coordinate_is_discarded(self, schedule):
        PrivacyZone.objects.create(
            owner=self.user, name="Home", center=Point(-75.1652, 39.9526, srid=4326), radius_m=500, is_home=True
        )
        response = self.client.post(
            reverse("owntracks-ingest"), self.payload(), format="json", HTTP_AUTHORIZATION=self.basic
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LocationSample.objects.count(), 0)
        self.assertEqual(PrivacyEvent.objects.count(), 1)
        schedule.assert_not_called()

    def test_stay_detection_requires_dwell_time(self):
        started = timezone.now() - timedelta(hours=2)
        for index, minute in enumerate((0, 10, 25)):
            captured = started + timedelta(minutes=minute)
            normalized = NormalizedLocationSample(
                source="owntracks",
                external_device_id=self.device.device_identifier,
                captured_at=captured,
                latitude=39.9526 + index * 0.00002,
                longitude=-75.1652 + index * 0.00002,
                accuracy_m=20,
                altitude_m=None,
                velocity_mps=None,
                motion_state="stationary",
                event_type="location",
                battery_percent=80,
                battery_state="1",
                source_fingerprint=f"sample-{index}",
            )
            store_normalized_sample(self.device, normalized)
        result = process_device_samples(self.device.pk)
        self.assertEqual(result["stays"], 1)
        stay = StayCandidate.objects.get()
        self.assertEqual(stay.sample_count, 3)
        self.assertGreaterEqual(stay.confidence, 0.5)

    def test_raw_samples_never_appear_as_places(self):
        normalized = NormalizedLocationSample(
            source="owntracks", external_device_id=self.device.device_identifier,
            captured_at=timezone.now(), latitude=39.95, longitude=-75.16, accuracy_m=20,
            altitude_m=None, velocity_mps=None, motion_state="", event_type="location",
            battery_percent=None, battery_state="", source_fingerprint="private-raw-sample",
        )
        store_normalized_sample(self.device, normalized)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/places/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_place_visit_accepts_shared_household_profiles(self):
        member = get_user_model().objects.create_user(username="ashley", email="ashley@example.test", password="test-password")
        shared_profile = TravelProfile.objects.create(owner=member, name="Ashley", color="#8B5CF6")
        shared_profile.shared_with.add(self.user)
        place = Location.objects.create(user=self.user, name="Shared-profile place", latitude=43.65, longitude=-79.38)
        place.profiles.set([self.profile, shared_profile])
        collection = Collection.objects.create(
            user=self.user,
            name="Shared-profile trip",
            start_date=timezone.datetime(2026, 10, 1).date(),
            end_date=timezone.datetime(2026, 10, 3).date(),
        )
        trip = Trip.objects.create(
            owner=self.user,
            collection=collection,
            title="Shared-profile trip",
            start_date=collection.start_date,
            end_date=collection.end_date,
        )
        trip.profiles.set([self.profile, shared_profile])

        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            f"/api/places/{place.pk}/visits/",
            {
                "start_date": "2026-10-01T09:00:00Z",
                "end_date": "2026-10-03T18:00:00Z",
                "profiles": [str(self.profile.pk), str(shared_profile.pk)],
                "trip": str(trip.pk),
                "notes": "[UAT-A] place visit initial",
                "source": "manual",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertCountEqual(response.json()["profiles"], [str(self.profile.pk), str(shared_profile.pk)])
        self.assertEqual(response.json()["trip"], str(trip.pk))
