"""Offline email notification service tests; never contact Resend."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from conscope_app.database import Database
from conscope_app.notifications import NotificationService, ResendEmailProvider
from conscope_app.notifications.models import AlertEmailContext, DeliveryFailure, DeliveryResult, EmailMessage
from conscope_app.notifications.sqlite_repository import SQLiteNotificationRepository
from conscope_app.notifications.templates import render_ticket_alert, sample_alert_context


NOW = datetime(2027, 4, 18, 18, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self, *results):
        self.results = list(results)
        self.sent = []

    def send(self, message, *, idempotency_key):
        self.sent.append((message, idempotency_key))
        return self.results.pop(0) if self.results else DeliveryResult(provider_message_id="accepted")


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.response


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db = Database(Path(self.temp_dir.name) / "notify.sqlite3")
        self.event = self.db.add_event(
            "Example show", ticket_quantity=2, maximum_price=120, currency="USD",
            providers=[{"provider_key": "sample", "display_name": "Sample", "provider_event_id": "show-1", "event_url": "https://example.invalid/event"}],
        )
        self.provider_link = self.event["providers"][0]
        self.alert_counter = 0

    def create_alert(self, *, simulation=False):
        self.alert_counter += 1
        if self.alert_counter > 1:
            self.event = self.db.add_event(
                f"Example show {self.alert_counter}", ticket_quantity=2, maximum_price=120, currency="USD",
                providers=[{"provider_key": "sample", "display_name": "Sample", "provider_event_id": f"show-{self.alert_counter}", "event_url": "https://example.invalid/event"}],
            )
            self.provider_link = self.event["providers"][0]
        observation_id = self.db.add_observation(
            self.event["id"], event_provider_id=self.provider_link["event_provider_id"],
            listing_id="listing-123", listing_url="https://tickets.example.invalid/listing/123",
            price_per_ticket=90, fees_per_ticket=6.5, total_per_ticket=96.5,
            currency="USD", available_quantity=4, pricing_confidence="verified_all_in",
            observed_at=NOW.isoformat(), source="sample",
        )
        record = self.db.record_monitor_alert(
            self.event["id"], event_provider_id=self.provider_link["event_provider_id"],
            observation_id=observation_id, simulation_only=simulation,
            total_per_ticket=96.5, currency="USD", available_quantity=4,
        )
        return record["id"]

    def service(self, provider, **kwargs):
        return NotificationService(SQLiteNotificationRepository(self.db), provider, sender="ConScope <alerts@example.invalid>", **kwargs)

    def test_template_has_required_details_and_price_change_notice(self):
        rendered = render_ticket_alert(sample_alert_context())
        for value in ("Example Band", "USD 96.50", "USD 120.00", "2", "2027-04-18", "https://tickets.example.invalid/listings/sample-123", "Prices and availability"):
            self.assertIn(value, rendered.text)
        self.assertIn("<html", rendered.html)
        self.assertIn("Open original ticket listing", rendered.html)

    def test_template_escapes_content_and_rejects_bad_url_and_simulation(self):
        context = sample_alert_context()
        from dataclasses import replace
        safe = render_ticket_alert(replace(context, event_name="<script>bad</script>"))
        self.assertNotIn("<script>", safe.html)
        with self.assertRaises(ValueError):
            render_ticket_alert(replace(context, listing_url="javascript:alert(1)"))
        with self.assertRaisesRegex(ValueError, "Simulation-only"):
            render_ticket_alert(replace(context, simulation_only=True))

    def test_resend_success_sends_header_and_never_logs_or_returns_key(self):
        session = FakeSession(FakeResponse(200, {"id": "email_123"}))
        provider = ResendEmailProvider("secret-value", session=session)
        result = provider.send(EmailMessage("a", "b", "s", "h", "t"), idempotency_key="stable-key")
        self.assertTrue(result.ok)
        self.assertEqual(session.calls[0][1]["headers"]["Idempotency-Key"], "stable-key")
        self.assertEqual(session.calls[0][1]["headers"]["Authorization"], "Bearer secret-value")
        self.assertNotIn("secret-value", repr(result))

    def test_resend_classifies_rate_limit_permanent_and_timeout(self):
        rate = ResendEmailProvider("x", session=FakeSession(FakeResponse(429, {"name": "rate_limit"}, {"Retry-After": "17"})))
        rate_result = rate.send(EmailMessage("a", "b", "s", "h", "t"), idempotency_key="k")
        self.assertTrue(rate_result.failure.retryable)
        self.assertEqual(rate_result.failure.retry_after_seconds, 17)
        permanent = ResendEmailProvider("x", session=FakeSession(FakeResponse(422, {"name": "validation_error"})))
        self.assertFalse(permanent.send(EmailMessage("a", "b", "s", "h", "t"), idempotency_key="k").failure.retryable)
        timeout = ResendEmailProvider("x", session=FakeSession(error=requests.exceptions.Timeout()))
        timeout_result = timeout.send(EmailMessage("a", "b", "s", "h", "t"), idempotency_key="k")
        self.assertTrue(timeout_result.failure.retryable)
        self.assertTrue(timeout_result.failure.delivery_uncertain)

    def test_resend_missing_credentials_does_not_call_session(self):
        session = FakeSession(FakeResponse(200, {"id": "x"}))
        with patch.dict("os.environ", {}, clear=True):
            result = ResendEmailProvider(session=session).send(EmailMessage("a", "b", "s", "h", "t"), idempotency_key="k")
        self.assertEqual(result.failure.code, "missing_credentials")
        self.assertEqual(session.calls, [])

    def test_enqueue_is_idempotent_and_simulation_isolated(self):
        alert_id = self.create_alert()
        service = self.service(FakeProvider())
        first = service.enqueue_alert(alert_id, " User@example.com ")
        second = service.enqueue_alert(alert_id, "user@example.com")
        self.assertEqual(first, second)
        self.assertEqual(len(self.db.list_email_notification_deliveries()), 1)
        simulation_id = self.create_alert(simulation=True)
        with self.assertRaisesRegex(ValueError, "Simulation-only"):
            service.enqueue_alert(simulation_id, "user@example.com")
        self.assertEqual(len(self.db.list_email_notification_deliveries()), 1)

    def test_delivery_success_and_repeat_pass_do_not_duplicate(self):
        alert_id = self.create_alert()
        fake = FakeProvider(DeliveryResult(provider_message_id="resend-id"))
        service = self.service(fake)
        service.enqueue_alert(alert_id, "user@example.com")
        result = service.deliver_pending(now=NOW)
        self.assertEqual(result.sent, 1)
        self.assertEqual(service.deliver_pending(now=NOW + timedelta(hours=1)).sent, 0)
        self.assertEqual(len(fake.sent), 1)
        row = self.db.list_email_notification_deliveries()[0]
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["provider_message_id"], "resend-id")

    def test_rate_limit_uses_bounded_backoff_and_stable_idempotency_key(self):
        alert_id = self.create_alert()
        fake = FakeProvider(
            DeliveryResult(failure=DeliveryFailure("rate_limit", "limited", retryable=True, retry_after_seconds=45)),
            DeliveryResult(provider_message_id="after-retry"),
        )
        service = self.service(fake, base_backoff_seconds=30)
        service.enqueue_alert(alert_id, "user@example.com")
        first = service.deliver_pending(now=NOW)
        self.assertEqual(first.retryable, 1)
        self.assertEqual(service.deliver_pending(now=NOW + timedelta(seconds=44)).sent, 0)
        self.assertEqual(service.deliver_pending(now=NOW + timedelta(seconds=45)).sent, 1)
        self.assertEqual(fake.sent[0][1], fake.sent[1][1])

    def test_permanent_error_and_max_attempts_stop_retrying(self):
        alert_id = self.create_alert()
        fake = FakeProvider(*[
            DeliveryResult(failure=DeliveryFailure("temporary", "down", retryable=True)) for _ in range(2)
        ])
        service = self.service(fake, max_attempts=2, base_backoff_seconds=0, max_backoff_seconds=0)
        service.enqueue_alert(alert_id, "user@example.com")
        self.assertEqual(service.deliver_pending(now=NOW).retryable, 1)
        self.assertEqual(service.deliver_pending(now=NOW).failed, 1)
        self.assertEqual(service.deliver_pending(now=NOW).sent, 0)
        self.assertEqual(len(fake.sent), 2)

    def test_uncertain_delivery_reuses_key_then_stops_after_idempotency_horizon(self):
        alert_id = self.create_alert()
        timeout = DeliveryResult(failure=DeliveryFailure("timeout", "uncertain", retryable=True, delivery_uncertain=True))
        fake = FakeProvider(timeout, timeout)
        service = self.service(fake, base_backoff_seconds=0, max_backoff_seconds=0)
        service.enqueue_alert(alert_id, "user@example.com")
        service.deliver_pending(now=NOW)
        before_horizon = NOW + timedelta(hours=22)
        self.assertEqual(service.deliver_pending(now=before_horizon).retryable, 1)
        after_horizon = NOW + timedelta(hours=24)
        self.assertEqual(service.deliver_pending(now=after_horizon).sent, 0)
        self.assertEqual(self.db.list_email_notification_deliveries()[0]["status"], "failed")
        self.assertEqual(len(fake.sent), 2)

    def test_preview_cli_is_offline_and_confirmation_mismatch_sends_nothing(self):
        from scripts.email_notifications import main
        self.assertEqual(main(["preview", "--format", "text"]), 0)
        with patch("scripts.email_notifications.ResendEmailProvider.send") as send:
            self.assertEqual(main(["test-email", "--to", "a@example.com", "--confirm-to", "b@example.com"]), 2)
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
