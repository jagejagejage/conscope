"""Offline email preview and explicitly confirmed Resend test-email CLI."""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from conscope_app.notifications.models import EmailMessage
from conscope_app.notifications.resend import ResendEmailProvider
from conscope_app.notifications.templates import render_ticket_alert, sample_alert_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Render a synthetic sample email without network access")
    preview.add_argument("--format", choices=("text", "html", "both"), default="both")
    test = sub.add_parser("test-email", help="Send one synthetic test email to a confirmed address")
    test.add_argument("--to", required=True, help="Test recipient")
    test.add_argument("--confirm-to", required=True, help="Must exactly match --to")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rendered = render_ticket_alert(sample_alert_context(), test_message=args.command == "test-email")
    if args.command == "preview":
        if args.format in {"text", "both"}:
            print("--- Plain text ---")
            print(rendered.text)
        if args.format in {"html", "both"}:
            print("--- HTML ---")
            print(rendered.html)
        return 0

    recipient = args.to.strip().lower()
    confirmed = args.confirm_to.strip().lower()
    if recipient != confirmed:
        print("Test recipient confirmation did not match; no email was sent.", file=sys.stderr)
        return 2
    sender = os.environ.get("RESEND_FROM_EMAIL", "").strip()
    if not sender:
        print("RESEND_FROM_EMAIL is not configured; no email was sent.", file=sys.stderr)
        return 2
    result = ResendEmailProvider().send(
        EmailMessage(sender, recipient, rendered.subject, rendered.html, rendered.text),
        idempotency_key=f"conscope-test/{uuid.uuid4()}",
    )
    if not result.ok:
        failure = result.failure
        print(f"Test email failed: {failure.code if failure else 'unknown_error'} — {failure.message if failure else 'unknown error'}", file=sys.stderr)
        return 1
    print(f"Test email accepted by Resend (message ID {result.provider_message_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
