"""Persist normalized provider results through the local SQLite repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from ..database import Database
from .base import ProviderFailure, TicketProvider
from .models import PriceObservation


@dataclass(frozen=True)
class StoredResult:
    observation_ids: tuple[int, ...]
    failure: ProviderFailure | None = None


def store_observations(
    database: Database,
    tracked_event_id: str,
    event_provider_id: int,
    provider_event_id: str,
    observations: Iterable[PriceObservation],
    *,
    failure: ProviderFailure | None = None,
) -> StoredResult:
    """Store valid observations; individual DB errors remain visible to callers."""
    saved = []
    for observation in observations:
        if observation.observation_type == "aggregate_price_range":
            saved.append(database.add_aggregate_price_range(
                tracked_event_id,
                event_provider_id=event_provider_id,
                source=observation.source,
                provider_event_id=provider_event_id,
                range_label=observation.range_label or "Price range",
                minimum_price=observation.range_min_price,
                maximum_price=observation.range_max_price,
                currency=observation.currency,
                observed_at=observation.observed_at,
                event_url=observation.url,
            ))
        else:
            saved.append(database.add_observation(
                tracked_event_id,
                event_provider_id=event_provider_id,
                source=observation.source,
                listing_id=observation.listing_id,
                listing_url=observation.url,
                section=observation.section,
                row_label=observation.row,
                price_per_ticket=observation.price_per_ticket,
                fees_per_ticket=observation.fees_per_ticket,
                total_per_ticket=observation.total_per_ticket,
                currency=observation.currency,
                available_quantity=observation.available_quantity,
                pricing_confidence=observation.pricing_confidence.value,
                observed_at=observation.observed_at,
            ))
    return StoredResult(tuple(saved), failure)


def check_and_store(database: Database, provider: TicketProvider, tracked_event: dict) -> StoredResult:
    """Check one configured provider event and preserve its last known prices on failure."""
    links = tracked_event.get("providers", [])
    link = next((row for row in links if row.get("provider_key") == provider.key), None)
    if link is None:
        return StoredResult((), ProviderFailure("provider_not_configured", "This event has no matching provider link."))
    event = _to_provider_event(tracked_event, provider.key, link)
    attempted_at = datetime.now(timezone.utc).isoformat()
    result = provider.get_prices(event)
    stored = store_observations(
        database,
        tracked_event["id"],
        link["event_provider_id"],
        link["provider_event_id"],
        result.items,
        failure=result.failure,
    )
    database.update_check_status(
        link["event_provider_id"],
        attempted_at=attempted_at,
        succeeded_at=datetime.now(timezone.utc).isoformat() if result.ok else None,
        error=result.failure.message if result.failure else None,
    )
    return stored


def _to_provider_event(tracked_event: dict, provider_key: str, link: dict):
    from .models import ProviderEvent
    return ProviderEvent(
        source=provider_key,
        event_id=link["provider_event_id"],
        name=tracked_event["name"],
        venue=tracked_event.get("venue") or "",
        event_date=tracked_event.get("event_date"),
        url=link.get("event_url"),
    )
