# Resend email notification foundation

ConScope now has a provider-neutral notification service, an SQLite outbox adapter, a Resend HTTP adapter, and a synthetic email template. This is delivery infrastructure only: monitoring does not enqueue or send customer alerts, and the CLI monitor does not register live ticket-price providers. The outbox rejects simulation-only alert records. No email is sent by installation, tests, or normal monitoring commands.

## Local Resend setup

1. Create a Resend account and an API key in its dashboard. Use a restricted key where available and keep it private.
2. Add a domain you control under Resend **Domains**. Publish the DNS records Resend provides, including its sending authentication records, and wait until the dashboard reports the domain as verified. Use a sender address on that verified domain, such as `ConScope <alerts@example.com>`; do not use an address you do not control.
3. Export the key and sender in the same shell used to invoke the CLI:

   ```sh
   export RESEND_API_KEY='re_…'
   export RESEND_FROM_EMAIL='ConScope <alerts@example.com>'
   ```

   PowerShell:

   ```powershell
   $env:RESEND_API_KEY = 're_…'
   $env:RESEND_FROM_EMAIL = 'ConScope <alerts@example.com>'
   ```

Never put credentials in Python source, tests, command-line arguments, screenshots, or committed `.env` files. If you use a local `.env` loader, keep that file ignored and restrict its permissions. Rotate a key if it is exposed. The Resend adapter reads `RESEND_API_KEY` from the process environment; the CLI reads `RESEND_FROM_EMAIL` the same way.

## Preview and explicit test email

Render synthetic HTML and plain text locally. This command has no network path and needs no API key:

```sh
python3 scripts/email_notifications.py preview --format both
```

To explicitly send one synthetic test message, provide the recipient twice as a confirmation. This is the only current command that sends email; it does not use a tracked user's alert data:

```sh
python3 scripts/email_notifications.py test-email \
  --to you@example.com \
  --confirm-to you@example.com
```

The two addresses must match. The command also requires the configured Resend key and verified sender. Do not invoke it in CI or automated tests. It was not invoked as part of this implementation.

## Delivery behavior and limits

The delivery worker is an explicit library service, separate from `run_monitor.py`; there is no scheduled customer delivery command or dashboard setting wired to it. The repository port is provider-neutral, with SQLite as its current implementation. A later hosted integration must deliberately define account ownership, verified recipient addresses, alert subscription/consent, queue dispatch, and monitoring-to-outbox enqueueing before sending customer notifications.

Outbox states are `pending`, `sending` (transactionally claimed with a lease token), `sent`, `retryable`, and `failed`. A unique alert/recipient constraint prevents duplicate queue entries. Claiming uses `BEGIN IMMEDIATE`; attempts use a stable idempotency key and are capped at five by default. Transient network/server failures and rate limits retry with exponential backoff, honoring a longer `Retry-After`. Permanent validation/authorization errors fail without repeated retries. Expired claims are retried with the same key. Uncertain deliveries stop after 23 hours, before Resend's documented 24-hour idempotency-key retention window.

No sender can guarantee exactly-once email delivery across arbitrary network failures. A timeout can happen after Resend accepted a message but before ConScope received its response. Retries with the same idempotency key reduce duplicate sends while the provider retains that key; after that window, ConScope marks the outcome failed/uncertain instead of blindly resending. A future operator workflow must resolve such records. Resend's current idempotency contract and error behavior can change; consult its [API reference](https://resend.com/docs/api-reference/emails/send-email) and [error codes](https://resend.com/docs/api-reference/errors).

The message contains an observed all-in price, target, requested and reported quantity, currency, check time, and original listing URL. It explicitly says price and availability can change before purchase. It is only valid for a future verified ticket-listing observation. Event-level Discovery API price ranges, estimated prices, incomplete prices, and simulation observations are not valid customer alert inputs.

Resend's plans, free allowances, sending limits, and account restrictions are subject to change. No current price or quota is assumed here; check the [official pricing page](https://resend.com/pricing) and your account's applicable terms before use.
