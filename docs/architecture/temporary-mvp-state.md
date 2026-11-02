# Temporary MVP state boundaries

These rows and values are implementation seams authorized for the local/demo buyer tracer only. They do not close the frozen target's `[OPEN]` policy ledger or establish production governance.

## Holds

- `holds` supports `active`, `converted`, `cancelled`, `expired`, and `payment_failed` statuses.
- The seed/config boundary records a ten-minute duration (`600` seconds), matching team decision D5.
- Expiry is represented using PostgreSQL timestamps and the availability view excludes active holds whose `expires_at` has passed.
- The exact release trigger, cancellation/payment-failure race, cleanup strategy, terminal transition linearization, exactly-once release proof, and hold-to-order conversion mechanics remain temporary MVP seams for the purchase/inventory lane to prove. This schema alone is not a hold state-machine acceptance claim.

## Audit

- `purchase_attempts` is bounded and database-enforced append-only: update/delete attempts are rejected by a trigger.
- The table can represent successful, rejected, failed, and replayed outcomes with bounded reason/request/idempotency fields and nullable related IDs.
- Audit durability across same-transaction rollback, process crash, retry, and audit-write failure remains explicitly open. The transaction seam provides the future purchase owner one commit boundary; it does not silently choose an outbox or separate durable transaction model.
- No rate-change audit history is added; ADR-003 scopes the admin viewer to purchase attempts only.

## Idempotency

**Call 5 update:** the table is now used. Every purchase form carries a one-time key; the first request with a key stores its result and any repeat replays it (purchase-014, ADR-007). Keys are kept 24 hours (`IDEMPOTENCY_RETENTION_HOURS`, `[TEMPORARY_MVP_DEFAULT]`). A buyer's expired keys are deleted the next time that buyer claims a key.

Original Part 3/4 note:

`idempotency_records` is deliberately bounded and every row is constrained to `policy_status='[TEMPORARY_MVP_DEFAULT]'`. Buyer scope, a 64-character request hash, a bounded key, bounded JSON outcome payload, state, expiry, and replay fields are present for the local/demo retry seam. Frozen requirements exclude idempotency acceptance; operation scope, concurrent in-progress behavior, replay authorization, lifecycle, and production retention remain blocked.

## Purchase request limit (Call 5)

`purchase_rate_windows` (migration 0006) holds one fixed-window counter per account: 10 purchase requests per 60 seconds, `[TEMPORARY_MVP_DEFAULT]` (purchase-015, ADR-007). A row is replaced in place when its window ends, so the table never grows past one row per account.
