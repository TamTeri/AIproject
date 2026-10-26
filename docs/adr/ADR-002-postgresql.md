# ADR-002: One PostgreSQL database

**Status:** `[TEAM]` accepted. Supports system-005 and inventory-003/004.

## Context
Overselling was the customer's biggest fear. The availability check and the ticket reservation must happen as one action, even when many buyers click at the same moment.

## Decision
- All persistent data lives in one PostgreSQL database, and Alembic migrations are the only thing that changes the schema.
- Availability is never stored. It is calculated as capacity minus sold minus active holds (the `event_availability` view).
- A purchase attempt runs in one transaction. It locks the event row with `SELECT ... FOR UPDATE` before checking the buyer's limit and the capacity.
- There is no SQLite fallback. Tests that need a database use a real PostgreSQL.

## Consequences
- `tests/integration/test_postgres_adapters.py` proves that 10 simultaneous buyers can never take more than the 2 remaining tickets.
- Purchases for one event are processed one at a time. That is fine at campus scale; load testing is `[OPEN]`.
