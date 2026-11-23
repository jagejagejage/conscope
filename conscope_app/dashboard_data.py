"""Dashboard-facing queries and actions backed by the local SQLite repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .database import Database
from .providers.base import ProviderFailure
from .providers.mock import MockProvider
from .providers.storage import StoredResult, check_and_store


def confidence_label(confidence: str, source: str, observation_type: str = "ticket_listing") -> str:
    if observation_type == "aggregate_price_range":
        label = "Event-level range · not an individual listing"
    else:
        label = {
            "verified_all_in": "Verified all-in",
            "estimated": "Estimated price",
            "incomplete": "Incomplete price",
        }.get(str(confidence), "Unknown pricing")
    return f"SIMULATED · {label}" if source == "mock" else label


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def observation_is_stale(observed_at: str | None, *, now: datetime | None = None, stale_after: timedelta = timedelta(hours=24)) -> bool:
    observed = _parse_time(observed_at)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return observed is None or now - observed > stale_after


def _provider_status(event: dict[str, Any], provider: dict[str, Any], now: datetime, stale_after: timedelta) -> str:
    key = provider["provider_key"]
    if event["is_paused"]:
        return "Paused"
    if key == "mock":
        if provider.get("last_error"):
            return f"Mock check failed: {provider['last_error']}"
        if not provider.get("last_success_at"):
            return "Mock data · not checked yet"
        if observation_is_stale(provider["last_success_at"], now=now, stale_after=stale_after):
            return "Mock data · last check is stale"
        return "Mock data · checked successfully"
    if key == "seatgeek":
        return "Disabled · access and endpoint not verified; credentials not checked"
    if key == "ticketmaster":
        return "Disabled · live checks are off; credentials not checked"
    return "Disabled · provider adapter unavailable"


def dashboard_snapshot(
    database: Database,
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(hours=24),
) -> dict[str, Any]:
    """Load dashboard summary and per-event price/check data without live calls."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    event_cards = []
    active_alerts = 0
    latest_success = None

    for event in database.list_events():
        observations = database.list_observations(event["id"])
        ranges = database.list_aggregate_price_ranges(event["id"])
        providers = event.get("providers", [])
        if event["alert_enabled"] and not event["is_paused"]:
            active_alerts += 1
        successes = [_parse_time(provider.get("last_success_at")) for provider in providers]
        successes = [success for success in successes if success]
        event_last_success = max(successes) if successes else None
        if event_last_success and (latest_success is None or event_last_success > latest_success):
            latest_success = event_last_success

        compatible = [item for item in observations if item["currency"] == event["currency"]]
        lowest = min(compatible, key=lambda item: item["price_per_ticket"]) if compatible else None
        provider_cards = []
        for provider in providers:
            provider_cards.append({
                **provider,
                "status_label": _provider_status(event, provider, now, stale_after),
            })
        observation_times = [item["observed_at"] for item in observations]
        parsed_observation_times = [(parsed, original) for original in observation_times if (parsed := _parse_time(original))]
        latest_observation_at = max(parsed_observation_times, key=lambda item: item[0])[1] if parsed_observation_times else None
        event_cards.append({
            "event": event,
            "providers": provider_cards,
            "observations": observations,
            "aggregate_ranges": ranges,
            "lowest_observation": lowest,
            "latest_success": event_last_success.isoformat() if event_last_success else None,
            "latest_observation_stale": observation_is_stale(latest_observation_at, now=now, stale_after=stale_after) if observations else None,
        })

    return {
        "watched_events": len(event_cards),
        "active_alerts": active_alerts,
        "events_with_prices": sum(card["lowest_observation"] is not None for card in event_cards),
        "latest_success": latest_success.isoformat() if latest_success else None,
        "events": event_cards,
    }


def event_price_history(database: Database, event_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return listing history and aggregate ranges in separate collections."""
    if database.get_event(event_id) is None:
        return {"listings": [], "ranges": []}
    return {
        "listings": database.list_observations(event_id),
        "ranges": database.list_aggregate_price_ranges(event_id),
    }


def run_manual_mock_check(database: Database, event_id: str) -> StoredResult:
    event = database.get_event(event_id)
    if event is None:
        return StoredResult((), ProviderFailure("event_not_found", "This tracked event no longer exists."))
    if event["is_paused"]:
        return StoredResult((), ProviderFailure("event_paused", "Resume this event before checking sample prices."))
    return check_and_store(database, MockProvider(), event)


def delete_event_after_confirmation(database: Database, event_id: str, *, confirmed: bool) -> bool:
    """Delete only when the UI has explicit confirmation."""
    if not confirmed:
        return False
    return database.delete_event(event_id)
