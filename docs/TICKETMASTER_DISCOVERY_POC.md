# Ticketmaster Discovery API proof of concept

ConScope can search Ticketmaster Discovery by keyword, with optional city and date filters. The normalized discovery result contains the provider ID, event name, optional date, venue, city/region, official event URL, and image URLs with available dimensions. Discovery results are catalog records; they are separate from `PriceObservation` and are not written as ticket-price observations.

## Get and configure a key

1. Create an account in the [Ticketmaster Developer Portal](https://developer.ticketmaster.com/) and register an application to obtain a Discovery API key. Ticketmaster says API access is available after registration in its [getting started guide](https://developer.ticketmaster.com/products-and-docs/apis/getting-started/).
2. Keep the key out of source control. Set it in the current shell, for example:

   ```sh
   export TICKETMASTER_API_KEY='your-key'
   ```

   On PowerShell, use `$env:TICKETMASTER_API_KEY = 'your-key'`. Do not commit `.env` files or paste the key into logs, issues, or screenshots. The adapter reads the environment variable when instantiated; tests use fake sessions and fixture files and make no network requests.
3. To explicitly make a read-only live request, run `python scripts/ticketmaster_smoke.py "artist or event"`. The script prints a few public event fields and never prints the key. With no key it exits without making a request.

The [Discovery API reference](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/) currently states a default public API quota of 5,000 requests/day and a rate limit. Ticketmaster's [FAQ](https://developer.ticketmaster.com/support/faq/) and API reference currently differ on the per-second limit (2 vs. 5 requests/second); honor `429` and `Retry-After` rather than relying on the higher figure. Search results can omit dates, venues, images, and URLs, so callers must handle missing fields.

## Pricing limitations and alert feasibility

The [Discovery API reference](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/) documents `priceRanges` as an event field containing a type, currency, minimum, and maximum. It does not document those values as individual live listings. The range does not provide listing identity, current purchasability, available quantity, section/row, fees per ticket, or a verified checkout total. A range can be stored as incomplete aggregate metadata, but must never be described as an actual purchasable listing or verified all-in price.

Reliable quantity-specific alerts still need an authorized source that returns current ticket-level offers with available quantity and a stable listing/offer identifier; fee and checkout totals (or an explicit inability to verify them); currency; event/provider identity; and terms permitting automated monitoring and alerts. The app also needs resilient polling, rate-limit/backoff handling, stale inventory handling, and deduplication. Discovery alone cannot establish that a specified number of seats is available below an all-in threshold.

### Free authorized source status

Verified for this proof of concept: Ticketmaster's public Discovery API is available with a developer API key and event search/metadata, including the documented event price range field. Not verified: any free, authorized API source that supplies quantity-specific, purchasable ticket listings and all-in prices suitable for ConScope alerts. The existing SeatGeek adapter remains explicitly gated on access approval and does not establish that such access is free or authorized for this use. No paid API, scraping, or unapproved source is included here.

## Scope

This is an isolated provider proof of concept. It does not add search UI, database persistence for discovered catalog records, a hosting migration, email, or deployment.
