"""SQLite persistence for the local ConScope application.

Each operation uses its own short-lived connection. The database file is stored
outside the installation directory so application upgrades and uninstalling do
not implicitly remove user data.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import math
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterable, Iterator, Mapping
import uuid


CURRENT_SCHEMA_VERSION = 6


def default_data_directory() -> Path:
    """Return the conventional per-user application data directory."""
    override = os.environ.get("CONSCOPE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "ConScope"
        return Path.home() / "AppData" / "Local" / "ConScope"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ConScope"
    root = os.environ.get("XDG_DATA_HOME")
    return (Path(root) if root else Path.home() / ".local" / "share") / "conscope"


def _validate_price(value: float | None, field: str, *, required: bool = False) -> float | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field} must be a finite positive amount")
    return value


def _validate_currency(currency: str) -> str:
    currency = str(currency).strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code")
    return currency


def _validate_quantity(quantity: int) -> int:
    if isinstance(quantity, bool) or int(quantity) != quantity or int(quantity) < 1:
        raise ValueError("ticket_quantity must be a positive integer")
    return int(quantity)


class Database:
    """Versioned SQLite data layer for tracked events and price monitoring."""

    def __init__(self, path: str | os.PathLike[str] | None = None, *, data_dir: str | os.PathLike[str] | None = None):
        if path is not None and data_dir is not None:
            raise ValueError("pass either path or data_dir, not both")
        if path is not None:
            self.path = Path(path).expanduser()
        else:
            self.path = Path(data_dir).expanduser() / "conscope.sqlite3" if data_dir is not None else default_data_directory() / "conscope.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level="DEFERRED")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _migration_1(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            CREATE TABLE tracked_events (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                venue TEXT NOT NULL DEFAULT '',
                event_date TEXT,
                ticket_quantity INTEGER NOT NULL CHECK (ticket_quantity >= 1),
                maximum_price REAL NOT NULL CHECK (maximum_price > 0),
                currency TEXT NOT NULL CHECK (length(currency) = 3),
                is_paused INTEGER NOT NULL DEFAULT 0 CHECK (is_paused IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE providers (
                id INTEGER PRIMARY KEY,
                provider_key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL
            );
            CREATE TABLE event_providers (
                id INTEGER PRIMARY KEY,
                tracked_event_id TEXT NOT NULL REFERENCES tracked_events(id) ON DELETE CASCADE,
                provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
                provider_event_id TEXT NOT NULL,
                event_url TEXT,
                UNIQUE (id, tracked_event_id),
                UNIQUE (tracked_event_id, provider_id, provider_event_id)
            );
            CREATE TABLE check_status (
                event_provider_id INTEGER PRIMARY KEY REFERENCES event_providers(id) ON DELETE CASCADE,
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error TEXT,
                next_check_at TEXT
            );
            CREATE TABLE price_observations (
                id INTEGER PRIMARY KEY,
                tracked_event_id TEXT NOT NULL REFERENCES tracked_events(id) ON DELETE CASCADE,
                event_provider_id INTEGER REFERENCES event_providers(id) ON DELETE SET NULL,
                listing_id TEXT,
                listing_url TEXT,
                section TEXT,
                row_label TEXT,
                price_per_ticket REAL NOT NULL CHECK (price_per_ticket > 0),
                fees_per_ticket REAL CHECK (fees_per_ticket IS NULL OR fees_per_ticket >= 0),
                total_per_ticket REAL CHECK (total_per_ticket IS NULL OR total_per_ticket > 0),
                currency TEXT NOT NULL CHECK (length(currency) = 3),
                available_quantity INTEGER CHECK (available_quantity IS NULL OR available_quantity >= 1),
                pricing_confidence TEXT NOT NULL CHECK (pricing_confidence IN ('verified_all_in', 'estimated', 'incomplete')),
                observed_at TEXT NOT NULL,
                UNIQUE (id, tracked_event_id),
                FOREIGN KEY (event_provider_id, tracked_event_id)
                    REFERENCES event_providers(id, tracked_event_id)
            );
            CREATE INDEX idx_price_observations_event_time
                ON price_observations(tracked_event_id, observed_at);
            PRAGMA user_version = 1;
            COMMIT;
            """
        )

    @staticmethod
    def _migration_2(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            CREATE TABLE alert_settings (
                tracked_event_id TEXT PRIMARY KEY REFERENCES tracked_events(id) ON DELETE CASCADE,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                allow_estimated_prices INTEGER NOT NULL DEFAULT 0 CHECK (allow_estimated_prices IN (0, 1)),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            INSERT INTO alert_settings (tracked_event_id)
                SELECT id FROM tracked_events;
            CREATE TABLE notification_deduplication (
                id INTEGER PRIMARY KEY,
                tracked_event_id TEXT NOT NULL REFERENCES tracked_events(id) ON DELETE CASCADE,
                deduplication_key TEXT NOT NULL,
                observation_id INTEGER REFERENCES price_observations(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE (tracked_event_id, deduplication_key),
                FOREIGN KEY (observation_id, tracked_event_id)
                    REFERENCES price_observations(id, tracked_event_id)
            );
            CREATE INDEX idx_notifications_status ON notification_deduplication(status);
            PRAGMA user_version = 2;
            COMMIT;
            """
        )

    @staticmethod
    def _migration_3(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            ALTER TABLE price_observations ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown';
            UPDATE price_observations
            SET source = COALESCE((
                SELECT p.provider_key
                FROM event_providers ep JOIN providers p ON p.id = ep.provider_id
                WHERE ep.id = price_observations.event_provider_id
            ), 'unknown');
            CREATE TABLE aggregate_price_ranges (
                id INTEGER PRIMARY KEY,
                tracked_event_id TEXT NOT NULL REFERENCES tracked_events(id) ON DELETE CASCADE,
                event_provider_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                provider_event_id TEXT NOT NULL,
                range_label TEXT NOT NULL,
                range_min_price REAL NOT NULL CHECK (range_min_price > 0),
                range_max_price REAL NOT NULL CHECK (range_max_price >= range_min_price),
                currency TEXT NOT NULL CHECK (length(currency) = 3),
                event_url TEXT,
                observed_at TEXT NOT NULL,
                pricing_confidence TEXT NOT NULL DEFAULT 'incomplete' CHECK (pricing_confidence = 'incomplete'),
                FOREIGN KEY (event_provider_id, tracked_event_id)
                    REFERENCES event_providers(id, tracked_event_id)
            );
            CREATE INDEX idx_aggregate_ranges_event_time
                ON aggregate_price_ranges(tracked_event_id, observed_at);
            PRAGMA user_version = 3;
            COMMIT;
            """
        )

    @staticmethod
    def _migration_4(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            ALTER TABLE tracked_events ADD COLUMN city TEXT;
            ALTER TABLE tracked_events ADD COLUMN region TEXT;
            ALTER TABLE tracked_events ADD COLUMN images_json TEXT NOT NULL DEFAULT '[]';
            PRAGMA user_version = 4;
            COMMIT;
            """
        )

    @staticmethod
    def _migration_5(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            CREATE TABLE monitor_alert_state (
                tracked_event_id TEXT PRIMARY KEY REFERENCES tracked_events(id) ON DELETE CASCADE,
                armed INTEGER NOT NULL DEFAULT 1 CHECK (armed IN (0, 1)),
                cycle_number INTEGER NOT NULL DEFAULT 1 CHECK (cycle_number >= 1),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            INSERT INTO monitor_alert_state (tracked_event_id)
                SELECT id FROM tracked_events;
            CREATE TABLE monitor_alert_records (
                id INTEGER PRIMARY KEY,
                tracked_event_id TEXT NOT NULL REFERENCES tracked_events(id) ON DELETE CASCADE,
                event_provider_id INTEGER NOT NULL,
                observation_id INTEGER NOT NULL,
                cycle_number INTEGER NOT NULL CHECK (cycle_number >= 1),
                simulation_only INTEGER NOT NULL CHECK (simulation_only IN (0, 1)),
                total_per_ticket REAL NOT NULL CHECK (total_per_ticket > 0),
                currency TEXT NOT NULL CHECK (length(currency) = 3),
                available_quantity INTEGER NOT NULL CHECK (available_quantity >= 1),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE (tracked_event_id, cycle_number),
                FOREIGN KEY (event_provider_id, tracked_event_id)
                    REFERENCES event_providers(id, tracked_event_id),
                FOREIGN KEY (observation_id, tracked_event_id)
                    REFERENCES price_observations(id, tracked_event_id)
            );
            CREATE INDEX idx_monitor_alert_records_created
                ON monitor_alert_records(created_at, id);
            PRAGMA user_version = 5;
            COMMIT;
            """
        )

    @staticmethod
    def _migration_6(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            BEGIN EXCLUSIVE;
            CREATE TABLE email_notification_outbox (
                id INTEGER PRIMARY KEY,
                monitor_alert_record_id INTEGER NOT NULL REFERENCES monitor_alert_records(id) ON DELETE CASCADE,
                recipient_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'retryable')),
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                idempotency_key TEXT NOT NULL UNIQUE,
                provider_message_id TEXT,
                available_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                first_attempt_at TEXT,
                claimed_at TEXT,
                claim_token TEXT,
                delivery_uncertain INTEGER NOT NULL DEFAULT 0 CHECK (delivery_uncertain IN (0, 1)),
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                sent_at TEXT,
                UNIQUE (monitor_alert_record_id, recipient_email),
                CHECK ((status = 'sending' AND claim_token IS NOT NULL AND claimed_at IS NOT NULL) OR status != 'sending')
            );
            CREATE INDEX idx_email_outbox_due
                ON email_notification_outbox(status, available_at, created_at);
            PRAGMA user_version = 6;
            COMMIT;
            """
        )

    def migrate(self, target_version: int = CURRENT_SCHEMA_VERSION) -> None:
        """Apply pending schema migrations, or migrate to a test target version."""
        if target_version < 0 or target_version > CURRENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version: {target_version}")
        with self._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > CURRENT_SCHEMA_VERSION:
                raise RuntimeError(f"database schema {version} is newer than supported schema {CURRENT_SCHEMA_VERSION}")
            migrations = {1: self._migration_1, 2: self._migration_2, 3: self._migration_3, 4: self._migration_4, 5: self._migration_5, 6: self._migration_6}
            while version < target_version:
                migrations[version + 1](conn)
                version = conn.execute("PRAGMA user_version").fetchone()[0]

    @property
    def schema_version(self) -> int:
        with self._connection() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def add_event(
        self,
        name: str,
        *,
        venue: str = "",
        event_date: str | None = None,
        city: str | None = None,
        region: str | None = None,
        images: Iterable[Mapping[str, Any]] = (),
        ticket_quantity: int = 1,
        maximum_price: float,
        currency: str = "USD",
        providers: Iterable[Mapping[str, Any]] = (),
        alert_enabled: bool = True,
        allow_estimated_prices: bool = False,
    ) -> dict[str, Any]:
        name = str(name).strip()
        if not name:
            raise ValueError("name is required")
        quantity = _validate_quantity(ticket_quantity)
        maximum_price = _validate_price(maximum_price, "maximum_price", required=True)
        currency = _validate_currency(currency)
        image_values = [dict(image) for image in images]
        event_id = str(uuid.uuid4())
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO tracked_events (id, name, venue, event_date, ticket_quantity, maximum_price, currency, city, region, images_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, name, venue.strip(), event_date, quantity, maximum_price, currency, city, region, json.dumps(image_values)),
            )
            conn.execute(
                "INSERT INTO alert_settings (tracked_event_id, enabled, allow_estimated_prices) VALUES (?, ?, ?)",
                (event_id, int(bool(alert_enabled)), int(bool(allow_estimated_prices))),
            )
            self._replace_providers(conn, event_id, providers)
        return self.get_event(event_id)  # type: ignore[return-value]

    def add_discovered_event(self, discovered_event: Any, *, ticket_quantity: int, maximum_price: float, currency: str = "USD") -> dict[str, Any]:
        """Track a normalized discovery result without creating price observations."""
        source = str(discovered_event.source).strip().lower()
        provider_event_id = str(discovered_event.provider_id).strip()
        name = str(discovered_event.name).strip()
        if not source or not provider_event_id or not name:
            raise ValueError("A discovered event must include its provider, ID, and name.")
        quantity = _validate_quantity(ticket_quantity)
        maximum_price = _validate_price(maximum_price, "maximum_price", required=True)
        currency = _validate_currency(currency)
        images = [{"url": image.url, "width": image.width, "height": image.height, "ratio": image.ratio} for image in discovered_event.images]
        tracked_event_id = str(uuid.uuid4())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute(
                "SELECT e.id FROM event_providers ep JOIN providers p ON p.id = ep.provider_id JOIN tracked_events e ON e.id = ep.tracked_event_id WHERE p.provider_key = ? AND ep.provider_event_id = ?",
                (source, provider_event_id),
            ).fetchone()
            if duplicate:
                raise ValueError("This event is already in your watchlist.")
            conn.execute(
                "INSERT INTO tracked_events (id, name, venue, event_date, ticket_quantity, maximum_price, currency, city, region, images_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tracked_event_id, name, discovered_event.venue or "", discovered_event.event_date, quantity,
                 maximum_price, currency, discovered_event.city, discovered_event.region, json.dumps(images)),
            )
            conn.execute(
                "INSERT INTO alert_settings (tracked_event_id, enabled, allow_estimated_prices) VALUES (?, 0, 0)",
                (tracked_event_id,),
            )
            self._replace_providers(conn, tracked_event_id, [{
                "provider_key": source,
                "display_name": "Ticketmaster" if source == "ticketmaster" else source.title(),
                "provider_event_id": provider_event_id,
                "event_url": discovered_event.url,
            }])
        return self.get_event(tracked_event_id)  # type: ignore[return-value]

    def _replace_providers(self, conn: sqlite3.Connection, event_id: str, providers: Iterable[Mapping[str, Any]]) -> None:
        providers = list(providers)
        normalized = []
        for provider in providers:
            key = str(provider["provider_key"]).strip().lower()
            display_name = str(provider.get("display_name") or key).strip()
            provider_event_id = str(provider["provider_event_id"]).strip()
            if not key or not display_name or not provider_event_id:
                raise ValueError("provider_key, display_name, and provider_event_id are required")
            conn.execute(
                "INSERT INTO providers (provider_key, display_name) VALUES (?, ?) ON CONFLICT(provider_key) DO UPDATE SET display_name = excluded.display_name",
                (key, display_name),
            )
            provider_id = conn.execute("SELECT id FROM providers WHERE provider_key = ?", (key,)).fetchone()[0]
            normalized.append((provider_id, provider_event_id, provider.get("event_url")))

        existing = conn.execute(
            "SELECT id, provider_id, provider_event_id, event_url FROM event_providers WHERE tracked_event_id = ? ORDER BY id",
            (event_id,),
        ).fetchall()
        # The dashboard edits a single provider association in place so its
        # check-status row and historical observations remain attached.
        if len(existing) == 1 and len(normalized) == 1:
            row = existing[0]
            provider_id, provider_event_id, event_url = normalized[0]
            changed = row[1] != provider_id or row[2] != provider_event_id
            conn.execute(
                "UPDATE event_providers SET provider_id = ?, provider_event_id = ?, event_url = ? WHERE id = ?",
                (provider_id, provider_event_id, event_url, row[0]),
            )
            if changed:
                conn.execute(
                    "UPDATE check_status SET last_attempt_at = NULL, last_success_at = NULL, last_error = NULL, next_check_at = NULL WHERE event_provider_id = ?",
                    (row[0],),
                )
            return

        for provider, (provider_id, provider_event_id, event_url) in zip(providers, normalized):
            conn.execute(
                "INSERT INTO event_providers (tracked_event_id, provider_id, provider_event_id, event_url) VALUES (?, ?, ?, ?) ON CONFLICT(tracked_event_id, provider_id, provider_event_id) DO UPDATE SET event_url = excluded.event_url",
                (event_id, provider_id, provider_event_id, event_url),
            )
            event_provider_id = conn.execute(
                "SELECT id FROM event_providers WHERE tracked_event_id = ? AND provider_id = ? AND provider_event_id = ?",
                (event_id, provider_id, provider_event_id),
            ).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO check_status (event_provider_id) VALUES (?)", (event_provider_id,))

    def update_event(self, event_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"name", "venue", "event_date", "city", "region", "images", "ticket_quantity", "maximum_price", "currency", "providers", "alert_enabled", "allow_estimated_prices"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported event fields: {', '.join(sorted(unknown))}")
        if "name" in fields:
            fields["name"] = str(fields["name"]).strip()
            if not fields["name"]:
                raise ValueError("name is required")
        if "ticket_quantity" in fields:
            fields["ticket_quantity"] = _validate_quantity(fields["ticket_quantity"])
        if "maximum_price" in fields:
            fields["maximum_price"] = _validate_price(fields["maximum_price"], "maximum_price", required=True)
        if "currency" in fields:
            fields["currency"] = _validate_currency(fields["currency"])
        with self._connection() as conn:
            if conn.execute("SELECT 1 FROM tracked_events WHERE id = ?", (event_id,)).fetchone() is None:
                raise KeyError(event_id)
            updates = {key: value for key, value in fields.items() if key in {"name", "venue", "event_date", "city", "region", "ticket_quantity", "maximum_price", "currency"}}
            if "images" in fields:
                updates["images_json"] = json.dumps(fields["images"])
            if updates:
                updates["updated_at"] = "__now__"
                assignments = ", ".join(f"{key} = ?" if value != "__now__" else "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')" for key, value in updates.items())
                values = [value for value in updates.values() if value != "__now__"]
                conn.execute(f"UPDATE tracked_events SET {assignments} WHERE id = ?", (*values, event_id))
            if "providers" in fields:
                self._replace_providers(conn, event_id, fields["providers"])
            alert_fields = {key: fields[key] for key in ("alert_enabled", "allow_estimated_prices") if key in fields}
            if alert_fields:
                current = conn.execute("SELECT enabled, allow_estimated_prices FROM alert_settings WHERE tracked_event_id = ?", (event_id,)).fetchone()
                enabled = int(bool(alert_fields.get("alert_enabled", current[0])))
                estimates = int(bool(alert_fields.get("allow_estimated_prices", current[1])))
                conn.execute(
                    "UPDATE alert_settings SET enabled = ?, allow_estimated_prices = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE tracked_event_id = ?",
                    (enabled, estimates, event_id),
                )
        return self.get_event(event_id)  # type: ignore[return-value]

    def set_paused(self, event_id: str, paused: bool) -> dict[str, Any]:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE tracked_events SET is_paused = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (int(bool(paused)), event_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(event_id)
        return self.get_event(event_id)  # type: ignore[return-value]

    def pause_event(self, event_id: str) -> dict[str, Any]:
        return self.set_paused(event_id, True)

    def resume_event(self, event_id: str) -> dict[str, Any]:
        return self.set_paused(event_id, False)

    def delete_event(self, event_id: str) -> bool:
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM tracked_events WHERE id = ?", (event_id,))
            return cursor.rowcount == 1

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT e.*, a.enabled AS alert_enabled, a.allow_estimated_prices FROM tracked_events e LEFT JOIN alert_settings a ON a.tracked_event_id = e.id WHERE e.id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            try:
                result["images"] = json.loads(result.pop("images_json", "[]"))
            except (TypeError, ValueError):
                result["images"] = []
            result["providers"] = self._get_providers(conn, event_id)
            return result

    @staticmethod
    def _get_providers(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT ep.id AS event_provider_id, p.provider_key, p.display_name, ep.provider_event_id, ep.event_url, cs.last_attempt_at, cs.last_success_at, cs.last_error, cs.next_check_at FROM event_providers ep JOIN providers p ON p.id = ep.provider_id LEFT JOIN check_status cs ON cs.event_provider_id = ep.id WHERE ep.tracked_event_id = ? ORDER BY ep.id",
            (event_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_events(self, *, include_paused: bool = True) -> list[dict[str, Any]]:
        with self._connection() as conn:
            query = "SELECT id FROM tracked_events"
            if not include_paused:
                query += " WHERE is_paused = 0"
            query += " ORDER BY created_at, id"
            ids = [row[0] for row in conn.execute(query).fetchall()]
        return [self.get_event(event_id) for event_id in ids]  # type: ignore[list-item]

    def update_check_status(self, event_provider_id: int, *, attempted_at: str | None = None, succeeded_at: str | None = None, error: str | None = None, next_check_at: str | None = None) -> None:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE check_status SET last_attempt_at = COALESCE(?, last_attempt_at), last_success_at = COALESCE(?, last_success_at), last_error = ?, next_check_at = ? WHERE event_provider_id = ?",
                (attempted_at, succeeded_at, error, next_check_at, event_provider_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(event_provider_id)

    def record_monitor_alert(self, tracked_event_id: str, *, event_provider_id: int, observation_id: int, simulation_only: bool, total_per_ticket: float, currency: str, available_quantity: int) -> dict[str, Any] | None:
        """Record one qualifying alert per armed price cycle; never sends a notification."""
        total = _validate_price(total_per_ticket, "total_per_ticket", required=True)
        currency = _validate_currency(currency)
        quantity = _validate_quantity(available_quantity)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO monitor_alert_state (tracked_event_id) VALUES (?)", (tracked_event_id,))
            state = conn.execute(
                "SELECT armed, cycle_number FROM monitor_alert_state WHERE tracked_event_id = ?",
                (tracked_event_id,),
            ).fetchone()
            if not state[0]:
                return None
            cursor = conn.execute(
                "INSERT INTO monitor_alert_records (tracked_event_id, event_provider_id, observation_id, cycle_number, simulation_only, total_per_ticket, currency, available_quantity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (tracked_event_id, event_provider_id, observation_id, state[1], int(bool(simulation_only)), total, currency, quantity),
            )
            conn.execute(
                "UPDATE monitor_alert_state SET armed = 0, cycle_number = cycle_number + 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE tracked_event_id = ?",
                (tracked_event_id,),
            )
            return {"id": int(cursor.lastrowid), "cycle_number": int(state[1]), "simulation_only": bool(simulation_only)}

    def rearm_monitor_alert(self, tracked_event_id: str, *, checked_at: str) -> None:
        """Rearm after a clear check, unless a later concurrent check alerted."""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO monitor_alert_state (tracked_event_id) VALUES (?)", (tracked_event_id,))
            conn.execute(
                "UPDATE monitor_alert_state SET armed = 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE tracked_event_id = ? AND NOT EXISTS (SELECT 1 FROM monitor_alert_records WHERE tracked_event_id = ? AND julianday(created_at) >= julianday(?))",
                (tracked_event_id, tracked_event_id, checked_at),
            )

    def list_monitor_alert_records(self, *, simulation_only: bool | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query = "SELECT a.*, e.name AS event_name, p.provider_key, po.listing_id FROM monitor_alert_records a JOIN tracked_events e ON e.id = a.tracked_event_id JOIN event_providers ep ON ep.id = a.event_provider_id JOIN providers p ON p.id = ep.provider_id JOIN price_observations po ON po.id = a.observation_id AND po.tracked_event_id = a.tracked_event_id"
        params: list[Any] = []
        if simulation_only is not None:
            query += " WHERE a.simulation_only = ?"
            params.append(int(simulation_only))
        query += " ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
        params.append(limit)
        with self._connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_email_alert_context(self, monitor_alert_record_id: int) -> dict[str, Any] | None:
        """Load immutable alert data for a delivery template, without email credentials."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT a.id AS alert_id, a.simulation_only, a.total_per_ticket AS observed_price, a.currency, a.available_quantity, a.created_at AS alert_created_at, e.name AS event_name, e.maximum_price AS target_price, e.ticket_quantity AS requested_quantity, po.observed_at AS checked_at, po.listing_url, po.listing_id FROM monitor_alert_records a JOIN tracked_events e ON e.id = a.tracked_event_id JOIN price_observations po ON po.id = a.observation_id AND po.tracked_event_id = a.tracked_event_id WHERE a.id = ?",
                (monitor_alert_record_id,),
            ).fetchone()
            return dict(row) if row else None

    def enqueue_email_notification(self, monitor_alert_record_id: int, *, recipient_email: str, idempotency_key: str) -> dict[str, Any]:
        """Queue a real alert recipient once; simulation records are rejected."""
        recipient_email = str(recipient_email).strip().lower()
        if not recipient_email or not idempotency_key or len(idempotency_key) > 256:
            raise ValueError("recipient_email and a valid idempotency_key are required")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            alert = conn.execute(
                "SELECT simulation_only FROM monitor_alert_records WHERE id = ?",
                (monitor_alert_record_id,),
            ).fetchone()
            if alert is None:
                raise KeyError(monitor_alert_record_id)
            if alert[0]:
                raise ValueError("Simulation-only alerts cannot enter the customer email queue.")
            conn.execute(
                "INSERT INTO email_notification_outbox (monitor_alert_record_id, recipient_email, idempotency_key) VALUES (?, ?, ?) ON CONFLICT(monitor_alert_record_id, recipient_email) DO NOTHING",
                (monitor_alert_record_id, recipient_email, idempotency_key),
            )
            row = conn.execute(
                "SELECT * FROM email_notification_outbox WHERE monitor_alert_record_id = ? AND recipient_email = ?",
                (monitor_alert_record_id, recipient_email),
            ).fetchone()
            if row["idempotency_key"] != idempotency_key:
                raise ValueError("This notification already exists with a different idempotency key.")
            return dict(row)

    def claim_email_notifications(self, *, now: str, lease_seconds: float, limit: int, max_attempts: int, idempotency_retention_hours: float = 23.0) -> list[dict[str, Any]]:
        """Claim due deliveries atomically; expired claims retain their idempotency key."""
        if lease_seconds <= 0 or limit <= 0 or max_attempts <= 0 or idempotency_retention_hours <= 0:
            raise ValueError("lease, limit, attempts, and retention must be positive")
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        now_dt = now_dt.astimezone(timezone.utc)
        lease_cutoff = (now_dt - timedelta(seconds=lease_seconds)).isoformat()
        uncertain_cutoff = (now_dt - timedelta(hours=idempotency_retention_hours)).isoformat()
        now_iso = now_dt.isoformat()
        claimed = []
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE email_notification_outbox SET status = 'failed', claim_token = NULL, claimed_at = NULL, delivery_uncertain = 1, last_error = COALESCE(last_error, 'Delivery outcome is uncertain beyond the provider idempotency window.'), updated_at = ? WHERE delivery_uncertain = 1 AND status IN ('retryable', 'sending') AND first_attempt_at IS NOT NULL AND julianday(first_attempt_at) <= julianday(?)",
                (now_iso, uncertain_cutoff),
            )
            conn.execute(
                "UPDATE email_notification_outbox SET status = 'failed', claim_token = NULL, claimed_at = NULL, delivery_uncertain = CASE WHEN status = 'sending' THEN 1 ELSE delivery_uncertain END, last_error = COALESCE(last_error, 'Maximum delivery attempts reached.'), updated_at = ? WHERE attempt_count >= ? AND ((status = 'retryable' AND julianday(available_at) <= julianday(?)) OR (status = 'sending' AND julianday(claimed_at) <= julianday(?)))",
                (now_iso, max_attempts, now_iso, lease_cutoff),
            )
            due = conn.execute(
                "SELECT * FROM email_notification_outbox WHERE ((status IN ('pending', 'retryable') AND julianday(available_at) <= julianday(?) AND attempt_count < ?) OR (status = 'sending' AND julianday(claimed_at) <= julianday(?) AND attempt_count < ?)) ORDER BY created_at, id LIMIT ?",
                (now_iso, max_attempts, lease_cutoff, max_attempts, limit),
            ).fetchall()
            for row in due:
                token = str(uuid.uuid4())
                was_claimed = row["status"] == "sending"
                conn.execute(
                    "UPDATE email_notification_outbox SET status = 'sending', attempt_count = attempt_count + 1, first_attempt_at = COALESCE(first_attempt_at, ?), claimed_at = ?, claim_token = ?, delivery_uncertain = CASE WHEN ? THEN 1 ELSE delivery_uncertain END, updated_at = ? WHERE id = ?",
                    (now_iso, now_iso, token, int(was_claimed), now_iso, row["id"]),
                )
                claimed_row = conn.execute("SELECT * FROM email_notification_outbox WHERE id = ?", (row["id"],)).fetchone()
                claimed.append(dict(claimed_row))
        return claimed

    def mark_email_notification_sent(self, delivery_id: int, claim_token: str, *, provider_message_id: str, sent_at: str) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE email_notification_outbox SET status = 'sent', provider_message_id = ?, sent_at = ?, claim_token = NULL, claimed_at = NULL, delivery_uncertain = 0, last_error = NULL, updated_at = ? WHERE id = ? AND status = 'sending' AND claim_token = ?",
                (provider_message_id, sent_at, sent_at, delivery_id, claim_token),
            )
            return cursor.rowcount == 1

    def mark_email_notification_failure(self, delivery_id: int, claim_token: str, *, status: str, error: str, retry_at: str, delivery_uncertain: bool, updated_at: str) -> bool:
        if status not in {"retryable", "failed"}:
            raise ValueError("email delivery failure status must be retryable or failed")
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE email_notification_outbox SET status = ?, available_at = ?, claim_token = NULL, claimed_at = NULL, delivery_uncertain = CASE WHEN ? THEN 1 ELSE delivery_uncertain END, last_error = ?, updated_at = ? WHERE id = ? AND status = 'sending' AND claim_token = ?",
                (status, retry_at, int(delivery_uncertain), error[:1000], updated_at, delivery_id, claim_token),
            )
            return cursor.rowcount == 1

    def list_email_notification_deliveries(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT n.*, a.tracked_event_id, e.name AS event_name, a.simulation_only FROM email_notification_outbox n JOIN monitor_alert_records a ON a.id = n.monitor_alert_record_id JOIN tracked_events e ON e.id = a.tracked_event_id ORDER BY n.created_at DESC, n.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_observation(self, event_id: str, *, price_per_ticket: float, currency: str, observed_at: str, pricing_confidence: str, source: str = "unknown", event_provider_id: int | None = None, listing_id: str | None = None, listing_url: str | None = None, section: str | None = None, row_label: str | None = None, fees_per_ticket: float | None = None, total_per_ticket: float | None = None, available_quantity: int | None = None) -> int:
        if pricing_confidence not in {"verified_all_in", "estimated", "incomplete"}:
            raise ValueError("unsupported pricing_confidence")
        price = _validate_price(price_per_ticket, "price_per_ticket", required=True)
        fees = None if fees_per_ticket is None else float(fees_per_ticket)
        if fees is not None and (not math.isfinite(fees) or fees < 0):
            raise ValueError("fees_per_ticket must be a finite nonnegative amount")
        total = _validate_price(total_per_ticket, "total_per_ticket")
        quantity = None if available_quantity is None else _validate_quantity(available_quantity)
        currency = _validate_currency(currency)
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO price_observations (tracked_event_id, event_provider_id, listing_id, listing_url, section, row_label, price_per_ticket, fees_per_ticket, total_per_ticket, currency, available_quantity, pricing_confidence, observed_at, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, event_provider_id, listing_id, listing_url, section, row_label, price, fees, total, currency, quantity, pricing_confidence, observed_at, source),
            )
            return int(cursor.lastrowid)

    def add_aggregate_price_range(self, event_id: str, *, event_provider_id: int, source: str, provider_event_id: str, range_label: str, minimum_price: float, maximum_price: float, currency: str, observed_at: str, event_url: str | None = None) -> int:
        """Persist an event-level price range without claiming listings or quantity."""
        minimum = _validate_price(minimum_price, "minimum_price", required=True)
        maximum = _validate_price(maximum_price, "maximum_price", required=True)
        if maximum < minimum:
            raise ValueError("maximum_price must be at least minimum_price")
        currency = _validate_currency(currency)
        if not source.strip() or not provider_event_id.strip() or not range_label.strip():
            raise ValueError("source, provider_event_id, and range_label are required")
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO aggregate_price_ranges (tracked_event_id, event_provider_id, source, provider_event_id, range_label, range_min_price, range_max_price, currency, event_url, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, event_provider_id, source, provider_event_id, range_label, minimum, maximum, currency, event_url, observed_at),
            )
            return int(cursor.lastrowid)

    def list_aggregate_price_ranges(self, event_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM aggregate_price_ranges WHERE tracked_event_id = ? ORDER BY observed_at, id",
                (event_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_observations(self, event_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM price_observations WHERE tracked_event_id = ? ORDER BY observed_at, id", (event_id,)).fetchall()
            return [dict(row) for row in rows]

    def record_notification(self, event_id: str, deduplication_key: str, *, observation_id: int | None = None, status: str = "pending") -> bool:
        """Insert one notification key; return False when already recorded."""
        if not deduplication_key:
            raise ValueError("deduplication_key is required")
        if status not in {"pending", "sent", "failed"}:
            raise ValueError("unsupported notification status")
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO notification_deduplication (tracked_event_id, deduplication_key, observation_id, status) VALUES (?, ?, ?, ?) ON CONFLICT(tracked_event_id, deduplication_key) DO NOTHING",
                (event_id, deduplication_key, observation_id, status),
            )
            return cursor.rowcount == 1

    def update_notification_status(self, event_id: str, deduplication_key: str, status: str) -> None:
        if status not in {"pending", "sent", "failed"}:
            raise ValueError("unsupported notification status")
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE notification_deduplication SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE tracked_event_id = ? AND deduplication_key = ?",
                (status, event_id, deduplication_key),
            )
            if cursor.rowcount != 1:
                raise KeyError((event_id, deduplication_key))
