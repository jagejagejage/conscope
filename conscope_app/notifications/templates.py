"""Safe plain-text and HTML templates for verified ticket alerts."""

from __future__ import annotations

from html import escape
import re
from urllib.parse import urlparse

from .models import AlertEmailContext, RenderedEmail


def _listing_url(value: str | None) -> str:
    if not value:
        raise ValueError("An original ticket listing URL is required for an email alert.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("The original ticket listing URL must use HTTP or HTTPS.")
    return value


def render_ticket_alert(context: AlertEmailContext, *, test_message: bool = False) -> RenderedEmail:
    if context.simulation_only and not test_message:
        raise ValueError("Simulation-only alerts cannot be rendered as customer emails.")
    url = _listing_url(context.listing_url)
    event_name = re.sub(r"[\r\n]+", " ", context.event_name).strip() or "Ticket event"
    escaped_name = escape(event_name)
    escaped_url = escape(url, quote=True)
    subject_prefix = "[TEST] " if test_message else ""
    subject = f"{subject_prefix}Ticket price target reached: {event_name}"[:200]
    notice = "This is a test message. No ticket alert was sent." if test_message else (
        "Prices and availability can change before purchase. This offer may no longer be available when you open the listing."
    )
    observed_price = f"{context.currency} {context.observed_price:,.2f}"
    target_price = f"{context.currency} {context.target_price:,.2f}"
    text = (
        f"{notice}\n\n"
        f"Event: {event_name}\n"
        f"Observed all-in price per ticket: {observed_price}\n"
        f"Your maximum target per ticket: {target_price}\n"
        f"Requested ticket quantity: {context.requested_quantity}\n"
        f"Quantity reported available: {context.available_quantity}\n"
        f"Currency: {context.currency}\n"
        f"Checked at: {context.checked_at}\n"
        f"Original ticket listing: {url}\n"
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#f5f7fa;font-family:Arial,sans-serif;color:#172033">
  <main style="max-width:600px;margin:24px auto;padding:24px;background:#ffffff;border-radius:12px">
    <p style="font-size:14px;color:#526079">ConScope ticket watch</p>
    <h1 style="font-size:24px;line-height:1.25">{escaped_name}</h1>
    <p style="font-size:16px">{escape(notice)}</p>
    <table role="presentation" style="width:100%;border-collapse:collapse">
      <tr><th align="left" style="padding:8px 0">Observed all-in price per ticket</th><td align="right">{escape(observed_price)}</td></tr>
      <tr><th align="left" style="padding:8px 0">Your maximum target per ticket</th><td align="right">{escape(target_price)}</td></tr>
      <tr><th align="left" style="padding:8px 0">Requested quantity</th><td align="right">{context.requested_quantity}</td></tr>
      <tr><th align="left" style="padding:8px 0">Reported available quantity</th><td align="right">{context.available_quantity}</td></tr>
      <tr><th align="left" style="padding:8px 0">Currency</th><td align="right">{escape(context.currency)}</td></tr>
      <tr><th align="left" style="padding:8px 0">Checked at</th><td align="right">{escape(context.checked_at)}</td></tr>
    </table>
    <p style="margin:24px 0"><a href="{escaped_url}" style="display:inline-block;padding:12px 18px;background:#164e63;color:#ffffff;text-decoration:none;border-radius:8px">Open original ticket listing</a></p>
    <p style="font-size:12px;color:#667085">Prices and availability may change before purchase. ConScope cannot reserve tickets.</p>
  </main>
</body></html>"""
    return RenderedEmail(subject=subject, html=html, text=text)


def sample_alert_context() -> AlertEmailContext:
    """Safe synthetic content for the offline preview and explicit test email."""
    return AlertEmailContext(
        alert_id=0,
        simulation_only=False,
        event_name="Example Band at Sample Arena",
        observed_price=96.50,
        target_price=120.00,
        requested_quantity=2,
        available_quantity=4,
        currency="USD",
        checked_at="2027-04-18T17:45:00+00:00",
        listing_url="https://tickets.example.invalid/listings/sample-123",
        listing_id="sample-123",
    )
