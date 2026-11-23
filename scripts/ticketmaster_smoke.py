"""Explicit, read-only Ticketmaster Discovery API smoke test."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conscope_app.providers.ticketmaster import search_ticketmaster_events


def main() -> int:
    if not os.environ.get("TICKETMASTER_API_KEY"):
        print("TICKETMASTER_API_KEY is not set; no request made.", file=sys.stderr)
        return 2
    query = " ".join(sys.argv[1:]).strip() or "concert"
    result = search_ticketmaster_events(query)
    if not result.ok:
        print(f"Search failed: {result.failure.code}: {result.failure.message}", file=sys.stderr)
        return 1
    print(f"Found {len(result.items)} event(s) for {query!r}.")
    for event in result.items[:5]:
        when = event.event_date or "Date not provided"
        where = ", ".join(part for part in (event.venue, event.city, event.region) if part) or "Location not provided"
        print(f"- {event.name} | {when} | {where} | {event.url or 'No event URL'} | id={event.provider_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
