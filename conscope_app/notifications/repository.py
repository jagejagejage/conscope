"""Persistence port used by the notification service."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import AlertEmailContext, DeliveryClaim


class NotificationRepository(Protocol):
    def get_alert_context(self, alert_id: int) -> AlertEmailContext | None:
        ...

    def enqueue_alert(self, alert_id: int, recipient_email: str, idempotency_key: str) -> int:
        ...

    def claim_due(self, *, now: datetime, lease_seconds: float, limit: int, max_attempts: int) -> list[DeliveryClaim]:
        ...

    def mark_sent(self, claim: DeliveryClaim, provider_message_id: str, *, sent_at: datetime) -> bool:
        ...

    def mark_failure(self, claim: DeliveryClaim, *, retryable: bool, error: str, retry_at: datetime, delivery_uncertain: bool, updated_at: datetime) -> bool:
        ...
