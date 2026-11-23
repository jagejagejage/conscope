"""Deterministic sample provider for local UI and integration development."""

from .base import ProviderFailure, ProviderResult
from .models import PriceObservation, PricingConfidence, ProviderEvent, current_timestamp


class MockProvider:
    key = "mock"
    display_name = "Sample ticket data"

    EVENTS = (
        ProviderEvent(
            source=key,
            event_id="sample-concert-001",
            name="The Example Band",
            venue="Sample Arena",
            event_date="2027-04-18T19:30:00-04:00",
            city="New York",
            region="NY",
            url="https://example.invalid/mock/events/sample-concert-001",
        ),
        ProviderEvent(
            source=key,
            event_id="sample-game-002",
            name="Sample City vs. Demo United",
            venue="Demo Stadium",
            event_date="2027-05-02T15:00:00-04:00",
            city="New York",
            region="NY",
            url="https://example.invalid/mock/events/sample-game-002",
        ),
    )

    def discover_events(self, query: str) -> ProviderResult[ProviderEvent]:
        needle = (query or "").strip().casefold()
        if not needle:
            return ProviderResult(self.EVENTS)
        results = tuple(
            event for event in self.EVENTS
            if needle in event.name.casefold() or needle in event.venue.casefold() or needle in (event.city or "").casefold()
        )
        return ProviderResult(results)

    def get_prices(self, event: ProviderEvent) -> ProviderResult[PriceObservation]:
        if event.source != self.key or event.event_id not in {item.event_id for item in self.EVENTS}:
            return ProviderResult(failure=ProviderFailure("unknown_mock_event", "The requested sample event is not available."))
        timestamp = current_timestamp()
        return ProviderResult((
            PriceObservation(
                source=self.key,
                event_id=event.event_id,
                listing_id=f"{event.event_id}-listing-001",
                url=f"https://example.invalid/mock/listings/{event.event_id}-listing-001",
                currency="USD",
                available_quantity=2,
                price_per_ticket=85.00,
                fees_per_ticket=15.00,
                total_per_ticket=100.00,
                observed_at=timestamp,
                pricing_confidence=PricingConfidence.VERIFIED_ALL_IN,
                section="Lower Level",
                row="12",
            ),
            PriceObservation(
                source=self.key,
                event_id=event.event_id,
                listing_id=f"{event.event_id}-listing-002",
                url=f"https://example.invalid/mock/listings/{event.event_id}-listing-002",
                currency="USD",
                available_quantity=4,
                price_per_ticket=72.50,
                fees_per_ticket=12.50,
                total_per_ticket=85.00,
                observed_at=timestamp,
                pricing_confidence=PricingConfidence.ESTIMATED,
                section="Upper Level",
                row="7",
            ),
            PriceObservation(
                source=self.key,
                event_id=event.event_id,
                listing_id=f"{event.event_id}-listing-003",
                url=f"https://example.invalid/mock/listings/{event.event_id}-listing-003",
                currency="USD",
                available_quantity=None,
                price_per_ticket=60.00,
                observed_at=timestamp,
                pricing_confidence=PricingConfidence.INCOMPLETE,
                section="Balcony",
            ),
        ))
