"""Provider-neutral email notification value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlertEmailContext:
    alert_id: int
    simulation_only: bool
    event_name: str
    observed_price: float
    target_price: float
    requested_quantity: int
    available_quantity: int
    currency: str
    checked_at: str
    listing_url: str | None
    listing_id: str | None = None


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class EmailMessage:
    sender: str
    recipient: str
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class DeliveryFailure:
    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: float | None = None
    delivery_uncertain: bool = False
    http_status: int | None = None


@dataclass(frozen=True)
class DeliveryResult:
    provider_message_id: str | None = None
    failure: DeliveryFailure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None and bool(self.provider_message_id)


@dataclass(frozen=True)
class DeliveryClaim:
    id: int
    monitor_alert_record_id: int
    recipient_email: str
    idempotency_key: str
    claim_token: str
    attempt_count: int


@dataclass(frozen=True)
class NotificationRunResult:
    sent: int = 0
    retryable: int = 0
    failed: int = 0
    claim_lost: int = 0
