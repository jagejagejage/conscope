"""Provider contracts and normalized request failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from .models import DiscoveredEvent, PriceObservation, ProviderEvent


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: float | None = None
    http_status: int | None = None


T = TypeVar("T")


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    items: tuple[T, ...] = ()
    failure: ProviderFailure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None


class TicketProvider(Protocol):
    """Minimal provider boundary; implementations never depend on Kafka."""

    key: str
    display_name: str

    def discover_events(self, query: str) -> ProviderResult[ProviderEvent]:
        ...

    def search_events(self, query: str, *, city: str | None = None, event_date: str | None = None) -> ProviderResult[DiscoveredEvent]:
        ...

    def get_prices(self, event: ProviderEvent) -> ProviderResult[PriceObservation]:
        ...


class ProviderRequestError(Exception):
    def __init__(self, failure: ProviderFailure):
        super().__init__(failure.message)
        self.failure = failure
