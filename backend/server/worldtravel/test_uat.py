import json
import os
import tempfile
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from integrations.models import ImmichIntegration, StravaToken, WandererIntegration
from locationtracking.models import LocationDevice, LocationSample, PrivacyZone
from photoindex.models import PhotoImportSource
from users.models import APIKey
from worldtravel.models import (
    BallparkVisit,
    SkylightConnection,
    SkylightTripSuggestion,
    TravelProfile,
    Trip,
)


UAT_ENV = {
    "UAT_MODE": "true",
    "UAT_OWNER_PASSWORD": "owner-test-password",
    "UAT_MEMBER_PASSWORD": "member-test-password",
    "UAT_OUTSIDER_PASSWORD": "outsider-test-password",
    "UAT_EMPTY_PASSWORD": "empty-test-password",
}


class PrepareUATCommandTests(TestCase):
    def _run(self, *extra):
        handle, manifest_path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        stdout = StringIO()
        with patch.dict(os.environ, UAT_ENV, clear=False):
            call_command(
                "prepare_uat",
                "--manifest",
                manifest_path,
                "--scenario",
                "core",
                "--anchor-date",
                "2026-08-15",
                *extra,
                stdout=stdout,
            )
        with open(manifest_path, encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        os.unlink(manifest_path)
        return manifest, stdout.getvalue()

    def test_refuses_to_run_outside_explicit_uat_mode(self):
        with patch.dict(os.environ, {"UAT_MODE": "false"}, clear=False):
            with self.assertRaisesMessage(CommandError, "UAT_MODE=true"):
                call_command("prepare_uat", "--manifest", "ignored.json", "--scenario", "core")

    def test_creates_accounts_and_sanitized_core_manifest(self):
        manifest, output = self._run("--reset")

        User = get_user_model()
        for role in ("owner", "member", "outsider", "empty"):
            user = User.objects.get(username=f"uat-{role}")
            self.assertEqual(user.email, f"uat-{role}@example.invalid")
            self.assertTrue(user.check_password(UAT_ENV[f"UAT_{role.upper()}_PASSWORD"]))

        owner = User.objects.get(username="uat-owner")
        self.assertEqual(
            set(TravelProfile.objects.filter(owner=owner).values_list("name", flat=True)),
            {"Spencer", "Ashley", "Joint"},
        )
        self.assertGreaterEqual(Trip.objects.filter(owner=owner, title__startswith="[UAT]").count(), 9)
        self.assertEqual(SkylightTripSuggestion.objects.filter(connection__owner=owner).count(), 3)
        self.assertEqual(BallparkVisit.objects.filter(profile__owner=owner).count(), 3)
        self.assertFalse(manifest["security"]["contains_passwords"])
        serialized = json.dumps(manifest)
        self.assertNotIn("owner-test-password", serialized)
        self.assertNotIn("token_hash", serialized)
        self.assertNotIn("C:\\\\Users", serialized)
        self.assertNotIn("Generated one-time", output)

    def test_is_idempotent_and_reset_restores_deterministic_counts(self):
        first, _ = self._run("--reset")
        second, _ = self._run()
        third, _ = self._run("--reset")

        self.assertEqual(first["expected"], second["expected"])
        self.assertEqual(first["expected"], third["expected"])
        self.assertEqual(get_user_model().objects.filter(username="uat-owner").count(), 1)

    def test_stress_scenario_reaches_declared_load_counts(self):
        handle, manifest_path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        with patch.dict(os.environ, UAT_ENV, clear=False):
            call_command(
                "prepare_uat",
                "--manifest",
                manifest_path,
                "--scenario",
                "stress",
                "--anchor-date",
                "2026-08-15",
                stdout=StringIO(),
            )
        with open(manifest_path, encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        os.unlink(manifest_path)

        self.assertEqual(manifest["expected"]["uat_trip_count"], 100)
        self.assertEqual(manifest["expected"]["uat_place_count"], 500)
        self.assertEqual(manifest["expected"]["photo_asset_count"], 1000)

    def test_scrubs_cloned_credentials_paths_and_exact_telemetry(self):
        User = get_user_model()
        source_owner = User.objects.create_user(
            username="real-owner", email="person@example.com", password="real-password"
        )
        profile = TravelProfile.objects.create(owner=source_owner, name="Spencer", is_default=True)
        APIKey.generate(source_owner, "secret key")
        Session.objects.create(
            session_key="uat-secret-session",
            session_data="secret",
            expire_date=timezone.make_aware(datetime(2030, 1, 1)),
        )
        ImmichIntegration.objects.create(user=source_owner, server_url="https://photos.example.com", api_key="secret")
        StravaToken.objects.create(user=source_owner, access_token="secret", refresh_token="secret", expires_at=1)
        WandererIntegration.objects.create(user=source_owner, server_url="https://trails.example.com", username="person", token="secret")
        SkylightConnection.objects.create(owner=source_owner, encrypted_credentials="secret", frame_id="real-frame")
        device = LocationDevice.objects.create(
            owner=source_owner,
            profile=profile,
            name="Real phone",
            auth_username="real-device",
            token_hash="secret",
            owntracks_username="person",
            device_identifier="phone",
        )
        PrivacyZone.objects.create(owner=source_owner, name="Home", center="POINT(-77 38)", is_home=True)
        LocationSample.objects.create(
            device=device,
            captured_at="2026-08-01T12:00:00Z",
            point="POINT(-77 38)",
            source_fingerprint="secret-sample",
        )
        PhotoImportSource.objects.create(
            owner=source_owner,
            profile=profile,
            root_alias="icloud-photos",
            auth_username="real-photo-source",
            token_hash="secret",
            name="C:\\Users\\person\\iCloudPhotos",
        )

        handle, manifest_path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        with patch.dict(os.environ, UAT_ENV, clear=False):
            call_command(
                "prepare_uat",
                "--manifest",
                manifest_path,
                "--scenario",
                "core",
                "--owner-username",
                "real-owner",
            )
        os.unlink(manifest_path)

        owner = User.objects.get(username="uat-owner")
        self.assertEqual(owner.pk, source_owner.pk)
        self.assertEqual(owner.email, "uat-owner@example.invalid")
        self.assertFalse(Session.objects.exists())
        self.assertFalse(APIKey.objects.exists())
        self.assertFalse(ImmichIntegration.objects.exists())
        self.assertFalse(StravaToken.objects.exists())
        self.assertFalse(WandererIntegration.objects.exists())
        self.assertEqual(SkylightConnection.objects.filter(owner=owner).count(), 1)
        self.assertEqual(SkylightConnection.objects.get(owner=owner).frame_id, "uat-frame")
        self.assertFalse(LocationSample.objects.exists())
        self.assertFalse(PrivacyZone.objects.exists())
        self.assertFalse(PhotoImportSource.objects.filter(auth_username="real-photo-source").exists())
