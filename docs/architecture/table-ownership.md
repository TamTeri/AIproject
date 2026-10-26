# Shared PostgreSQL table ownership

Status: implementation seam for the buyer tracer. This document does not close frozen `[OPEN]` policy items.

## One writer per relation

| Relation | Owning lane | Allowed responsibility | Explicit non-owner |
|---|---|---|---|
| `accounts` | identity | buyer identity, normalized email, password hash, role field, session-revocation timestamps | catalog, pricing, purchase, web request fields |
| `account_sessions` | identity | hashed session token, expiry, revocation, last-seen support fields | process-local session dictionaries |
| `events` | catalog | event description, catalog key, base price, fixed capacity, deterministic import/seed | catalog does not write availability counters |
| `event_availability` | inventory read seam | derived `capacity - sold - active unexpired holds` view | no mutable `available` column or process-local authority |
| `currencies` | pricing/config | enabled currency and minor-unit metadata | request payloads cannot add currencies |
| `exchange_rates` | pricing/admin boundary | configured exact numeric rates and update provenance | no live external-rate fetch in MVP |
| `app_config` | config/pricing | bounded, labeled policy/config values used by temporary USD pricing and adjacent seams | temporary values are not stakeholder approval |
| `holds` | inventory/purchase transaction | reservation rows and temporary lifecycle state | no independent repository commit/rollback |
| `orders` | orders/purchase transaction | committed buyer-owned sale snapshot and history fields | orders do not recalculate pricing |
| `purchase_attempts` | audit/purchase transaction | bounded append-only purchase-attempt projection | no rate-change audit history is implied |
| `idempotency_records` | purchase transaction | bounded buyer-scoped replay record under an explicit temporary label | not a frozen production requirement |
| `eventhub_bootstrap` | database bootstrap | infrastructure marker used by the existing foundation command | not product authority |

## PostgreSQL authority

PostgreSQL owns durable capacity, reservations, completed orders, and audit rows. The availability view is intentionally derived from `events.capacity`, completed `orders`, and active unexpired `holds`; it is not a second mutable inventory counter. Hold creation and order conversion must be performed by the purchase-owned transaction seam with one connection and one commit boundary.

Migrations are the only schema writer. The deterministic seed writes only the declared catalog, currency/rate, and labeled configuration fixtures. Reset is destructive and is exposed only through an explicit local/development/test guard.
