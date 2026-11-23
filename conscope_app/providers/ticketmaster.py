"""Ticketmaster Discovery adapter for event search and aggregate price ranges.

This adapter is based on the legacy ConScope Discovery API paths and parameter
names. It does not treat a price range as an individual ticket listing and
never reports listing quantity, fees, or an all-in total.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from .base import ProviderFailure, ProviderRequestError, ProviderResult
from .http import HttpProvider, make_event_time, observed_now
from .models import DiscoveredEvent, EventImage, PriceObservation, PricingConfidence, ProviderEvent, normalize_currency, positive_amount


class TicketmasterProvider(HttpProvider):
    key = "ticketmaster"
    display_name = "Ticketmaster"

    def __init__(self, api_key: str | None = None, *, base_url: str = "https://app.ticketmaster.com/discovery/v2", session: Any | None = None, timeout: float = 10.0):
        super().__init__(session=session, timeout=timeout)
        self.api_key = api_key if api_key is not None else os.environ.get("TICKETMASTER_API_KEY")
        self.base_url = base_url.rstrip("/")

    def discover_events(self, query: str) -> ProviderResult[ProviderEvent]:
        """Compatibility adapter for existing provider consumers."""
        found = self.search_events(query)
        if not found.ok:
            return ProviderResult(failure=found.failure)
        return ProviderResult(tuple(ProviderEvent(
            source=item.source, event_id=item.provider_id, name=item.name, venue=item.venue,
            event_date=item.event_date, city=item.city, region=item.region, url=item.url,
        ) for item in found.items))

    def search_events(
        self,
        query: str,
        *,
        city: str | None = None,
        event_date: str | None = None,
    ) -> ProviderResult[DiscoveredEvent]:
        """Search the Discovery API without coupling discovery to price data.

        ``event_date`` accepts YYYY-MM-DD (UTC day window) or an ISO timestamp.
        """
        if not self.api_key:
            return ProviderResult(failure=ProviderFailure("missing_credentials", "Ticketmaster API key is not configured."))
        if not query or not query.strip():
            return ProviderResult(failure=ProviderFailure("invalid_query", "Enter an event, artist, or venue to search."))
        params: dict[str, Any] = {
            "apikey": self.api_key,
            "keyword": query.strip(),
            "size": 20,
            "sort": "relevance,desc",
        }
        if city and city.strip():
            params["city"] = city.strip()
        if event_date:
            date_value = event_date.strip()
            if len(date_value) == 10:
                try:
                    from datetime import date, timedelta
                    day = date.fromisoformat(date_value)
                except ValueError:
                    return ProviderResult(failure=ProviderFailure("invalid_date", "Use YYYY-MM-DD or an ISO date-time for the event date."))
                params["startDateTime"] = f"{day.isoformat()}T00:00:00Z"
                params["endDateTime"] = f"{(day + timedelta(days=1)).isoformat()}T00:00:00Z"
            else:
                normalized = make_event_time(date_value)
                if not normalized:
                    return ProviderResult(failure=ProviderFailure("invalid_date", "Use YYYY-MM-DD or an ISO date-time for the event date."))
                params["startDateTime"] = normalized
        try:
            payload = self.get_json(f"{self.base_url}/events.json", params=params)
        except ProviderRequestError as exc:
            return ProviderResult(failure=exc.failure)

        embedded = payload.get("_embedded", {})
        raw_events = embedded.get("events", []) if isinstance(embedded, dict) else None
        if not isinstance(raw_events, list):
            return ProviderResult(failure=ProviderFailure("malformed_response", "Ticketmaster response did not contain an event array."))
        events = []
        failure = None
        for raw in raw_events:
            try:
                if not isinstance(raw, dict) or not raw.get("id") or not raw.get("name"):
                    raise ValueError("event ID and name are required")
                embedded_event = raw.get("_embedded") or {}
                venues = embedded_event.get("venues", []) if isinstance(embedded_event, dict) else []
                venue = venues[0] if isinstance(venues, list) and venues and isinstance(venues[0], dict) else {}
                city = venue.get("city") or {}
                state = venue.get("state") or {}
                start = (raw.get("dates") or {}).get("start") or {}
                raw_images = raw.get("images") or []
                if not isinstance(raw_images, list):
                    raise ValueError("images must be an array")
                images = tuple(EventImage(
                    url=str(image["url"]),
                    width=_optional_int(image.get("width")),
                    height=_optional_int(image.get("height")),
                    ratio=_optional(image.get("ratio")),
                ) for image in raw_images if isinstance(image, dict) and image.get("url"))
                events.append(DiscoveredEvent(
                    source=self.key,
                    provider_id=str(raw["id"]),
                    name=str(raw["name"]),
                    venue=str(venue.get("name") or ""),
                    event_date=make_event_time(start.get("dateTime")),
                    city=_optional(city.get("name")),
                    region=_optional(state.get("stateCode")),
                    url=_optional(raw.get("url")),
                    images=images,
                ))
            except (TypeError, ValueError, AttributeError) as exc:
                failure = ProviderFailure("malformed_event", f"A Ticketmaster event result was invalid: {exc}")
        return ProviderResult(tuple(events), failure)

    def get_prices(self, event: ProviderEvent) -> ProviderResult[PriceObservation]:
        if not self.api_key:
            return ProviderResult(failure=ProviderFailure("missing_credentials", "Ticketmaster API key is not configured."))
        if event.source.lower() != self.key:
            return ProviderResult(failure=ProviderFailure("wrong_provider_event", "The supplied event is not a Ticketmaster event."))
        if not event.event_id.strip():
            return ProviderResult(failure=ProviderFailure("invalid_event", "A Ticketmaster event ID is required."))
        try:
            payload = self.get_json(f"{self.base_url}/events/{quote(event.event_id, safe='')}.json", params={"apikey": self.api_key})
        except ProviderRequestError as exc:
            return ProviderResult(failure=exc.failure)
        raw_ranges = payload.get("priceRanges", [])
        if raw_ranges is None:
            raw_ranges = []
        if not isinstance(raw_ranges, list):
            return ProviderResult(failure=ProviderFailure("malformed_response", "Ticketmaster priceRanges was not an array."))
        observations = []
        failure = None
        for raw in raw_ranges:
            try:
                if not isinstance(raw, dict):
                    raise ValueError("price range must be an object")
                label = str(raw.get("type") or "").strip()
                if not label:
                    raise ValueError("price range type is required")
                observations.append(PriceObservation(
                    source=self.key,
                    event_id=event.event_id,
                    currency=normalize_currency(raw.get("currency")),
                    observed_at=observed_now(),
                    pricing_confidence=PricingConfidence.INCOMPLETE,
                    observation_type="aggregate_price_range",
                    range_min_price=positive_amount(raw.get("min"), "min"),
                    range_max_price=positive_amount(raw.get("max"), "max"),
                    range_label=label,
                    url=event.url,
                ))
            except (TypeError, ValueError, KeyError) as exc:
                failure = ProviderFailure("malformed_price_range", f"A Ticketmaster price range was invalid: {exc}")
        return ProviderResult(tuple(observations), failure)


def _optional(value: object) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def search_ticketmaster_events(
    query: str,
    *,
    city: str | None = None,
    event_date: str | None = None,
    api_key: str | None = None,
    session: Any | None = None,
    timeout: float = 10.0,
) -> ProviderResult[DiscoveredEvent]:
    """Small injectable entry point for search UI and offline tests."""
    return TicketmasterProvider(api_key, session=session, timeout=timeout).search_events(
        query, city=city, event_date=event_date,
    )
