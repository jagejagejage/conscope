"""Provider-neutral outbox orchestration with bounded retry behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re

from .models import EmailMessage, NotificationRunResult
from .repository import NotificationRepository
from .resend import EmailProvider
from .templates import render_ticket_alert


_EMAIL_RE = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


class NotificationService:
    """Coordinates durable claims, template rendering, and provider delivery."""

    def __init__(
        self, repository: NotificationRepository, provider: EmailProvider, *, sender: str,
        max_attempts: int = 5, base_backoff_seconds: float = 30,
        max_backoff_seconds: float = 3600, lease_seconds: float = 120,
    ):
        if max_attempts < 1 or base_backoff_seconds < 0 or max_backoff_seconds < base_backoff_seconds or lease_seconds <= 0:
            raise ValueError("invalid notification retry or lease configuration")
        self.repository = repository
        self.provider = provider
        self.sender = sender.strip()
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.lease_seconds = lease_seconds

    def enqueue_alert(self, alert_id: int, recipient_email: str) -> int:
        recipient = recipient_email.strip().lower()
        if not _EMAIL_RE.fullmatch(recipient):
            raise ValueError("A valid recipient email address is required.")
        context = self.repository.get_alert_context(alert_id)
        if context is None:
            raise KeyError(alert_id)
        if context.simulation_only:
            raise ValueError("Simulation-only alerts cannot enter the customer email queue.")
        # Validate required listing data before making an outbox record.
        render_ticket_alert(context)
        recipient_digest = hashlib.sha256(recipient.encode("utf-8")).hexdigest()
        key = f"conscope-alert/{alert_id}/{recipient_digest}"
        return self.repository.enqueue_alert(alert_id, recipient, key)

    def deliver_pending(self, *, now: datetime | None = None, limit: int = 50) -> NotificationRunResult:
        current = _utc(now)
        claims = self.repository.claim_due(
            now=current, lease_seconds=self.lease_seconds, limit=limit, max_attempts=self.max_attempts,
        )
        sent = retryable = failed = claim_lost = 0
        for claim in claims:
            context = self.repository.get_alert_context(claim.monitor_alert_record_id)
            if context is None or context.simulation_only:
                retry = False
                error = "Alert context is missing or simulation-only."
                uncertain = False
                retry_at = current
            else:
                try:
                    rendered = render_ticket_alert(context)
                    result = self.provider.send(EmailMessage(
                        sender=self.sender, recipient=claim.recipient_email,
                        subject=rendered.subject, html=rendered.html, text=rendered.text,
                    ), idempotency_key=claim.idempotency_key)
                except Exception:
                    # If the provider call raises unexpectedly, treat the result as
                    # uncertain: it may have accepted the message before failing.
                    result = None
                if result is not None and result.ok:
                    if self.repository.mark_sent(claim, result.provider_message_id or "", sent_at=current):
                        sent += 1
                    else:
                        claim_lost += 1
                    continue
                problem = result.failure if result is not None else None
                retry = bool(problem and problem.retryable) and claim.attempt_count < self.max_attempts
                error = problem.message if problem else "Unexpected delivery error; outcome may be uncertain."
                uncertain = problem.delivery_uncertain if problem else True
                delay = min(self.base_backoff_seconds * (2 ** max(0, claim.attempt_count - 1)), self.max_backoff_seconds)
                if problem and problem.retry_after_seconds is not None:
                    delay = max(delay, problem.retry_after_seconds)
                retry_at = current + timedelta(seconds=delay)
            changed = self.repository.mark_failure(
                claim, retryable=retry, error=error, retry_at=retry_at,
                delivery_uncertain=uncertain, updated_at=current,
            )
            if not changed:
                claim_lost += 1
            elif retry:
                retryable += 1
            else:
                failed += 1
        return NotificationRunResult(sent, retryable, failed, claim_lost)


def _utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
