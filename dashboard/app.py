#!/usr/bin/env python3
"""Local ConScope dashboard backed by SQLite and manual mock checks."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import plotly.graph_objects as go
import streamlit as st

# Streamlit may put dashboard/ rather than the repository root on sys.path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conscope_app.dashboard_data import (  # noqa: E402
    confidence_label,
    dashboard_snapshot,
    delete_event_after_confirmation,
    event_price_history,
    observation_is_stale,
    run_manual_mock_check,
)
from conscope_app.database import Database  # noqa: E402
from conscope_app.providers.mock import MockProvider  # noqa: E402
from conscope_app.providers.ticketmaster import search_ticketmaster_events  # noqa: E402


st.set_page_config(
    page_title="ConScope · Ticket Monitor",
    page_icon="🎟️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_resource
def get_database() -> Database:
    """Keep one repository object; Database opens a short-lived SQLite connection per operation."""
    return Database()


def _rerun() -> None:
    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun")
    rerun()


def _money(value, currency: str) -> str:
    if value is None:
        return "Not provided"
    return f"{currency} {float(value):,.2f}"


def _normalize_event_date(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise ValueError("Use an ISO date and time, such as 2027-04-18T19:30:00-04:00.") from exc


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def _record_notice(kind: str, message: str) -> None:
    st.session_state["notice"] = (kind, message)


def _show_notice() -> None:
    notice = st.session_state.pop("notice", None)
    if not notice:
        return
    kind, message = notice
    if kind == "success":
        st.success(message)
    elif kind == "error":
        st.error(message)
    else:
        st.info(message)


def _provider_label(key: str) -> str:
    return {
        "mock": "Mock sample · simulated",
        "ticketmaster": "Ticketmaster · disabled",
        "seatgeek": "SeatGeek · disabled",
    }.get(key, key.title())


def _ticketmaster_search(database: Database) -> None:
    """Render discovery and add-to-watchlist flow; Discovery is not monitoring."""
    st.subheader("Find an event to watch")
    st.caption("Search Ticketmaster event listings. Adding an event saves a watchlist target; live ticket checks and alerts are not enabled.")
    with st.form("ticketmaster_search_form"):
        keyword = st.text_input("Event, artist, or venue", placeholder="e.g. The Example Band")
        city = st.text_input("City (optional)", placeholder="e.g. New York")
        event_date = st.date_input("Event date (optional)", value=None)
        search = st.form_submit_button("Search events", type="primary", use_container_width=True)
    if search:
        if not keyword.strip():
            st.session_state.pop("ticketmaster_search_results", None)
            st.session_state["ticketmaster_search_error"] = "Enter an event, artist, or venue to search."
        else:
            result = search_ticketmaster_events(
                keyword,
                city=city or None,
                event_date=event_date.isoformat() if event_date else None,
            )
            if result.ok:
                st.session_state["ticketmaster_search_results"] = result.items
                st.session_state.pop("ticketmaster_search_error", None)
                st.session_state.pop("ticketmaster_selected_id", None)
            else:
                st.session_state.pop("ticketmaster_search_results", None)
                st.session_state["ticketmaster_search_error"] = result.failure

    error = st.session_state.get("ticketmaster_search_error")
    if error:
        if getattr(error, "code", None) == "missing_credentials":
            st.warning("Ticketmaster search needs an API key. Set TICKETMASTER_API_KEY in the shell used to launch Streamlit, then restart the dashboard.")
            st.caption("macOS/Linux: export TICKETMASTER_API_KEY='your-key' · PowerShell: $env:TICKETMASTER_API_KEY = 'your-key'")
        elif isinstance(error, str):
            st.warning(error)
        else:
            st.error(f"Ticketmaster search failed ({error.code}): {error.message}")

    results = st.session_state.get("ticketmaster_search_results")
    if results is not None:
        if not results:
            st.info("No matching events were found. Try another keyword or a broader location/date.")
            return
        st.markdown(f"**{len(results)} event result(s)**")
        for index, event in enumerate(results):
            st.markdown("---")
            st.markdown(f"**{event.name}**")
            st.write(f"Date: {event.event_date or 'Not provided'}")
            st.write(f"Venue: {event.venue or 'Not provided'}")
            location = ", ".join(part for part in (event.city, event.region) if part) or "Not provided"
            st.write(f"Location: {location}")
            if event.images:
                st.image(event.images[0].url, width=300)
            if event.url and _safe_url(event.url):
                st.link_button("Open official event page", event.url, use_container_width=True)
            if st.button("Select this event", key=f"select_ticketmaster_{event.provider_id}", use_container_width=True):
                st.session_state["ticketmaster_selected_id"] = event.provider_id

        selected = next((item for item in results if item.provider_id == st.session_state.get("ticketmaster_selected_id")), None)
        if selected:
            st.markdown("---")
            st.markdown(f"#### Add **{selected.name}** to your watchlist")
            st.caption("This stores your target only. No Ticketmaster ticket inventory is checked and no alert will be sent.")
            with st.form("track_discovered_event_form"):
                quantity = st.number_input("Desired ticket quantity", min_value=1, max_value=20, value=2, step=1)
                st.caption("Target currency: USD")
                maximum_price = st.number_input("Maximum target price per ticket (USD)", min_value=0.01, value=200.0, step=5.0)
                add = st.form_submit_button("Add to watchlist", type="primary", use_container_width=True)
            if add:
                try:
                    database.add_discovered_event(
                        selected, ticket_quantity=int(quantity), maximum_price=maximum_price, currency="USD",
                    )
                    _record_notice("success", f"Added {selected.name} to your watchlist. Ticket monitoring and alerts remain inactive.")
                    st.session_state.pop("ticketmaster_search_results", None)
                    st.session_state.pop("ticketmaster_selected_id", None)
                    _rerun()
                except ValueError as exc:
                    st.warning(str(exc))
                except sqlite3.Error:
                    st.error("Could not save this event to the local database. Please try again.")


def _provider_input(provider_key: str, *, key_prefix: str, current: dict | None = None):
    current = current or {}
    if provider_key == "mock":
        samples = MockProvider.EVENTS
        current_id = current.get("provider_event_id")
        selected_index = next((i for i, sample in enumerate(samples) if sample.event_id == current_id), 0)
        sample = st.selectbox(
            "Sample event",
            samples,
            index=selected_index,
            format_func=lambda item: f"{item.name} · {item.venue}",
            key=f"{key_prefix}_mock_event",
        )
        provider_event_id = sample.event_id
        event_url = sample.url
        return sample, provider_event_id, event_url

    if provider_key == "seatgeek":
        st.warning("SeatGeek remains disabled until API access and permission for price monitoring are verified.")
    else:
        st.info("Ticketmaster live checks are not enabled in this version. Its event price ranges are aggregate only.")
    current_reference = current.get("provider_event_id", "")
    reference = st.text_input(
        "Provider event ID or event URL",
        value=current_reference,
        key=f"{key_prefix}_provider_reference",
        help="This is saved for later setup. No live request will be made.",
    ).strip()
    current_url = current.get("event_url")
    if reference.startswith(("https://", "http://")):
        event_url = reference
        path_id = urlparse(reference).path.rstrip("/").split("/")[-1]
        provider_event_id = path_id or reference
    else:
        provider_event_id = reference
        event_url = st.text_input(
            "Event page link (optional)",
            value=current_url or "",
            key=f"{key_prefix}_event_url",
        ).strip() or None
    return None, provider_event_id, event_url


def _add_event_form(database: Database) -> None:
    with st.expander("Advanced: add an event manually", expanded=False):
        provider_key = st.selectbox(
            "Ticket source",
            ("mock", "ticketmaster", "seatgeek"),
            format_func=_provider_label,
            key="new_provider_key",
        )
        sample, provider_event_id, event_url = _provider_input(provider_key, key_prefix="new")
        with st.form("create_event_form", clear_on_submit=False):
            name = st.text_input("Event name", value=sample.name if sample else "")
            venue = st.text_input("Venue", value=sample.venue if sample else "")
            event_date = st.text_input("Event date and time (optional)", value=sample.event_date if sample else "", placeholder="2027-04-18T19:30:00-04:00")
            quantity = st.number_input("Tickets wanted", min_value=1, max_value=20, value=2, step=1)
            currency = st.text_input("Currency", value="USD", max_chars=3)
            maximum_price = st.number_input("Maximum price per ticket", min_value=0.01, value=200.0, step=5.0)
            alert_enabled = st.checkbox("Alert target active", value=True)
            allow_estimated = st.checkbox("Allow estimated prices to match this target", value=False)
            submitted = st.form_submit_button("Add tracked event", type="primary", use_container_width=True)
        if submitted:
            try:
                if not name.strip():
                    raise ValueError("Enter an event name.")
                if not provider_event_id.strip():
                    raise ValueError("Choose a sample event or enter a provider event ID or URL.")
                database.add_event(
                    name,
                    venue=venue,
                    event_date=_normalize_event_date(event_date),
                    ticket_quantity=int(quantity),
                    maximum_price=maximum_price,
                    currency=currency,
                    providers=[{
                        "provider_key": provider_key,
                        "display_name": _provider_label(provider_key).split(" ·")[0],
                        "provider_event_id": provider_event_id,
                        "event_url": event_url,
                    }],
                    alert_enabled=alert_enabled,
                    allow_estimated_prices=allow_estimated,
                )
                _record_notice("success", f"Added {name.strip()} to your watch list.")
                _rerun()
            except (ValueError, sqlite3.Error) as exc:
                st.error(f"Could not add the event: {exc}")


def _edit_event_form(database: Database, event: dict) -> None:
    links = event.get("providers", [])
    current = links[0] if links else None
    current_key = current.get("provider_key", "mock") if current else "mock"
    provider_key = st.selectbox(
        "Ticket source",
        ("mock", "ticketmaster", "seatgeek"),
        index=("mock", "ticketmaster", "seatgeek").index(current_key) if current_key in ("mock", "ticketmaster", "seatgeek") else 0,
        format_func=_provider_label,
        key=f"edit_provider_{event['id']}",
    )
    sample, provider_event_id, event_url = _provider_input(
        provider_key,
        key_prefix=f"edit_{event['id']}",
        current=current if current_key == provider_key else None,
    )
    with st.form(f"edit_event_form_{event['id']}"):
        name = st.text_input("Event name", value=event["name"])
        venue = st.text_input("Venue", value=event["venue"])
        event_date = st.text_input("Event date and time", value=event.get("event_date") or "")
        quantity = st.number_input("Tickets wanted", min_value=1, max_value=20, value=int(event["ticket_quantity"]), step=1)
        currency = st.text_input("Currency", value=event["currency"], max_chars=3)
        maximum_price = st.number_input("Maximum price per ticket", min_value=0.01, value=float(event["maximum_price"]), step=5.0)
        alert_enabled = st.checkbox("Alert target active", value=bool(event["alert_enabled"]))
        allow_estimated = st.checkbox("Allow estimated prices to match this target", value=bool(event["allow_estimated_prices"]))
        submitted = st.form_submit_button("Save changes", type="primary", use_container_width=True)
    if submitted:
        try:
            if not name.strip():
                raise ValueError("Enter an event name.")
            if not provider_event_id.strip():
                raise ValueError("A provider event ID or URL is required.")
            database.update_event(
                event["id"],
                name=name,
                venue=venue,
                event_date=_normalize_event_date(event_date),
                ticket_quantity=int(quantity),
                currency=currency,
                maximum_price=maximum_price,
                alert_enabled=alert_enabled,
                allow_estimated_prices=allow_estimated,
                providers=[{
                    "provider_key": provider_key,
                    "display_name": _provider_label(provider_key).split(" ·")[0],
                    "provider_event_id": provider_event_id,
                    "event_url": event_url,
                }],
            )
            _record_notice("success", f"Saved changes to {name.strip()}.")
            _rerun()
        except (ValueError, sqlite3.Error) as exc:
            st.error(f"Could not save changes: {exc}")


def _display_history(database: Database, event: dict) -> None:
    history = event_price_history(database, event["id"])
    listings = history["listings"]
    ranges = history["ranges"]
    st.markdown("#### Ticket listings")
    if listings:
        rows = []
        for item in listings:
            confidence = confidence_label(item["pricing_confidence"], item["source"])
            if item["available_quantity"] is None:
                availability = "Not reported"
            elif item["available_quantity"] < event["ticket_quantity"]:
                availability = f"{item['available_quantity']} · below target of {event['ticket_quantity']}"
            else:
                availability = f"{item['available_quantity']} available"
            if item["pricing_confidence"] == "verified_all_in":
                total_label = "Verified all-in total"
            elif item["total_per_ticket"] is not None:
                total_label = "Estimated total"
            else:
                total_label = "Total price"
            rows.append({
                "Source": _provider_label(item["source"]).split(" ·")[0],
                "Base price / ticket": _money(item["price_per_ticket"], item["currency"]),
                "Known fees / ticket": _money(item["fees_per_ticket"], item["currency"]),
                total_label: _money(item["total_per_ticket"], item["currency"]) if item["total_per_ticket"] is not None else "Not provided",
                "Available tickets": availability,
                "Confidence": confidence,
                "Observed": item["observed_at"],
                "Stale": "Yes" if observation_is_stale(item["observed_at"]) else "No",
                "Section / row": " / ".join(part for part in (item.get("section"), item.get("row_label")) if part) or "Not reported",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
        for index, item in enumerate(listings):
            listing_url = _safe_url(item.get("listing_url"))
            if listing_url:
                st.link_button(f"Open {item.get('source', 'ticket')} listing {index + 1}", listing_url)
        figure = go.Figure()
        for source in sorted({item["source"] for item in listings}):
            selected = [item for item in listings if item["source"] == source and item["currency"] == event["currency"]]
            figure.add_trace(go.Scatter(
                x=[item["observed_at"] for item in selected],
                y=[item["price_per_ticket"] for item in selected],
                mode="lines+markers",
                name=_provider_label(source),
                customdata=[confidence_label(item["pricing_confidence"], source) for item in selected],
                hovertemplate="%{x}<br>%{y:.2f} " + event["currency"] + "<br>%{customdata}<extra></extra>",
            ))
        figure.update_layout(
            title=f"Observed base price per ticket · {event['currency']}",
            xaxis_title="Check time",
            yaxis_title=f"Price ({event['currency']})",
            height=330,
            margin=dict(l=20, r=20, t=55, b=20),
            legend_title="Source",
        )
        st.plotly_chart(figure, use_container_width=True)
    else:
        st.info("No ticket listings have been recorded. Run a manual mock check on a mock event to populate sample history.")

    if ranges:
        st.markdown("#### Event-level ranges")
        st.warning("These are broad event price ranges, not individual listings. They do not confirm that a ticket is currently purchasable or available in your quantity.")
        range_rows = [{
            "Source": _provider_label(item["source"]).split(" ·")[0],
            "Range type": item["range_label"],
            "Minimum": _money(item["range_min_price"], item["currency"]),
            "Maximum": _money(item["range_max_price"], item["currency"]),
            "Confidence": confidence_label(item["pricing_confidence"], item["source"], "aggregate_price_range"),
            "Observed": item["observed_at"],
        } for item in ranges]
        st.dataframe(range_rows, use_container_width=True, hide_index=True)
        for index, item in enumerate(ranges):
            event_url = _safe_url(item.get("event_url"))
            if event_url:
                st.link_button(f"Open {item['source']} event page {index + 1}", event_url)


def _event_card(database: Database, card: dict) -> None:
    event = card["event"]
    suffix = " · paused" if event["is_paused"] else ""
    with st.expander(f"{event['name']}{suffix}", expanded=False):
        date_text = event.get("event_date") or "Date not set"
        venue_text = event.get("venue") or "Venue not set"
        st.caption(f"{venue_text} · {date_text}")
        left, mid, right = st.columns(3)
        left.metric("Ticket target", f"{event['ticket_quantity']} tickets")
        mid.metric("Maximum per ticket", _money(event["maximum_price"], event["currency"]))
        lowest = card["lowest_observation"]
        right.metric("Lowest observed base", _money(lowest["price_per_ticket"], event["currency"]) if lowest else "—")
        if lowest:
            st.caption(
                f"{confidence_label(lowest['pricing_confidence'], lowest['source'])} · "
                f"quantity {lowest['available_quantity'] if lowest['available_quantity'] is not None else 'not reported'} · "
                f"{lowest['observed_at']}"
            )
        if card["latest_observation_stale"]:
            st.warning("The latest listing observation is stale (more than 24 hours old). No scheduled checks are running.")

        if card["providers"]:
            for provider in card["providers"]:
                st.caption(f"{provider['display_name']}: {provider['status_label']}")
                if provider.get("last_error") and provider["provider_key"] != "mock":
                    st.error(provider["last_error"])
        else:
            st.info("No provider link is configured.")

        tabs = st.tabs(("Price history", "Edit event", "Actions"))
        with tabs[0]:
            _display_history(database, event)
        with tabs[1]:
            _edit_event_form(database, event)
        with tabs[2]:
            action_columns = st.columns(3)
            if event["is_paused"]:
                if action_columns[0].button("Resume monitoring", key=f"resume_{event['id']}", use_container_width=True):
                    database.resume_event(event["id"])
                    _record_notice("success", f"Resumed {event['name']}.")
                    _rerun()
            elif action_columns[0].button("Pause monitoring", key=f"pause_{event['id']}", use_container_width=True):
                database.pause_event(event["id"])
                _record_notice("info", f"Paused {event['name']}.")
                _rerun()

            is_mock = any(provider["provider_key"] == "mock" for provider in event.get("providers", []))
            if is_mock:
                if action_columns[1].button(
                    "Check sample prices now",
                    key=f"mock_check_{event['id']}",
                    disabled=bool(event["is_paused"]),
                    use_container_width=True,
                ):
                    result = run_manual_mock_check(database, event["id"])
                    if result.failure:
                        _record_notice("error", result.failure.message)
                    else:
                        _record_notice("success", f"Saved {len(result.observation_ids)} simulated price observations.")
                    _rerun()
            else:
                action_columns[1].button(
                    "Live check unavailable",
                    key=f"disabled_check_{event['id']}",
                    disabled=True,
                    use_container_width=True,
                    help="Live provider checks are not enabled.",
                )

            if action_columns[2].button("Delete event…", key=f"delete_{event['id']}", use_container_width=True):
                st.session_state["confirm_delete_event"] = event["id"]
            if st.session_state.get("confirm_delete_event") == event["id"]:
                st.warning(f"Delete {event['name']} and its saved price history? This cannot be undone.")
                confirm, cancel = st.columns(2)
                if confirm.button("Confirm delete", key=f"confirm_delete_{event['id']}", type="primary"):
                    if delete_event_after_confirmation(database, event["id"], confirmed=True):
                        st.session_state.pop("confirm_delete_event", None)
                        _record_notice("success", f"Deleted {event['name']} and its saved history.")
                        _rerun()
                if cancel.button("Keep event", key=f"cancel_delete_{event['id']}"):
                    st.session_state.pop("confirm_delete_event", None)
                    _rerun()


def main() -> None:
    database = get_database()
    st.title("🎟️ ConScope")
    st.caption("Your local ticket watch list")
    st.info("Local-only dashboard. No live ticket checks or email alerts are running. Mock checks below use simulated sample prices.")
    _show_notice()

    snapshot = dashboard_snapshot(database)
    summary = st.columns(4)
    summary[0].metric("Watched events", snapshot["watched_events"])
    summary[1].metric("Active alerts", snapshot["active_alerts"])
    summary[2].metric("Events with prices", snapshot["events_with_prices"])
    if snapshot["latest_success"]:
        summary[3].metric("Last successful check", snapshot["latest_success"][:19].replace("T", " "))
    else:
        summary[3].metric("Last successful check", "Never")
    st.caption("Active alerts are saved price targets. Email notifications are not part of this phase.")

    st.subheader("Lowest observed listing prices")
    lowest_rows = []
    for card in snapshot["events"]:
        event = card["event"]
        item = card["lowest_observation"]
        lowest_rows.append({
            "Event": event["name"],
            "Lowest base price": _money(item["price_per_ticket"], item["currency"]) if item else "No listing yet",
            "Source": _provider_label(item["source"]) if item else "—",
            "Pricing": confidence_label(item["pricing_confidence"], item["source"]) if item else "—",
            "Target": _money(event["maximum_price"], event["currency"]),
            "Last successful check": card["latest_success"] or "Never",
        })
    if lowest_rows:
        st.dataframe(lowest_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No events yet. Add an event to start your local watch list.")

    _ticketmaster_search(database)
    _add_event_form(database)
    st.subheader("Watched events")
    if snapshot["events"]:
        for card in snapshot["events"]:
            _event_card(database, card)
    else:
        st.caption("Your event details and price history will appear here.")

    st.caption(f"Data file: {database.path}")


if __name__ == "__main__":
    main()
