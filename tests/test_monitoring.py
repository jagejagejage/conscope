"""Offline behavior tests for monitoring and threshold alert cycles."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from conscope_app.database import Database
from conscope_app.monitoring import run_monitoring_pass
from conscope_app.providers.base import ProviderFailure, ProviderResult
from conscope_app.providers.models import PriceObservation, PricingConfidence
from conscope_app.providers.mock import MockProvider
from conscope_app.scheduler import run_local_scheduler


NOW = datetime(2027, 4, 1, 12, 0, tzinfo=timezone.utc)
NOW_TEXT = NOW.isoformat()


def observation(
    *,
    source="sample",
    event_id="provider-event",
    total=100,
    quantity=2,
    currency="USD",
    confidence=PricingConfidence.VERIFIED_ALL_IN,
    observed_at=NOW_TEXT,
    observation_type="ticket_listing",
):
    return PriceObservation(
        source=source,
        event_id=event_id,
        listing_id="listing-1" if observation_type == "ticket_listing" else None,
        currency=currency,
        observed_at=observed_at,
        pricing_confidence=confidence,
        price_per_ticket=total if observation_type == "ticket_listing" else None,
        total_per_ticket=total if observation_type == "ticket_listing" and confidence == PricingConfidence.VERIFIED_ALL_IN else None,
        available_quantity=quantity if observation_type == "ticket_listing" else None,
        observation_type=observation_type,
        range_min_price=20 if observation_type == "aggregate_price_range" else None,
        range_max_price=total if observation_type == "aggregate_price_range" else None,
        range_label="standard" if observation_type == "aggregate_price_range" else None,
    )


class SequenceProvider:
    def __init__(self, key, results):
        self.key = key
        self.display_name = key.title()
        self.results = list(results)
        self.calls = 0

    def get_prices(self, event):
        self.calls += 1
        if self.results:
            result = self.results.pop(0)
            self.last_result = result
            return result
        return self.last_result


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Database(Path(self.temp_dir.name) / "monitor.sqlite3")

    def add_event(self, *, key="sample", provider_event_id="provider-event", currency="USD", quantity=2, maximum=100, paused=False):
        event = self.database.add_event(
            "Test event", ticket_quantity=quantity, maximum_price=maximum, currency=currency,
            alert_enabled=True,
            providers=[{
                "provider_key": key,
                "display_name": key.title(),
                "provider_event_id": provider_event_id,
                "event_url": "https://example.invalid/event",
            }],
        )
        if paused:
            self.database.pause_event(event["id"])
            event = self.database.get_event(event["id"])
        return event

    def run_pass(self, event, provider, *, simulation_mode=False, interval_seconds=None):
        return run_monitoring_pass(
            self.database, {provider.key: provider}, simulation_mode=simulation_mode,
            interval_seconds=interval_seconds, now=NOW,
        )

    def test_verified_all_in_threshold_and_sufficient_quantity_create_simulation_record(self):
        event = self.add_event(key="mock", provider_event_id="sample-concert-001")
        provider = MockProvider()
        result = run_monitoring_pass(self.database, {"mock": provider}, simulation_mode=True)
        self.assertEqual(len(result.alerts), 1)
        self.assertTrue(result.alerts[0]["simulation_only"])
        self.assertEqual(result.alerts[0]["total_per_ticket"], 100)
        rows = self.database.list_monitor_alert_records(simulation_only=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_name"], event["name"])
        self.assertEqual(self.database.list_observations(event["id"])[0]["total_per_ticket"], 100)
        link = event["providers"][0]
        observation_id = self.database.list_observations(event["id"])[0]["id"]
        with sqlite3.connect(self.database.path) as conn, self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO monitor_alert_records (tracked_event_id, event_provider_id, observation_id, cycle_number, simulation_only, total_per_ticket, currency, available_quantity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event["id"], link["event_provider_id"], observation_id, 1, 1, 100, "USD", 2),
            )

    def test_price_above_threshold_and_insufficient_quantity_do_not_alert(self):
        cases = ((100.01, 2), (99.00, 1))
        for total, quantity in cases:
            with self.subTest(total=total, quantity=quantity):
                event = self.add_event()
                provider = SequenceProvider("sample", [ProviderResult((observation(total=total, quantity=quantity),))])
                result = self.run_pass(event, provider)
                self.assertEqual(result.alerts, ())
                self.assertEqual(self.database.list_monitor_alert_records(), [])

    def test_currency_mismatch_and_non_verified_pricing_do_not_alert(self):
        cases = (
            observation(currency="CAD"),
            observation(confidence=PricingConfidence.ESTIMATED),
            observation(confidence=PricingConfidence.INCOMPLETE),
        )
        for item in cases:
            with self.subTest(currency=item.currency, confidence=item.pricing_confidence):
                event = self.add_event()
                provider = SequenceProvider("sample", [ProviderResult((item,))])
                result = self.run_pass(event, provider)
                self.assertEqual(result.alerts, ())

    def test_mock_prices_never_create_customer_alert_records_without_simulation_mode(self):
        event = self.add_event(key="mock", provider_event_id="sample-concert-001")
        result = run_monitoring_pass(self.database, {"mock": MockProvider()})
        self.assertEqual(result.alerts, ())
        self.assertEqual(self.database.list_monitor_alert_records(), [])
        self.assertEqual(len(self.database.list_observations(event["id"])), 3)

    def test_ticketmaster_aggregate_ranges_and_seatgeek_are_disabled(self):
        for key in ("ticketmaster", "seatgeek"):
            event = self.add_event(key=key)
            provider = SequenceProvider(key, [ProviderResult((observation(
                source=key, event_id="provider-event", observation_type="aggregate_price_range",
                confidence=PricingConfidence.INCOMPLETE,
            ),))])
            result = self.run_pass(event, provider, simulation_mode=True)
            self.assertEqual(result.alerts, ())
            self.assertEqual(provider.calls, 0)
            self.assertEqual(result.checks[0].skipped, True)

    def test_repeat_passes_do_not_duplicate_alert_until_successful_clear_rearms(self):
        event = self.add_event()
        provider = SequenceProvider("sample", [
            ProviderResult((observation(total=90),)),
            ProviderResult((observation(total=90),)),
            ProviderResult((observation(total=120),)),
            ProviderResult((observation(total=90),)),
        ])
        counts = []
        for _ in range(4):
            result = self.run_pass(event, provider)
            counts.append(len(result.alerts))
        rows = self.database.list_monitor_alert_records()
        self.assertEqual(counts, [1, 0, 0, 1])
        self.assertEqual([row["cycle_number"] for row in reversed(rows)], [1, 2])

    def test_older_clear_pass_cannot_rearm_after_a_newer_qualifying_alert(self):
        event = self.add_event()
        started = datetime.now(timezone.utc)
        provider = SequenceProvider("sample", [ProviderResult((observation(observed_at=started.isoformat()),))])
        first = run_monitoring_pass(self.database, {"sample": provider}, now=started)
        self.assertEqual(len(first.alerts), 1)

        self.database.rearm_monitor_alert(
            event["id"], checked_at=(started - timedelta(seconds=10)).isoformat(),
        )
        later = started + timedelta(seconds=1)
        provider.results.append(ProviderResult((observation(observed_at=later.isoformat()),)))
        second = run_monitoring_pass(self.database, {"sample": provider}, now=later)
        self.assertEqual(second.alerts, ())
        self.assertEqual(len(self.database.list_monitor_alert_records()), 1)

    def test_paused_event_is_not_checked_until_resumed(self):
        event = self.add_event(paused=True)
        provider = SequenceProvider("sample", [ProviderResult((observation(),))])
        paused_result = self.run_pass(event, provider)
        self.assertEqual(provider.calls, 0)
        self.assertEqual(paused_result.checks, ())
        self.database.resume_event(event["id"])
        resumed_result = self.run_pass(event, provider)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(resumed_result.alerts), 1)

    def test_failure_preserves_history_and_does_not_rearm_or_claim_zero_inventory(self):
        event = self.add_event()
        provider = SequenceProvider("sample", [
            ProviderResult((observation(),)),
            ProviderResult(failure=ProviderFailure("rate_limited", "rate limited", retryable=True, retry_after_seconds=30)),
            ProviderResult((observation(),)),
        ])
        first = self.run_pass(event, provider)
        self.assertEqual(len(first.alerts), 1)
        initial_history = len(self.database.list_observations(event["id"]))
        failed = self.run_pass(event, provider)
        self.assertEqual(failed.failure_count, 1)
        self.assertEqual(len(self.database.list_observations(event["id"])), initial_history)
        status = self.database.get_event(event["id"])["providers"][0]
        self.assertEqual(status["last_error"], "rate limited")
        self.assertIsNotNone(status["last_success_at"])
        recovered = self.run_pass(event, provider)
        self.assertEqual(recovered.alerts, ())
        self.assertEqual(len(self.database.list_monitor_alert_records()), 1)

    def test_retry_after_is_persisted_and_checks_wait_until_due(self):
        event = self.add_event()
        provider = SequenceProvider("sample", [
            ProviderResult(failure=ProviderFailure("rate_limited", "rate limited", retryable=True, retry_after_seconds=120)),
            ProviderResult((observation(),)),
        ])
        first = run_monitoring_pass(self.database, {"sample": provider}, interval_seconds=60, now=NOW)
        self.assertEqual(first.failure_count, 1)
        status = self.database.get_event(event["id"])["providers"][0]
        self.assertEqual(status["next_check_at"], "2027-04-01T12:02:00+00:00")

        too_soon = run_monitoring_pass(self.database, {"sample": provider}, now=NOW)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(too_soon.checks[0].skipped, True)

        due = run_monitoring_pass(self.database, {"sample": provider}, now=NOW.replace(minute=2))
        self.assertEqual(provider.calls, 2)
        self.assertEqual(due.checked_count, 1)

    def test_offline_and_missing_credentials_failures_preserve_successful_history(self):
        for code in ("offline", "missing_credentials"):
            with self.subTest(code=code):
                event_db = Database(Path(self.temp_dir.name) / f"{code}.sqlite3")
                event = event_db.add_event(
                    "Test event", ticket_quantity=2, maximum_price=100, currency="USD",
                    alert_enabled=True,
                    providers=[{
                        "provider_key": "sample", "display_name": "Sample",
                        "provider_event_id": f"{code}-event", "event_url": "https://example.invalid/event",
                    }],
                )
                first_listing = observation(event_id=f"{code}-event", total=120)
                provider = SequenceProvider("sample", [
                    ProviderResult((first_listing,)),
                    ProviderResult(failure=ProviderFailure(code, f"{code} error", retryable=True)),
                ])
                run_monitoring_pass(event_db, {"sample": provider}, now=NOW)
                previous_count = len(event_db.list_observations(event["id"]))
                failed = run_monitoring_pass(event_db, {"sample": provider}, now=NOW)
                self.assertEqual(failed.failure_count, 1)
                self.assertEqual(len(event_db.list_observations(event["id"])), previous_count)
                status = event_db.get_event(event["id"])["providers"][0]
                self.assertEqual(status["last_error"], f"{code} error")
                self.assertIsNotNone(status["last_success_at"])

    def test_stale_or_unknown_inventory_does_not_alert_or_rearm(self):
        event = self.add_event()
        stale = observation(observed_at="2026-01-01T00:00:00Z")
        provider = SequenceProvider("sample", [
            ProviderResult((observation(),)),
            ProviderResult((stale,)),
            ProviderResult((observation(),)),
        ])
        self.assertEqual(len(self.run_pass(event, provider).alerts), 1)
        self.assertEqual(self.run_pass(event, provider).alerts, ())
        self.assertEqual(self.run_pass(event, provider).alerts, ())
        self.assertEqual(len(self.database.list_monitor_alert_records()), 1)

    def test_scheduler_repeat_runs_are_deduplicated_and_set_next_check(self):
        event = self.add_event(key="mock", provider_event_id="sample-concert-001")

        class StopAfterTwoWaits:
            def __init__(self):
                self.wait_count = 0

            def is_set(self):
                return self.wait_count >= 2

            def wait(self, timeout):
                self.wait_count += 1
                return self.wait_count >= 2

        run_local_scheduler(
            self.database, {"mock": MockProvider()}, interval_seconds=60,
            simulation_mode=True, stop_event=StopAfterTwoWaits(),
        )
        self.assertEqual(len(self.database.list_monitor_alert_records(simulation_only=True)), 1)
        provider = self.database.get_event(event["id"])["providers"][0]
        self.assertIsNotNone(provider["last_attempt_at"])
        self.assertIsNotNone(provider["next_check_at"])


if __name__ == "__main__":
    unittest.main()
