"""SeatGeek adapter based on the legacy ConScope listings integration.

The endpoint and ``client_id`` query parameter are carried forward from the
legacy producer. Their current availability, authorization requirements, and
price-field semantics have not been verified; no request is made at import or
construction time.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from .base import ProviderFailure, ProviderRequestError, ProviderResult
from .http import HttpProvider, observed_now
from .models import PriceObservation, PricingConfidence, ProviderEvent, positive_amount


class SeatGeekProvider(HttpProvider):
    key = "seatgeek"
    display_name = "SeatGeek"

    def __init__(self, client_id: str | None = None, *, base_url: str = "https://api.seatgeek.com/2", session: Any | None = None, timeout: float = 10.0, access_approved: bool = False):
        super().__init__(session=session, timeout=timeout)
        self.client_id = client_id if client_id is not None else os.environ.get("SEATGEEK_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.access_approved = access_approved

    def discover_events(self, query: str) -> ProviderResult[ProviderEvent]:
        return ProviderResult(failure=ProviderFailure(
            "unsupported_operation",
            "Event discovery is not implemented for this SeatGeek adapter; provide a SeatGeek event ID.",
        ))

    def get_prices(self, event: ProviderEvent) -> ProviderResult[PriceObservation]:
        if not self.access_approved:
            return ProviderResult(failure=ProviderFailure(
                "access_unverified",
                "The legacy listings endpoint and permission for price monitoring must be verified before use.",
            ))
        if not self.client_id:
            return ProviderResult(failure=ProviderFailure("missing_credentials", "SeatGeek client ID is not configured."))
        if event.source.lower() != self.key:
            return ProviderResult(failure=ProviderFailure("wrong_provider_event", "The supplied event is not a SeatGeek event."))
        if not event.event_id.strip():
            return ProviderResult(failure=ProviderFailure("invalid_event", "A SeatGeek event ID is required."))
        url = f"{self.base_url}/events/{quote(event.event_id, safe='')}/listings"
        try:
            payload = self.get_json(url, params={
                "client_id": self.client_id,
                "per_page": 100,
                "sort": "price",
                "order": "asc",
            })
        except ProviderRequestError as exc:
            return ProviderResult(failure=exc.failure)
        listings = payload.get("listings")
        if not isinstance(listings, list):
            return ProviderResult(failure=ProviderFailure("malformed_response", "SeatGeek response did not contain a listings array."))

        observations = []
        failure = None
        for listing in listings:
            try:
                observations.append(self._normalize_listing(listing, event))
            except (TypeError, ValueError, KeyError) as exc:
                failure = ProviderFailure("malformed_listing", f"A SeatGeek listing was invalid: {exc}")
        return ProviderResult(tuple(observations), failure)

    def _normalize_listing(self, listing: object, event: ProviderEvent) -> PriceObservation:
        if not isinstance(listing, dict):
            raise ValueError("listing must be an object")
        currency = listing.get("currency")
        price = _amount(listing.get("price"), "price")
        quantity = _quantity(listing.get("quantity")) if listing.get("quantity") is not None else None
        fees = None
        fee_data = listing.get("fees")
        if isinstance(fee_data, dict) and fee_data.get("per_ticket") is not None:
            fees = _fee(fee_data["per_ticket"])

        explicit_total = listing.get("total_price")
        total = _amount(explicit_total, "total_price") if explicit_total is not None else None
        confidence = PricingConfidence.INCOMPLETE
        if total is not None:
            confidence = PricingConfidence.ESTIMATED
        elif fees is not None:
            total = price + fees
            confidence = PricingConfidence.ESTIMATED

        listing_id = listing.get("id")
        return PriceObservation(
            source=self.key,
            event_id=event.event_id,
            listing_id=str(listing_id) if listing_id is not None else None,
            url=_optional_text(listing.get("url")),
            currency=currency,
            available_quantity=quantity,
            price_per_ticket=price,
            fees_per_ticket=fees,
            total_per_ticket=total,
            observed_at=observed_now(),
            pricing_confidence=confidence,
            section=_optional_text(listing.get("section")),
            row=_optional_text(listing.get("row")),
        )


def _amount(value: object, field: str) -> float:
    return positive_amount(value, field)


def _fee(value: object) -> float:
    try:
        fee = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("fees.per_ticket must be numeric") from exc
    if fee < 0 or fee != fee or fee == float("inf"):
        raise ValueError("fees.per_ticket must be a finite nonnegative amount")
    return fee


def _quantity(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("quantity must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("quantity must be a positive integer") from exc
    if result != value or result < 1:
        raise ValueError("quantity must be a positive integer")
    return result


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
