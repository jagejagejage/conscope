"""Resend adapter implemented over its documented REST endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
from typing import Any, Protocol

import requests

from .models import DeliveryFailure, DeliveryResult, EmailMessage


class EmailProvider(Protocol):
    def send(self, message: EmailMessage, *, idempotency_key: str) -> DeliveryResult:
        ...


class ResendEmailProvider:
    """Send a single email via Resend without logging credentials or payloads."""

    key = "resend"

    def __init__(self, api_key: str | None = None, *, session: Any | None = None, timeout: float = 10.0, base_url: str = "https://api.resend.com"):
        self._api_key = api_key if api_key is not None else os.environ.get("RESEND_API_KEY")
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    def send(self, message: EmailMessage, *, idempotency_key: str) -> DeliveryResult:
        if not self._api_key:
            return DeliveryResult(failure=DeliveryFailure(
                "missing_credentials", "RESEND_API_KEY is not configured.", retryable=False,
            ))
        if not idempotency_key or len(idempotency_key) > 256:
            return DeliveryResult(failure=DeliveryFailure(
                "invalid_idempotency_key", "A valid Resend idempotency key is required.", retryable=False,
            ))
        try:
            response = self.session.post(
                f"{self.base_url}/emails",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "from": message.sender,
                    "to": [message.recipient],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout:
            return DeliveryResult(failure=DeliveryFailure(
                "timeout", "Resend timed out; delivery may have completed.", retryable=True,
                delivery_uncertain=True,
            ))
        except requests.exceptions.RequestException:
            return DeliveryResult(failure=DeliveryFailure(
                "network_error", "The Resend request failed; delivery may have completed.", retryable=True,
                delivery_uncertain=True,
            ))

        status = getattr(response, "status_code", None)
        if status is None or not 200 <= status < 300:
            provider_code = _response_error_code(response)
            retryable = status == 429 or status in {408, 425} or (status is not None and status >= 500)
            if status == 409 and provider_code == "concurrent_idempotent_requests":
                retryable = True
            failure = DeliveryFailure(
                provider_code or f"http_{status or 'unknown'}",
                _safe_http_message(status),
                retryable=retryable,
                retry_after_seconds=_retry_after(getattr(response, "headers", {}).get("Retry-After")) if status == 429 else None,
                delivery_uncertain=False,
                http_status=status,
            )
            return DeliveryResult(failure=failure)
        try:
            payload = response.json()
        except (ValueError, AttributeError):
            payload = None
        message_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(message_id, str) or not message_id.strip():
            return DeliveryResult(failure=DeliveryFailure(
                "malformed_success_response", "Resend accepted the request but returned no email ID.",
                retryable=True, delivery_uncertain=True, http_status=status,
            ))
        return DeliveryResult(provider_message_id=message_id)


def _response_error_code(response: Any) -> str | None:
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("name") or payload.get("code") or payload.get("error")
    if isinstance(value, str) and value and len(value) <= 80:
        return value
    return None


def _safe_http_message(status: int | None) -> str:
    if status == 429:
        return "Resend rate limit reached."
    if status is not None and status >= 500:
        return "Resend is temporarily unavailable."
    if status in {401, 403}:
        return "Resend rejected the credentials or sender authorization."
    if status == 409:
        return "Resend reported an idempotency conflict."
    return f"Resend rejected the email request (HTTP {status or 'unknown'})."


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
