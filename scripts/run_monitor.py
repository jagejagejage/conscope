#!/usr/bin/env python3
"""Run one ConScope monitoring pass or an optional local scheduler loop."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conscope_app.database import Database  # noqa: E402
from conscope_app.monitoring import run_monitoring_pass  # noqa: E402
from conscope_app.providers.mock import MockProvider  # noqa: E402
from conscope_app.scheduler import format_pass_summary, run_local_scheduler  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("once", "schedule"), default="once")
    parser.add_argument("--simulation", action="store_true", help="Allow qualifying MockProvider observations to create simulation-only alert records. Sends no email.")
    parser.add_argument("--interval-seconds", type=float, default=300, help="Local scheduler interval; defaults to 300 seconds.")
    parser.add_argument("--data-dir", help="Optional SQLite data directory (defaults to the platform ConScope directory).")
    args = parser.parse_args()
    if args.interval_seconds <= 0:
        parser.error("--interval-seconds must be positive")

    database = Database(data_dir=args.data_dir) if args.data_dir else Database()
    # Ticketmaster and SeatGeek pricing stay intentionally unregistered/disabled.
    providers = {"mock": MockProvider()}
    def report(result):
        print(format_pass_summary(result, simulation_mode=args.simulation))
        for check in result.checks:
            if not check.succeeded:
                label = "Skipped" if check.skipped else "Check failed"
                print(f"{label}: {check.event_name} · {check.provider_key} · {check.error or 'no details'}")
        for alert in result.alerts:
            marker = "SIMULATED ALERT · no email sent" if alert["simulation_only"] else "Alert record created · no email sent"
            print(f"{marker}: {alert['event_name']} · {alert['currency']} {alert['total_per_ticket']:.2f}/ticket · quantity {alert['available_quantity']}")

    if args.command == "schedule":
        print(f"Starting local scheduler every {args.interval_seconds:g} seconds.")
        print("Simulation mode is ON; no outbound notifications are configured." if args.simulation else "Simulation mode is OFF; no outbound notifications are configured.")
        try:
            run_local_scheduler(
                database,
                providers,
                interval_seconds=args.interval_seconds,
                simulation_mode=args.simulation,
                on_pass=report,
            )
        except KeyboardInterrupt:
            print("Local scheduler stopped.")
        return 0

    result = run_monitoring_pass(database, providers, simulation_mode=args.simulation)
    report(result)
    return 1 if result.failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
