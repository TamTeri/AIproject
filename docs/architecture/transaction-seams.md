# PostgreSQL transaction seams

Status: minimum shared seam for the buyer tracer; not a complete purchase implementation.

## Unit of work

`app.db.PostgresDatabase.transaction()` opens one SQLAlchemy PostgreSQL transaction and yields its one `Connection`. Normal exit commits; an exception rolls back. The purchase coordinator is the future owner of this scope. Inventory, order, idempotency, and audit repositories must accept the yielded connection and must not call `commit()` or `rollback()` themselves.

This is a transaction seam, not a purchase service. It does not select an isolation level, retry policy, or lock order beyond the PostgreSQL transaction boundary. Those remain implementation obligations for the purchase/inventory lane.

## Seed/reset

`app.db.commands` provides a shared-schema command path:

```text
python -m app.db.commands reset
python -m app.db.commands migrate
python -m app.db.commands seed
```

The command path requires a PostgreSQL URL. Reset additionally requires explicit `EVENTHUB_ENVIRONMENT` in `local`, `development`, or `test` and `EVENTHUB_RESET_ENABLED=true`; an omitted environment is rejected. Seed runs migrations first and upserts the fixed `seed/catalog.json` fixture in one database transaction. The fixture is labeled `[TEMPORARY_MVP_DEFAULT] [PROVISIONAL_LOCAL_ONLY]` and is not an acceptance or production policy source.

## Fresh-database contract

The ordered Alembic stream is:

1. `0001_bootstrap` — existing foundation marker;
2. `0002_reference_config` — currencies and labeled config values;
3. `0003_accounts_catalog` — accounts, session support, events, exchange rates;
4. `0004_purchase_audit` — holds, orders, and purchase-attempt rows;
5. `0005_schema_seams` — bounded temporary idempotency, derived availability, and append-only audit enforcement.

A fresh database must apply all five revisions before seed. Reset leaves this same migrated schema without seed rows.
