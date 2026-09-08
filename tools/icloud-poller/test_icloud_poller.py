import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import subprocess
import json


MODULE_PATH = Path(__file__).with_name("icloud_poller.py")
SPEC = importlib.util.spec_from_file_location("touchgrass_icloud_poller", MODULE_PATH)
poller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(poller)


class PollerTests(unittest.TestCase):
    def database(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE files (
                relative_path TEXT PRIMARY KEY, source_key TEXT NOT NULL,
                size_bytes INTEGER NOT NULL, mtime REAL NOT NULL,
                stable_count INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'discovered', priority INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0, next_retry REAL NOT NULL DEFAULT 0,
                last_seen_scan TEXT, error TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        return db

    def test_two_scans_are_required_before_metadata_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "IMG_0001.JPG").write_bytes(b"placeholder")
            db = self.database()
            poller.reconcile_local(db, root)
            self.assertEqual(db.execute("SELECT stable_count FROM files").fetchone()[0], 0)
            poller.reconcile_local(db, root)
            self.assertEqual(db.execute("SELECT stable_count FROM files").fetchone()[0], 1)

    def test_new_media_is_prioritized_after_historical_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "old.JPG").write_bytes(b"old")
            db = self.database()
            poller.reconcile_local(db, root)
            (root / "new.HEIC").write_bytes(b"new")
            poller.reconcile_local(db, root)
            priorities = dict(db.execute("SELECT relative_path,priority FROM files"))
            self.assertEqual(priorities["old.JPG"], 0)
            self.assertEqual(priorities["new.HEIC"], 100)

    def test_live_photo_identifier_and_timezone_are_preserved(self):
        row = {
            "relative_path": "IMG_1000.HEIC",
            "source_key": "a" * 64,
            "size_bytes": 10,
            "mtime": 1_700_000_000,
        }
        record = poller.record_from_metadata(row, {
            "DateTimeOriginal": "2026:08:27 09:15:00",
            "OffsetTimeOriginal": "-04:00",
            "ContentIdentifier": "live-photo-id",
        })
        self.assertEqual(record["timezone_offset"], "-04:00")
        self.assertEqual(record["live_photo_identifier"], "live-photo-id")
        self.assertTrue(record["captured_at"].endswith("+00:00"))

    def test_single_instance_lock_rejects_a_second_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "poller.lock"
            with mock.patch.object(poller, "LOCK_PATH", lock_path), mock.patch.object(poller, "APP_DIR", Path(directory)):
                first = poller.acquire_instance_lock()
                self.assertIsNotNone(first)
                self.assertIsNone(poller.acquire_instance_lock())
                first.close()

    def test_install_falls_back_to_user_startup_folder_without_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "TouchGrass iCloud Poller.cmd"
            denied = subprocess.CalledProcessError(1, ["schtasks"])
            with mock.patch.object(poller, "STARTUP_LAUNCHER", launcher), \
                 mock.patch.object(poller.subprocess, "run", side_effect=denied), \
                 mock.patch.object(poller, "start_background_worker", return_value=1234):
                poller.install_task(SimpleNamespace())
            self.assertTrue(launcher.is_file())
            self.assertIn("icloud_poller.py", launcher.read_text(encoding="utf-8"))

    def test_credential_rotation_replaces_the_saved_dpapi_value(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config = {
                "ingest_url": "http://localhost:8016/api/photo-ingest/icloud/assets/",
                "username": "icloud-test",
                "token_dpapi": "encrypted-old-token",
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(poller, "CONFIG_PATH", config_path), \
                 mock.patch.object(poller, "load_config", return_value=config), \
                 mock.patch.object(poller, "unprotect_token", return_value="old-token"), \
                 mock.patch.object(poller, "protect_token", return_value="encrypted-new-token"), \
                 mock.patch.object(poller, "request_json", return_value={"token": "n" * 43}) as request:
                poller.rotate_credential()
            request.assert_called_once_with(
                "http://localhost:8016/api/photo-ingest/icloud/rotate-token/",
                "icloud-test",
                "old-token",
                {},
            )
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["token_dpapi"], "encrypted-new-token")

    def test_historical_hydration_stops_before_the_drive_is_full(self):
        usage = SimpleNamespace(free=4 * 1024 ** 3)
        with mock.patch.object(poller.shutil, "disk_usage", return_value=usage):
            allowed, free_gb, minimum_gb = poller.hydration_capacity(Path("C:/photos"), {"minimum_free_gb": 10})
        self.assertFalse(allowed)
        self.assertEqual(free_gb, 4)
        self.assertEqual(minimum_gb, 10)


if __name__ == "__main__":
    unittest.main()
