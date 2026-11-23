"""Isolated tests for the local SQLite persistence layer (stdlib unittest)."""

import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from conscope_app.database import CURRENT_SCHEMA_VERSION, Database, default_data_directory
from conscope_app.providers.models import DiscoveredEvent, EventImage


class LocalDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.db = Database(self.root / "test.sqlite3")

    def create_event(self, db=None, **changes):
        db = db or self.db
        fields = {
            "name": "Example concert",
            "venue": "Example Arena",
            "event_date": "2027-06-01T19:30:00-04:00",
            "ticket_quantity": 2,
            "maximum_price": 175.0,
            "currency": "USD",
            "providers": [{
                "provider_key": "sample",
                "display_name": "Sample Tickets",
                "provider_event_id": "evt-42",
                "event_url": "https://example.invalid/events/42",
            }],
        }
        fields.update(changes)
        return db.add_event(**fields)

    def test_event_crud_provider_and_alert_settings(self):
        event = self.create_event()
        event_id = event["id"]
        self.assertEqual(event["ticket_quantity"], 2)
        self.assertEqual(event["maximum_price"], 175.0)
        self.assertEqual(event["currency"], "USD")
        self.assertEqual(event["alert_enabled"], 1)
        self.assertEqual(event["allow_estimated_prices"], 0)
        self.assertEqual(event["providers"][0]["provider_key"], "sample")
        self.assertEqual(event["providers"][0]["provider_event_id"], "evt-42")

        updated = self.db.update_event(
            event_id,
            name="Updated concert",
            ticket_quantity=3,
            maximum_price=220,
            currency="cad",
            alert_enabled=False,
            allow_estimated_prices=True,
            providers=[{
                "provider_key": "sample",
                "display_name": "Sample Tickets",
                "provider_event_id": "evt-42",
                "event_url": "https://example.invalid/events/42",
            }],
        )
        self.assertEqual(updated["name"], "Updated concert")
        self.assertEqual(updated["ticket_quantity"], 3)
        self.assertEqual(updated["maximum_price"], 220.0)
        self.assertEqual(updated["currency"], "CAD")
        self.assertEqual(updated["alert_enabled"], 0)
        self.assertEqual(updated["allow_estimated_prices"], 1)
        self.assertEqual(len(updated["providers"]), 1)

        self.assertTrue(self.db.delete_event(event_id))
        self.assertIsNone(self.db.get_event(event_id))
        self.assertFalse(self.db.delete_event(event_id))

    def test_discovered_event_metadata_provider_url_and_duplicate_guard(self):
        discovered = DiscoveredEvent(
            source="ticketmaster", provider_id="tm-discovered-1", name="Live Example",
            event_date="2027-08-09T20:00:00+00:00", venue="City Hall",
            city="Boston", region="MA", url="https://ticketmaster.example/event/1",
            images=(EventImage("https://images.example/event.jpg", width=1200, height=800),),
        )
        saved = self.db.add_discovered_event(discovered, ticket_quantity=3, maximum_price=145)
        self.assertEqual(saved["city"], "Boston")
        self.assertEqual(saved["region"], "MA")
        self.assertEqual(saved["images"][0]["url"], "https://images.example/event.jpg")
        self.assertEqual(saved["providers"][0]["provider_event_id"], "tm-discovered-1")
        self.assertEqual(saved["providers"][0]["event_url"], discovered.url)
        self.assertEqual(saved["ticket_quantity"], 3)
        self.assertEqual(saved["maximum_price"], 145)
        self.assertEqual(saved["alert_enabled"], 0)
        self.assertEqual(self.db.list_observations(saved["id"]), [])
        with self.assertRaisesRegex(ValueError, "already in your watchlist"):
            self.db.add_discovered_event(discovered, ticket_quantity=2, maximum_price=100)

    def test_pause_resume_and_list_filtering(self):
        event = self.create_event()
        event_id = event["id"]
        self.assertTrue(self.db.list_events(include_paused=False))

        self.assertEqual(self.db.pause_event(event_id)["is_paused"], 1)
        self.assertEqual(self.db.list_events(include_paused=False), [])
        self.assertEqual(self.db.list_events()[0]["id"], event_id)
        self.assertEqual(self.db.resume_event(event_id)["is_paused"], 0)
        self.assertEqual(self.db.list_events(include_paused=False)[0]["id"], event_id)

    def test_observations_status_and_dedupe_have_foreign_keys_and_valid_confidence(self):
        event = self.create_event()
        provider = event["providers"][0]
        self.db.update_check_status(
            provider["event_provider_id"],
            attempted_at="2026-11-22T12:00:00Z",
            succeeded_at="2026-11-22T12:00:00Z",
            next_check_at="2026-11-22T13:00:00Z",
        )
        observation_id = self.db.add_observation(
            event["id"],
            event_provider_id=provider["event_provider_id"],
            listing_id="listing-1",
            listing_url="https://example.invalid/listing/1",
            price_per_ticket=150,
            fees_per_ticket=25,
            total_per_ticket=175,
            currency="USD",
            available_quantity=2,
            pricing_confidence="verified_all_in",
            observed_at="2026-11-22T12:00:00Z",
        )
        self.assertEqual(self.db.list_observations(event["id"])[0]["id"], observation_id)
        self.assertTrue(self.db.record_notification(event["id"], "threshold:listing-1", observation_id=observation_id))
        self.assertFalse(self.db.record_notification(event["id"], "threshold:listing-1", observation_id=observation_id))
        self.db.update_notification_status(event["id"], "threshold:listing-1", "sent")

        with sqlite3.connect(self.db.path) as conn:
            self.assertEqual(conn.execute("SELECT status FROM notification_deduplication").fetchone()[0], "sent")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO notification_deduplication (tracked_event_id, deduplication_key) VALUES (?, ?)",
                    (event["id"], "threshold:listing-1"),
                )
        with self.assertRaisesRegex(ValueError, "pricing_confidence"):
            self.db.add_observation(
                event["id"], price_per_ticket=20, currency="USD",
                observed_at="now", pricing_confidence="unknown",
            )

    def test_persistence_after_reopening(self):
        path = self.root / "persist.sqlite3"
        first = Database(path)
        event = self.create_event(db=first)
        first.add_observation(
            event["id"], price_per_ticket=80, currency="USD", observed_at="2026-11-22T12:00:00Z",
            pricing_confidence="estimated", available_quantity=4,
        )

        reopened = Database(path)
        self.assertEqual(reopened.get_event(event["id"])["name"], "Example concert")
        self.assertEqual(reopened.list_observations(event["id"])[0]["pricing_confidence"], "estimated")

    def test_schema_migrates_from_v1_to_current(self):
        path = self.root / "migration.sqlite3"
        v1 = Database.__new__(Database)
        v1.path = path
        v1.migrate(target_version=1)
        self.assertEqual(v1.schema_version, 1)
        with sqlite3.connect(path) as conn:
            conn.execute(
                "INSERT INTO tracked_events (id, name, ticket_quantity, maximum_price, currency) VALUES (?, ?, ?, ?, ?)",
                ("legacy-event", "Legacy event", 1, 100, "USD"),
            )

        upgraded = Database(path)
        self.assertEqual(upgraded.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(upgraded.get_event("legacy-event")["alert_enabled"], 1)
        self.assertEqual(upgraded.get_event("legacy-event")["allow_estimated_prices"], 0)
        self.assertEqual(upgraded.get_event("legacy-event")["images"], [])

    def test_v2_observations_gain_provider_source_during_v3_migration(self):
        path = self.root / "source-migration.sqlite3"
        legacy = Database.__new__(Database)
        legacy.path = path
        legacy.migrate(target_version=1)
        with sqlite3.connect(path) as conn:
            conn.execute(
                "INSERT INTO tracked_events (id, name, ticket_quantity, maximum_price, currency) VALUES (?, ?, ?, ?, ?)",
                ("legacy-event", "Legacy event", 1, 100, "USD"),
            )
            conn.execute("INSERT INTO providers (provider_key, display_name) VALUES ('seatgeek', 'SeatGeek')")
            provider_id = conn.execute("SELECT id FROM providers WHERE provider_key = 'seatgeek'").fetchone()[0]
            conn.execute(
                "INSERT INTO event_providers (tracked_event_id, provider_id, provider_event_id) VALUES (?, ?, ?)",
                ("legacy-event", provider_id, "source-event-1"),
            )
            event_provider_id = conn.execute("SELECT id FROM event_providers").fetchone()[0]
            conn.execute("INSERT INTO check_status (event_provider_id) VALUES (?)", (event_provider_id,))
            conn.execute(
                "INSERT INTO price_observations (tracked_event_id, event_provider_id, price_per_ticket, currency, pricing_confidence, observed_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("legacy-event", event_provider_id, 55, "USD", "incomplete", "2026-11-22T12:00:00Z"),
            )
        legacy.migrate(target_version=2)

        upgraded = Database(path)
        self.assertEqual(upgraded.schema_version, CURRENT_SCHEMA_VERSION)
        self.assertEqual(upgraded.list_observations("legacy-event")[0]["source"], "seatgeek")

    def test_configurable_and_platform_default_data_directories(self):
        override = self.root / "override"
        with patch.dict(os.environ, {"CONSCOPE_DATA_DIR": str(override)}):
            self.assertEqual(default_data_directory(), override)

        env = {key: value for key, value in os.environ.items() if key != "CONSCOPE_DATA_DIR"}
        env["LOCALAPPDATA"] = str(self.root / "local")
        with patch.dict(os.environ, env, clear=True), patch("conscope_app.database.sys.platform", "win32"):
            self.assertEqual(default_data_directory(), self.root / "local" / "ConScope")

        configured = Database(data_dir=self.root / "configured")
        self.assertEqual(configured.path, self.root / "configured" / "conscope.sqlite3")


if __name__ == "__main__":
    unittest.main()
