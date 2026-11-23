"""One-pass ticket monitoring and threshold-alert evaluation.

This module contains no scheduler, web server, or notification delivery code so a
single pass can run from a CLI, task runner, or hosted scheduled job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Mapping

from .database import Database
from .providers.base import ProviderFailure, ProviderRequestError, ProviderResult, TicketProvider
from .providers.models import PriceObservation, PricingConfidence, ProviderEvent
from .providers.storage import store_observations


DISABLED_PRICE_PROVIDERS = frozenset({"ticketmaster", "seatgeek"})


@dataclass(frozen=True)
class ProviderCheck:
    event_id: str
    event_name: str
    provider_key: str
    succeeded: bool
    saved_observations: int = 0
    error: str | None = None
    skipped: bool = False


@dataclass(frozen=True)
class MonitorPassResult:
    checks: tuple[ProviderCheck, ...]
    alerts: tuple[dict[str, Any], ...]

    @property
    def checked_count(self) -> int:
        return sum(check.succeeded for check in self.checks)

    @property
    def failure_count(self) -> int:
        return sum(not check.succeeded and not check.skipped for check in self.checks)


def _as_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _fresh(observation: PriceObservation, *, now: datetime, stale_after: timedelta) -> bool:
    observed = _as_utc(observation.observed_at)
    return observed is not None and timedelta(0) <= now - observed <= stale_after


def _candidate(observation: PriceObservation, event: dict[str, Any], *, now: datetime, stale_after: timedelta) -> bool:
    return (
        observation.observation_type == "ticket_listing"
        and observation.pricing_confidence is PricingConfidence.VERIFIED_ALL_IN
        and observation.total_per_ticket is not None
        and observation.available_quantity is not None
        and observation.available_quantity >= event["ticket_quantity"]
        and observation.currency == event["currency"]
        and observation.total_per_ticket <= event["maximum_price"]
        and _fresh(observation, now=now, stale_after=stale_after)
    )


def _inventory_is_comparable(observations: tuple[PriceObservation, ...], *, event: dict[str, Any], now: datetime, stale_after: timedelta) -> bool:
    """Return false when a successful response still leaves inventory ambiguous."""
    for observation in observations:
        if not _fresh(observation, now=now, stale_after=stale_after):
            return False
        if observation.observation_type != "ticket_listing":
            return False
        if (
            observation.pricing_confidence is not PricingConfidence.VERIFIED_ALL_IN
            or observation.total_per_ticket is None
            or observation.available_quantity is None
            or observation.currency != event["currency"]
        ):
            return False
    return True


def run_monitoring_pass(
    database: Database,
    providers: Mapping[str, TicketProvider],
    *,
    simulation_mode: bool = False,
    interval_seconds: float | None = None,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(hours=24),
) -> MonitorPassResult:
    """Check each supported provider once for each unpaused tracked event.

    Mock observations can create explicitly simulation-only ledger records only
    when ``simulation_mode`` is true. This function never sends emails.
    """
    if interval_seconds is not None and interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if stale_after.total_seconds() <= 0:
        raise ValueError("stale_after must be positive")
    fixed_now = now is not None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    attempted_at = now.isoformat()
    scheduled_next = now + timedelta(seconds=interval_seconds) if interval_seconds else None
    checks: list[ProviderCheck] = []
    alerts: list[dict[str, Any]] = []

    for event in database.list_events(include_paused=False):
        links = event.get("providers", [])
        if not links:
            continue
        all_succeeded = True
        complete_inventory = True
        event_candidates: list[tuple[dict[str, Any], PriceObservation, int, bool]] = []

        for link in links:
            key = link["provider_key"]
            provider = providers.get(key)
            if key in DISABLED_PRICE_PROVIDERS or provider is None:
                all_succeeded = False
                complete_inventory = False
                checks.append(ProviderCheck(event["id"], event["name"], key, False, error="Live price checks are disabled or no provider adapter is configured.", skipped=True))
                continue

            if getattr(provider, "key", key) != key:
                all_succeeded = False
                complete_inventory = False
                checks.append(ProviderCheck(event["id"], event["name"], key, False, error="Provider key does not match the configured event source."))
                continue

            not_before = _as_utc(link.get("next_check_at"))
            if not_before and not_before > now:
                all_succeeded = False
                complete_inventory = False
                checks.append(ProviderCheck(
                    event["id"], event["name"], key, False,
                    error=f"Next check is scheduled for {not_before.isoformat()}.", skipped=True,
                ))
                continue

            provider_event = ProviderEvent(
                source=key,
                event_id=link["provider_event_id"],
                name=event["name"],
                venue=event.get("venue") or "",
                event_date=event.get("event_date"),
                city=event.get("city"),
                region=event.get("region"),
                url=link.get("event_url"),
            )
            try:
                result = provider.get_prices(provider_event)
                if not isinstance(result, ProviderResult):
                    raise TypeError("provider returned an invalid result")
            except ProviderRequestError as exc:
                result = ProviderResult(failure=exc.failure)
            except Exception:
                result = ProviderResult(failure=ProviderFailure("provider_error", "The provider check failed unexpectedly.", retryable=True))

            # Provider observations are normally timestamped after the pass starts.
            # Evaluate freshness at response time unless a deterministic test time
            # was explicitly supplied.
            if not fixed_now:
                now = datetime.now(timezone.utc)

            invalid_item = any(
                not isinstance(item, PriceObservation)
                or item.source != key
                or item.event_id != link["provider_event_id"]
                for item in result.items
            )
            if invalid_item:
                result = ProviderResult(failure=ProviderFailure("malformed_observation", "The provider returned an observation for a different source or event."))

            try:
                stored = store_observations(
                    database,
                    event["id"],
                    link["event_provider_id"],
                    link["provider_event_id"],
                    result.items,
                    failure=result.failure,
                )
                successful = result.ok and stored.failure is None
                error = result.failure.message if result.failure else (stored.failure.message if stored.failure else None)
                provider_next = scheduled_next
                retry_after = result.failure.retry_after_seconds if result.failure else None
                if retry_after is not None and math.isfinite(retry_after) and retry_after >= 0:
                    retry_next = now + timedelta(seconds=retry_after)
                    if provider_next is None or retry_next > provider_next:
                        provider_next = retry_next
                database.update_check_status(
                    link["event_provider_id"],
                    attempted_at=attempted_at,
                    succeeded_at=attempted_at if successful else None,
                    error=error,
                    next_check_at=provider_next.isoformat() if provider_next else None,
                )
            except Exception:
                successful = False
                error = "Could not persist the provider check result."
                try:
                    database.update_check_status(
                        link["event_provider_id"],
                        attempted_at=attempted_at,
                        error=error,
                        next_check_at=scheduled_next.isoformat() if scheduled_next else None,
                    )
                except Exception:
                    pass
                all_succeeded = False
                complete_inventory = False
                checks.append(ProviderCheck(event["id"], event["name"], key, False, error=error))
                continue

            checks.append(ProviderCheck(
                event["id"], event["name"], key, successful,
                saved_observations=len(stored.observation_ids), error=error,
            ))
            if not successful:
                all_succeeded = False
                complete_inventory = False
                continue
            if not _inventory_is_comparable(result.items, event=event, now=now, stale_after=stale_after):
                complete_inventory = False
            for observation, observation_id in zip(result.items, stored.observation_ids):
                if _candidate(observation, event, now=now, stale_after=stale_after):
                    is_simulation = key == "mock"
                    if not is_simulation or simulation_mode:
                        event_candidates.append((link, observation, observation_id, is_simulation))

        if not event["alert_enabled"] or not all_succeeded:
            continue
        if event_candidates:
            link, observation, observation_id, is_simulation = event_candidates[0]
            record = database.record_monitor_alert(
                event["id"],
                event_provider_id=link["event_provider_id"],
                observation_id=observation_id,
                simulation_only=is_simulation,
                total_per_ticket=observation.total_per_ticket,
                currency=observation.currency,
                available_quantity=observation.available_quantity,
            )
            if record:
                alerts.append({
                    **record,
                    "event_id": event["id"],
                    "event_name": event["name"],
                    "provider_key": link["provider_key"],
                    "total_per_ticket": observation.total_per_ticket,
                    "currency": observation.currency,
                    "available_quantity": observation.available_quantity,
                })
        elif complete_inventory:
            database.rearm_monitor_alert(event["id"], checked_at=attempted_at)

    return MonitorPassResult(tuple(checks), tuple(alerts))
