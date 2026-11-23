"""Provider-neutral event and price observation models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math


class PricingConfidence(str, Enum):
    VERIFIED_ALL_IN = "verified_all_in"
    ESTIMATED = "estimated"
    INCOMPLETE = "incomplete"


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_currency(value: object) -> str:
    currency = str(value or "").strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError("currency must be a three-letter ASCII code")
    return currency


def positive_amount(value: object, field: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError(f"{field} must be a finite positive amount")
    return amount


@dataclass(frozen=True)
class ProviderEvent:
    source: str
    event_id: str
    name: str
    venue: str = ""
    event_date: str | None = None
    city: str | None = None
    region: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.event_id.strip() or not self.name.strip():
            raise ValueError("source, event_id, and name are required")


@dataclass(frozen=True)
class EventImage:
    url: str
    width: int | None = None
    height: int | None = None
    ratio: str | None = None


@dataclass(frozen=True)
class DiscoveredEvent:
    """Event catalog data, kept separate from ticket price observations."""

    source: str
    provider_id: str
    name: str
    event_date: str | None = None
    venue: str = ""
    city: str | None = None
    region: str | None = None
    url: str | None = None
    images: tuple[EventImage, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.provider_id.strip() or not self.name.strip():
            raise ValueError("source, provider_id, and name are required")


@dataclass(frozen=True)
class PriceObservation:
    """A ticket listing or a clearly distinct aggregate event price range."""

    source: str
    event_id: str
    currency: str
    observed_at: str
    pricing_confidence: PricingConfidence
    price_per_ticket: float | None = None
    listing_id: str | None = None
    url: str | None = None
    available_quantity: int | None = None
    fees_per_ticket: float | None = None
    total_per_ticket: float | None = None
    section: str | None = None
    row: str | None = None
    observation_type: str = "ticket_listing"
    range_min_price: float | None = None
    range_max_price: float | None = None
    range_label: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.event_id.strip():
            raise ValueError("source and event_id are required")
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        try:
            confidence = PricingConfidence(self.pricing_confidence)
        except ValueError as exc:
            raise ValueError("unsupported pricing confidence") from exc
        object.__setattr__(self, "pricing_confidence", confidence)
        if not self.observed_at.strip():
            raise ValueError("observed_at is required")

        if self.observation_type == "aggregate_price_range":
            low = positive_amount(self.range_min_price, "range_min_price")
            high = positive_amount(self.range_max_price, "range_max_price")
            if high < low:
                raise ValueError("range maximum must be at least the minimum")
            if any(value is not None for value in (self.price_per_ticket, self.available_quantity, self.fees_per_ticket, self.total_per_ticket)):
                raise ValueError("aggregate ranges cannot claim listing price, quantity, fees, or total")
            if confidence is not PricingConfidence.INCOMPLETE:
                raise ValueError("aggregate ranges must have incomplete pricing confidence")
            object.__setattr__(self, "range_min_price", low)
            object.__setattr__(self, "range_max_price", high)
        elif self.observation_type == "ticket_listing":
            price = positive_amount(self.price_per_ticket, "price_per_ticket")
            object.__setattr__(self, "price_per_ticket", price)
            if self.available_quantity is not None:
                if isinstance(self.available_quantity, bool) or int(self.available_quantity) != self.available_quantity or int(self.available_quantity) < 1:
                    raise ValueError("available_quantity must be a positive integer")
                object.__setattr__(self, "available_quantity", int(self.available_quantity))
            if self.fees_per_ticket is not None:
                fee = float(self.fees_per_ticket)
                if not math.isfinite(fee) or fee < 0:
                    raise ValueError("fees_per_ticket must be a finite nonnegative amount")
                object.__setattr__(self, "fees_per_ticket", fee)
            if self.total_per_ticket is not None:
                object.__setattr__(self, "total_per_ticket", positive_amount(self.total_per_ticket, "total_per_ticket"))
            if confidence is PricingConfidence.VERIFIED_ALL_IN and self.total_per_ticket is None:
                raise ValueError("verified all-in pricing requires a total_per_ticket")
        else:
            raise ValueError("unsupported observation_type")
