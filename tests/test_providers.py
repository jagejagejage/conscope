"""Offline tests for provider normalization, failure handling, and SQLite storage."""

from pathlib import Path
import tempfile
import unittest
import requests
import json

from conscope_app.database import Database
from conscope_app.providers.base import ProviderFailure, ProviderResult
from conscope_app.providers.mock import MockProvider
from conscope_app.providers.models import PriceObservation, PricingConfidence, ProviderEvent, normalize_currency
from conscope_app.providers.seatgeek import SeatGeekProvider
from conscope_app.providers.storage import check_and_store, store_observations
from conscope_app.providers.ticketmaster import TicketmasterProvider, search_ticketmaster_events


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, headers=None, json_error=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.json_error = json_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        if self.error:
            raise self.error
        return self.response


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db = Database(Path(self.temp_dir.name) / "provider.sqlite3")
        self.event = self.db.add_event(
            "Example concert",
            venue="Example Arena",
            ticket_quantity=2,
            maximum_price=200,
            currency="USD",
            providers=[{
                "provider_key": "mock",
                "display_name": "Sample ticket data",
                "provider_event_id": "sample-concert-001",
                "event_url": "https://example.invalid/mock/event",
            }],
        )

    def test_currency_validation(self):
        self.assertEqual(normalize_currency(" usd "), "USD")
        for invalid in (None, "US", "USDD", "€UR", ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_currency(invalid)

    def test_seatgeek_normalizes_estimated_incomplete_and_verified_prices(self):
        session = FakeSession(FakeResponse({"listings": [
            {"id": 11, "url": "https://tickets.invalid/11", "currency": "USD", "price": 80, "quantity": 2,
             "fees": {"per_ticket": 10}, "total_price": 90},
            {"id": 12, "url": "https://tickets.invalid/12", "currency": "USD", "price": 65, "quantity": 1},
        ]}))
        provider = SeatGeekProvider("test-client-id", session=session, access_approved=True)
        result = provider.get_prices(ProviderEvent("seatgeek", "sg-1", "Example"))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 2)
        first, second = result.items
        self.assertEqual(first.source, "seatgeek")
        self.assertEqual(first.event_id, "sg-1")
        self.assertEqual(first.listing_id, "11")
        self.assertEqual(first.url, "https://tickets.invalid/11")
        self.assertEqual(first.available_quantity, 2)
        self.assertEqual(first.currency, "USD")
        self.assertEqual(first.fees_per_ticket, 10)
        self.assertEqual(first.total_per_ticket, 90)
        self.assertEqual(first.pricing_confidence, PricingConfidence.ESTIMATED)
        self.assertEqual(second.pricing_confidence, PricingConfidence.INCOMPLETE)
        self.assertIsNone(second.fees_per_ticket)
        self.assertIsNone(second.total_per_ticket)
        self.assertEqual(second.available_quantity, 1)
        self.assertEqual(session.calls[0][1]["client_id"], "test-client-id")

        unverified = SeatGeekProvider("client", session=FakeSession(FakeResponse({"listings": [
            {"id": "all-in", "currency": "USD", "price": 80, "total_price": 100},
        ]})), access_approved=True)
        unverified_result = unverified.get_prices(ProviderEvent("seatgeek", "sg-2", "Example"))
        self.assertEqual(unverified_result.items[0].pricing_confidence, PricingConfidence.ESTIMATED)

    def test_seatgeek_missing_currency_or_invalid_quantity_is_reported_as_malformed(self):
        provider = SeatGeekProvider("client", session=FakeSession(FakeResponse({"listings": [
            {"id": "missing-currency", "price": 20},
            {"id": "bad-quantity", "currency": "USD", "price": 20, "quantity": 0},
        ]})), access_approved=True)
        result = provider.get_prices(ProviderEvent("seatgeek", "sg-1", "Example"))
        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "malformed_listing")
        self.assertEqual(result.items, ())

    def test_missing_credentials_and_unsupported_discovery_are_explicit(self):
        unapproved = SeatGeekProvider("client", session=FakeSession())
        self.assertEqual(unapproved.get_prices(ProviderEvent("seatgeek", "sg-1", "Example")).failure.code, "access_unverified")
        provider = SeatGeekProvider(client_id="", session=FakeSession(), access_approved=True)
        missing = provider.get_prices(ProviderEvent("seatgeek", "sg-1", "Example"))
        self.assertEqual(missing.failure.code, "missing_credentials")
        unsupported = SeatGeekProvider("client").discover_events("artist")
        self.assertEqual(unsupported.failure.code, "unsupported_operation")

    def test_http_failures_return_structured_results_without_network(self):
        event = ProviderEvent("ticketmaster", "tm-1", "Example")
        cases = (
            (requests.exceptions.Timeout(), "timeout", True),
            (requests.exceptions.ConnectionError(), "offline", True),
        )
        for error, expected_code, retryable in cases:
            with self.subTest(expected_code=expected_code):
                provider = TicketmasterProvider("key", session=FakeSession(error=error))
                result = provider.get_prices(event)
                self.assertEqual(result.failure.code, expected_code)
                self.assertEqual(result.failure.retryable, retryable)

        provider = TicketmasterProvider("key", session=FakeSession(FakeResponse(
            {"message": "slow down"}, status_code=429, headers={"Retry-After": "17"},
        )))
        limited = provider.get_prices(event)
        self.assertEqual(limited.failure.code, "rate_limited")
        self.assertEqual(limited.failure.retry_after_seconds, 17)

        provider = TicketmasterProvider("key", session=FakeSession(FakeResponse(json_error=ValueError("bad json"))))
        malformed = provider.discover_events("band")
        self.assertEqual(malformed.failure.code, "malformed_response")

        missing_key = TicketmasterProvider(api_key="", session=FakeSession())
        self.assertEqual(missing_key.discover_events("band").failure.code, "missing_credentials")

    def test_ticketmaster_discovery_and_aggregate_ranges_do_not_claim_listings(self):
        discovery = FakeSession(FakeResponse({"_embedded": {"events": [{
            "id": "tm-1",
            "name": "Example Show",
            "url": "https://tickets.invalid/tm-1",
            "dates": {"start": {"dateTime": "2027-01-02T19:00:00Z"}},
            "_embedded": {"venues": [{"name": "Main Hall", "city": {"name": "New York"}, "state": {"stateCode": "NY"}}]},
        }]}}))
        provider = TicketmasterProvider("key", session=discovery)
        events = provider.discover_events("Example Show")
        self.assertTrue(events.ok)
        self.assertEqual(events.items[0].event_id, "tm-1")
        self.assertEqual(events.items[0].venue, "Main Hall")

        provider.session = FakeSession(FakeResponse({"priceRanges": [{
            "type": "standard", "currency": "USD", "min": 50, "max": 140,
        }]}))
        ranges = provider.get_prices(events.items[0])
        self.assertTrue(ranges.ok)
        item = ranges.items[0]
        self.assertEqual(item.observation_type, "aggregate_price_range")
        self.assertIsNone(item.price_per_ticket)
        self.assertIsNone(item.total_per_ticket)
        self.assertIsNone(item.available_quantity)
        self.assertIsNone(item.listing_id)
        self.assertEqual(item.range_min_price, 50)
        self.assertEqual(item.range_max_price, 140)
        self.assertEqual(item.pricing_confidence, PricingConfidence.INCOMPLETE)

    def test_ticketmaster_search_uses_fixture_and_normalizes_event_catalog(self):
        fixture = Path(__file__).parent / "fixtures" / "ticketmaster" / "search_success.json"
        session = FakeSession(FakeResponse(json.loads(fixture.read_text())))
        result = search_ticketmaster_events(
            "Example Show", city="New York", event_date="2027-01-02",
            api_key="fixture-key", session=session,
        )
        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 2)
        event = result.items[0]
        self.assertEqual((event.name, event.provider_id), ("Example Show", "tm-1"))
        self.assertEqual(event.event_date, "2027-01-02T19:00:00+00:00")
        self.assertEqual((event.venue, event.city, event.region), ("Main Hall", "New York", "NY"))
        self.assertEqual(event.url, "https://tickets.example/tm-1")
        self.assertEqual(event.images[0].url, "https://images.example/poster.jpg")
        self.assertEqual((event.images[0].width, event.images[0].height), (1024, 576))
        self.assertIsNone(result.items[1].event_date)
        self.assertEqual(session.calls[0][1]["city"], "New York")
        self.assertEqual(session.calls[0][1]["startDateTime"], "2027-01-02T00:00:00Z")
        self.assertEqual(session.calls[0][1]["endDateTime"], "2027-01-03T00:00:00Z")
        self.assertEqual(session.calls[0][1]["apikey"], "fixture-key")

    def test_ticketmaster_search_empty_malformed_credentials_timeout_and_rate_limit(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "ticketmaster"
        empty = TicketmasterProvider("fixture-key", session=FakeSession(FakeResponse(
            json.loads((fixture_dir / "search_empty.json").read_text()),
        ))).search_events("No match")
        self.assertTrue(empty.ok)
        self.assertEqual(empty.items, ())

        malformed = TicketmasterProvider("fixture-key", session=FakeSession(FakeResponse(
            json.loads((fixture_dir / "search_malformed.json").read_text()),
        ))).search_events("bad payload")
        self.assertEqual(malformed.failure.code, "malformed_response")

        missing = TicketmasterProvider(api_key="", session=FakeSession()).search_events("band")
        self.assertEqual(missing.failure.code, "missing_credentials")

        timeout = TicketmasterProvider("fixture-key", session=FakeSession(error=requests.exceptions.Timeout())).search_events("band")
        self.assertEqual(timeout.failure.code, "timeout")

        limited = TicketmasterProvider("fixture-key", session=FakeSession(FakeResponse(
            {"fault": "rate limited"}, status_code=429, headers={"Retry-After": "17"},
        ))).search_events("band")
        self.assertEqual(limited.failure.code, "rate_limited")
        self.assertEqual(limited.failure.retry_after_seconds, 17)

    def test_fake_ticketmaster_search_result_can_be_tracked_without_live_prices(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "ticketmaster"
        result = search_ticketmaster_events(
            "Example Show", api_key="offline-key",
            session=FakeSession(FakeResponse(json.loads((fixture_dir / "search_success.json").read_text()))),
        )
        self.assertTrue(result.ok)
        tracked = self.db.add_discovered_event(result.items[0], ticket_quantity=2, maximum_price=125)
        self.assertEqual(tracked["providers"][0]["provider_event_id"], "tm-1")
        self.assertEqual(tracked["providers"][0]["event_url"], result.items[0].url)
        self.assertEqual(tracked["images"][0]["url"], result.items[0].images[0].url)
        self.assertEqual(self.db.list_observations(tracked["id"]), [])

    def test_mock_provider_is_deterministic_and_persists_both_observation_kinds(self):
        provider = MockProvider()
        discovered = provider.discover_events("example")
        self.assertEqual(len(discovered.items), 1)
        event = discovered.items[0]
        first = provider.get_prices(event)
        second = provider.get_prices(event)
        self.assertEqual([item.listing_id for item in first.items], [item.listing_id for item in second.items])
        self.assertEqual([item.price_per_ticket for item in first.items], [item.price_per_ticket for item in second.items])

        stored = check_and_store(self.db, provider, self.event)
        self.assertIsNone(stored.failure)
        self.assertEqual(len(stored.observation_ids), 3)
        observations = self.db.list_observations(self.event["id"])
        self.assertEqual(len(observations), 3)
        self.assertEqual(observations[0]["source"], "mock")
        self.assertEqual(observations[0]["listing_url"], first.items[0].url)
        self.assertEqual(observations[0]["available_quantity"], 2)
        check = self.db.get_event(self.event["id"])["providers"][0]
        self.assertIsNotNone(check["last_success_at"])

    def test_aggregate_price_range_persistence_is_separate_from_listing_history(self):
        ticketmaster_event = self.db.add_event(
            "TM Example", maximum_price=200, providers=[{
                "provider_key": "ticketmaster", "display_name": "Ticketmaster",
                "provider_event_id": "tm-42", "event_url": "https://example.invalid/tm-42",
            }],
        )
        link = ticketmaster_event["providers"][0]
        observation = PriceObservation(
            source="ticketmaster", event_id="tm-42", currency="USD",
            observed_at="2026-11-22T12:00:00Z", pricing_confidence=PricingConfidence.INCOMPLETE,
            observation_type="aggregate_price_range", range_min_price=40,
            range_max_price=120, range_label="standard", url="https://example.invalid/tm-42",
        )
        stored = store_observations(
            self.db, ticketmaster_event["id"], link["event_provider_id"], "tm-42", [observation],
        )
        self.assertEqual(len(stored.observation_ids), 1)
        self.assertEqual(self.db.list_observations(ticketmaster_event["id"]), [])
        ranges = self.db.list_aggregate_price_ranges(ticketmaster_event["id"])
        self.assertEqual(ranges[0]["range_min_price"], 40)
        self.assertEqual(ranges[0]["range_max_price"], 120)
        self.assertEqual(ranges[0]["pricing_confidence"], "incomplete")

    def test_provider_failure_retains_prices_and_records_error(self):
        provider = MockProvider()
        check_and_store(self.db, provider, self.event)
        previous_count = len(self.db.list_observations(self.event["id"]))

        class FailedProvider:
            key = "mock"

            def get_prices(self, event):
                return ProviderResult(failure=ProviderFailure("offline", "offline", retryable=True))

        result = check_and_store(self.db, FailedProvider(), self.event)
        self.assertEqual(result.failure.code, "offline")
        self.assertEqual(len(self.db.list_observations(self.event["id"])), previous_count)
        status = self.db.get_event(self.event["id"])["providers"][0]
        self.assertEqual(status["last_error"], "offline")
        self.assertIsNotNone(status["last_success_at"])

    def test_invalid_observation_constraints(self):
        base = dict(source="mock", event_id="evt", currency="USD", observed_at="now", pricing_confidence="incomplete")
        for updates in (
            {"price_per_ticket": 0},
            {"price_per_ticket": 10, "available_quantity": 0},
            {"price_per_ticket": 10, "currency": "US"},
            {"price_per_ticket": 10, "pricing_confidence": "verified_all_in"},
        ):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                PriceObservation(**{**base, **updates})


if __name__ == "__main__":
    unittest.main()
