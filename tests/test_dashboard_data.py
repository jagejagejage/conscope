"""Dashboard-facing SQLite queries and actions."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from conscope_app.dashboard_data import (
    confidence_label,
    dashboard_snapshot,
    delete_event_after_confirmation,
    event_price_history,
    monitoring_status_snapshot,
    observation_is_stale,
    run_manual_mock_check,
)
from conscope_app.database import Database
from conscope_app.monitoring import run_monitoring_pass
from conscope_app.providers.mock import MockProvider


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Database(Path(self.temp_dir.name) / "dashboard.sqlite3")
        self.event = self.database.add_event(
            "The Example Band",
            venue="Sample Arena",
            event_date="2027-04-18T19:30:00-04:00",
            ticket_quantity=2,
            maximum_price=120,
            currency="USD",
            providers=[{
                "provider_key": "mock",
                "display_name": "Mock sample",
                "provider_event_id": "sample-concert-001",
                "event_url": "https://example.invalid/mock/event",
            }],
        )

    def test_dashboard_summary_mock_check_history_and_confidence(self):
        before = dashboard_snapshot(self.database)
        self.assertEqual(before["watched_events"], 1)
        self.assertEqual(before["active_alerts"], 1)
        self.assertEqual(before["events_with_prices"], 0)
        self.assertIsNone(before["latest_success"])

        checked = run_manual_mock_check(self.database, self.event["id"])
        self.assertIsNone(checked.failure)
        self.assertEqual(len(checked.observation_ids), 3)

        history = event_price_history(self.database, self.event["id"])
        self.assertEqual(len(history["listings"]), 3)
        self.assertEqual(history["ranges"], [])
        self.assertTrue(history["listings"][0]["listing_url"].startswith("https://example.invalid/mock/listings/"))

        snapshot = dashboard_snapshot(self.database)
        self.assertEqual(snapshot["events_with_prices"], 1)
        card = snapshot["events"][0]
        self.assertEqual(card["lowest_observation"]["price_per_ticket"], 60.0)
        self.assertEqual(card["lowest_observation"]["pricing_confidence"], "incomplete")
        self.assertFalse(card["latest_observation_stale"])
        self.assertEqual(card["providers"][0]["status_label"], "Mock data · checked successfully")
        self.assertIsNotNone(snapshot["latest_success"])

    def test_pause_resume_changes_active_alerts_and_blocks_manual_checks(self):
        self.database.pause_event(self.event["id"])
        paused = dashboard_snapshot(self.database)
        self.assertEqual(paused["active_alerts"], 0)
        self.assertEqual(paused["events"][0]["providers"][0]["status_label"], "Paused")
        blocked_check = run_manual_mock_check(self.database, self.event["id"])
        self.assertEqual(blocked_check.failure.code, "event_paused")
        self.assertEqual(event_price_history(self.database, self.event["id"])["listings"], [])

        self.database.resume_event(self.event["id"])
        resumed = dashboard_snapshot(self.database)
        self.assertEqual(resumed["active_alerts"], 1)
        checked = run_manual_mock_check(self.database, self.event["id"])
        self.assertIsNone(checked.failure)

    def test_delete_requires_confirmation(self):
        self.assertFalse(delete_event_after_confirmation(self.database, self.event["id"], confirmed=False))
        self.assertIsNotNone(self.database.get_event(self.event["id"]))
        self.assertTrue(delete_event_after_confirmation(self.database, self.event["id"], confirmed=True))
        self.assertIsNone(self.database.get_event(self.event["id"]))

    def test_disabled_live_providers_are_reported_as_disabled(self):
        event = self.database.add_event(
            "Ticketmaster event", maximum_price=300, providers=[{
                "provider_key": "ticketmaster",
                "display_name": "Ticketmaster",
                "provider_event_id": "tm-event-1",
                "event_url": "https://example.invalid/tm-event-1",
            }],
        )
        snapshot = dashboard_snapshot(self.database)
        tm_card = next(card for card in snapshot["events"] if card["event"]["id"] == event["id"])
        self.assertEqual(tm_card["providers"][0]["status_label"], "Disabled · live checks are off; credentials not checked")

    def test_confidence_labels_and_staleness(self):
        self.assertEqual(confidence_label("verified_all_in", "ticketmaster"), "Verified all-in")
        self.assertEqual(confidence_label("estimated", "mock"), "SIMULATED · Estimated price")
        self.assertEqual(confidence_label("incomplete", "mock"), "SIMULATED · Incomplete price")
        self.assertEqual(
            confidence_label("incomplete", "ticketmaster", "aggregate_price_range"),
            "Event-level range · not an individual listing",
        )
        now = datetime(2026, 11, 22, tzinfo=timezone.utc)
        self.assertTrue(observation_is_stale("2026-11-20T00:00:00Z", now=now, stale_after=timedelta(hours=24)))
        self.assertFalse(observation_is_stale("2026-11-21T12:00:00Z", now=now, stale_after=timedelta(hours=24)))

    def test_editing_provider_link_replaces_single_dashboard_link(self):
        run_manual_mock_check(self.database, self.event["id"])
        edited = self.database.update_event(
            self.event["id"],
            maximum_price=140,
            ticket_quantity=3,
            providers=[{
                "provider_key": "ticketmaster",
                "display_name": "Ticketmaster",
                "provider_event_id": "tm-event-2",
                "event_url": "https://example.invalid/tm-event-2",
            }],
        )
        self.assertEqual(edited["maximum_price"], 140)
        self.assertEqual(edited["ticket_quantity"], 3)
        self.assertEqual(len(edited["providers"]), 1)
        self.assertEqual(edited["providers"][0]["provider_key"], "ticketmaster")
        self.assertEqual(edited["providers"][0]["provider_event_id"], "tm-event-2")
        self.assertIsNone(edited["providers"][0]["last_success_at"])
        self.assertEqual(self.database.list_observations(self.event["id"])[0]["source"], "mock")

    def test_monitoring_status_view_reports_provider_schedule_and_simulation_records(self):
        before = monitoring_status_snapshot(self.database)
        self.assertEqual(before["checks"][0]["last_attempt_at"], None)
        self.assertEqual(before["checks"][0]["next_check_at"], None)
        self.assertEqual(before["simulation_alerts"], [])

        run_monitoring_pass(
            self.database, {"mock": MockProvider()}, simulation_mode=True, interval_seconds=60,
        )
        after = monitoring_status_snapshot(self.database)
        self.assertIsNotNone(after["checks"][0]["last_attempt_at"])
        self.assertIsNotNone(after["checks"][0]["next_check_at"])
        self.assertEqual(len(after["simulation_alerts"]), 1)


if __name__ == "__main__":
    unittest.main()
