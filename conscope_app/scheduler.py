"""Optional standard-library scheduler for local monitoring runs."""

from __future__ import annotations

from threading import Event
from typing import Callable, Mapping

from .database import Database
from .monitoring import MonitorPassResult, run_monitoring_pass
from .providers.base import TicketProvider


def run_local_scheduler(
    database: Database,
    providers: Mapping[str, TicketProvider],
    *,
    interval_seconds: float = 300,
    simulation_mode: bool = False,
    stop_event: Event | None = None,
    on_pass: Callable[[MonitorPassResult], None] | None = None,
) -> None:
    """Run a pass immediately, then repeat until stopped; no server is started."""
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    stop_event = stop_event or Event()
    while not stop_event.is_set():
        result = run_monitoring_pass(
            database,
            providers,
            simulation_mode=simulation_mode,
            interval_seconds=interval_seconds,
        )
        if on_pass:
            on_pass(result)
        if stop_event.wait(interval_seconds):
            break


def format_pass_summary(result: MonitorPassResult, *, simulation_mode: bool) -> str:
    label = "SIMULATION ONLY" if simulation_mode else "monitoring"
    return (
        f"{label}: {result.checked_count} provider check(s) succeeded, "
        f"{result.failure_count} failed, {len(result.alerts)} new alert record(s)."
    )
