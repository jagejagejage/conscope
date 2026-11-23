# Local monitoring engine

ConScope has a provider-neutral, one-pass monitoring service. The service checks each unpaused event for configured providers, stores normalized price observations, and updates each provider's last attempt, last success, last error, and optional next-check time. A failed check leaves prior successful price history intact. An offline or rate-limited response is shown as a failure; it is never treated as zero tickets.

## Local commands

Run the focused offline tests (all provider sessions are fakes; no live API requests):

```sh
python3 -m unittest tests.test_monitoring tests.test_providers tests.test_local_database tests.test_dashboard_data -v
```

Run one monitoring pass, suitable for invoking from a future external scheduled job:

```sh
python3 scripts/run_monitor.py once
```

Run one explicit simulation pass that allows qualifying MockProvider observations to create test alert records:

```sh
python3 scripts/run_monitor.py once --simulation
```

Run the optional local scheduler (first pass starts immediately, then repeats every 5 minutes):

```sh
python3 scripts/run_monitor.py schedule --interval-seconds 300
```

Run the scheduler in simulation mode, then stop it with Ctrl+C:

```sh
python3 scripts/run_monitor.py schedule --simulation --interval-seconds 300
```

Use `--data-dir /path/to/conscope-data` with any command to choose a SQLite data directory. By default it uses the platform ConScope application data directory. The `once` command does not wait or start a server. The scheduler uses only Python's standard library and can be omitted in a hosted scheduled-job deployment.

The current CLI registers only the deterministic MockProvider. Ticketmaster live pricing and SeatGeek remain disabled. Mock observations may create records only with `--simulation`; records are visibly marked simulation-only and no email or other outbound notification is sent. Non-mock verified observations may create a non-simulation alert ledger record if a future authorized provider is explicitly registered. Resend delivery components exist separately but are not wired to the monitor; see [EMAIL_NOTIFICATIONS.md](EMAIL_NOTIFICATIONS.md).

## Qualification rules

A listing qualifies only when all of these are true:

- it is a `ticket_listing`, not an event-level aggregate range;
- pricing confidence is `verified_all_in` and `total_per_ticket` is present;
- reported available quantity meets the tracked event's requested quantity;
- the listing currency exactly matches the tracked event's target currency (there is no currency conversion);
- all-in total per ticket is at or below the maximum target;
- the observation is fresh (within 24 hours and not future-dated).

Estimated, incomplete, simulated-without-simulation-mode, stale, and currency-mismatched observations do not qualify. Ambiguous, stale, failed, or skipped provider results do not rearm a prior alert. Ticketmaster `priceRanges` are event metadata, not listing offers, and can never qualify.

## Duplicate prevention and rearming

The SQLite `monitor_alert_records` table has a unique `(tracked_event_id, cycle_number)` constraint, and alert-state transitions run in an immediate write transaction. The first qualifying result while armed creates one record and disarms that event's alert cycle. Repeat checks while a qualifying offer remains do not create duplicate records.

A cycle rearms only after every configured provider for that event returns successfully with fresh, comparable inventory and no qualifying offer. A successful empty result counts as no inventory. If any returned listing is stale, not verified all-in, missing quantity/total, in a different currency, or is an aggregate range, the result is ambiguous and does not rearm. A provider error or disabled provider also does not rearm. A `Retry-After` value is persisted as a not-before check time and the engine skips that provider until the time arrives. Once rearmed, a later qualifying result can create the next cycle's record. Paused events are skipped; resuming allows checks on the next pass.

The dashboard's **Automatic monitoring status** section shows provider check times, next check when set by the local scheduler, and simulation-only alert records. Alert ledger records are monitoring state only. Resend delivery primitives now exist separately, but monitoring does not enqueue alerts or send email; see [EMAIL_NOTIFICATIONS.md](EMAIL_NOTIFICATIONS.md). Cloud hosting and live ticket-price providers remain future work.
