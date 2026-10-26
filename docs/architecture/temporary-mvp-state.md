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

`idempotency_records` is deliberately bounded and every row is constrained to `policy_status='[TEMPORARY_MVP_DEFAULT]'`. Buyer scope, a 64-character request hash, a bounded key, bounded JSON outcome payload, state, expiry, and replay fields are present for the local/demo retry seam. Frozen requirements exclude idempotency acceptance; operation scope, concurrent in-progress behavior, replay authorization, lifecycle, and production retention remain blocked.
