"""HTTP helpers shared by API provider adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

import requests

from .base import ProviderFailure, ProviderRequestError
from .models import current_timestamp

class HttpProvider:
    key = ""
    display_name = ""

    def __init__(self, *, session: Any | None = None, timeout: float = 10.0):
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    def get_json(self, url: str, *, params: Mapping[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.get(url, params=dict(params), timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise ProviderRequestError(ProviderFailure("timeout", "The provider request timed out.", retryable=True)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderRequestError(ProviderFailure("offline", "Could not connect to the ticket provider.", retryable=True)) from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderRequestError(ProviderFailure("request_error", "The provider request failed.", retryable=True)) from exc

        status = getattr(response, "status_code", None)
        if status == 429:
            raise ProviderRequestError(ProviderFailure(
                "rate_limited", "The provider rate limit was reached.", retryable=True,
                retry_after_seconds=_retry_after(response.headers.get("Retry-After")), http_status=status,
            ))
        if status is not None and status >= 500:
            raise ProviderRequestError(ProviderFailure("provider_unavailable", "The ticket provider is temporarily unavailable.", retryable=True, http_status=status))
        if status is not None and status >= 400:
            raise ProviderRequestError(ProviderFailure("http_error", "The ticket provider rejected the request.", http_status=status))
        try:
            payload = response.json()
        except (ValueError, AttributeError) as exc:
            raise ProviderRequestError(ProviderFailure("malformed_response", "The provider returned invalid JSON.")) from exc
        if not isinstance(payload, dict):
            raise ProviderRequestError(ProviderFailure("malformed_response", "The provider response was not a JSON object."))
        return payload


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


def make_event_time(value: object) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    return None


def observed_now() -> str:
    return current_timestamp()
