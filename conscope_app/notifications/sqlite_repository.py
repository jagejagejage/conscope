"""SQLite adapter for the provider-neutral notification repository port."""

from __future__ import annotations

from datetime import datetime, timezone

from ..database import Database
from .models import AlertEmailContext, DeliveryClaim


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class SQLiteNotificationRepository:
    def __init__(self, database: Database):
        self.database = database

    def get_alert_context(self, alert_id: int) -> AlertEmailContext | None:
        row = self.database.get_email_alert_context(alert_id)
        if row is None:
            return None
        return AlertEmailContext(
            alert_id=row["alert_id"],
            simulation_only=bool(row["simulation_only"]),
            event_name=row["event_name"],
            observed_price=float(row["observed_price"]),
            target_price=float(row["target_price"]),
            requested_quantity=int(row["requested_quantity"]),
            available_quantity=int(row["available_quantity"]),
            currency=row["currency"],
            checked_at=row["checked_at"],
            listing_url=row["listing_url"],
            listing_id=row["listing_id"],
        )

    def enqueue_alert(self, alert_id: int, recipient_email: str, idempotency_key: str) -> int:
        row = self.database.enqueue_email_notification(
            alert_id, recipient_email=recipient_email, idempotency_key=idempotency_key,
        )
        return int(row["id"])

    def claim_due(self, *, now: datetime, lease_seconds: float, limit: int, max_attempts: int) -> list[DeliveryClaim]:
        rows = self.database.claim_email_notifications(
            now=_iso(now), lease_seconds=lease_seconds, limit=limit, max_attempts=max_attempts,
        )
        return [DeliveryClaim(
            id=int(row["id"]),
            monitor_alert_record_id=int(row["monitor_alert_record_id"]),
            recipient_email=row["recipient_email"],
            idempotency_key=row["idempotency_key"],
            claim_token=row["claim_token"],
            attempt_count=int(row["attempt_count"]),
        ) for row in rows]

    def mark_sent(self, claim: DeliveryClaim, provider_message_id: str, *, sent_at: datetime) -> bool:
        return self.database.mark_email_notification_sent(
            claim.id, claim.claim_token, provider_message_id=provider_message_id, sent_at=_iso(sent_at),
        )

    def mark_failure(self, claim: DeliveryClaim, *, retryable: bool, error: str, retry_at: datetime, delivery_uncertain: bool, updated_at: datetime) -> bool:
        return self.database.mark_email_notification_failure(
            claim.id,
            claim.claim_token,
            status="retryable" if retryable else "failed",
            error=error,
            retry_at=_iso(retry_at),
            delivery_uncertain=delivery_uncertain,
            updated_at=_iso(updated_at),
        )
