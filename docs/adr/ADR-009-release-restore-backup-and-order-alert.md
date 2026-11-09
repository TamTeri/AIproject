# ADR-009: Release gate, restorable releases, backup and order alert

**Status:** `[TEAM]` accepted (Call 6). Thresholds `[TEMPORARY_MVP_DEFAULT]`; backup owner and alert rotation `[OPEN]`. Supports system-017, system-018, system-019, audit-009, pricing-013.

## Context
Call 6 postmortem: the audit trail recorded every wrong order, but nobody watched it, so the team learned of the bug from a group chat. Rolling back to release 1.2 took eleven minutes and worked because the previous version existed and was runnable. Nobody had asked who backs up the database.

## Decisions
1. **Release gate (system-017).** A release is not promoted until the corrective tests are green. The CI gate also fails if any test is skipped, so a missing database or browser cannot turn a failure into a quiet pass. The previous release stays live meanwhile.
2. **Restorable releases (system-018).** Every release is tagged: `v1.2.0` is the known-good baseline and `v1.3.0` the maintenance release. The documented switch back is to check out the previous tag and restart. Database caveat: an Alembic `downgrade` is only safe for migrations that were written reversible. A rollback that crosses a migration needs its downgrade tested first, or the tables the older release does not know about must be left in place.
3. **Rollback first.** When a live defect is confirmed, restore the previous tag, then debug in a test environment.
4. **Rate edits are recorded (pricing-013).** `exchange_rate_history` stores who, old rate, new rate and when. An edit of more than 25% needs explicit confirmation.
5. **Order alert (audit-009).** A scheduled `check-orders` command flags orders whose per-ticket USD-equivalent total is below 50% or above 200% of the event's base price, and logs one ERROR line per finding through a `notify()` function; the scheduled job exits non-zero, and that failing run is what reaches a human (GitHub emails the workflow watchers). The job is skipped when the database secret is absent. Known limits [TEMPORARY_MVP_DEFAULT]: the check compares `total_minor` (discounts included) with the event's current base price, so a discount over 50% or a later price edit can false-alarm, and overlapping windows can repeat an alert. The payload carries order id, event id, currency and ratio, and no personal data. The channel is an external system behind the port, so changing it touches one adapter.
6. **Backup (system-019).** The database needs a named owner, a nightly `pg_dump`, and a restore drill. The owner is `[OPEN]` until a person is named. We do not assume the hosting side backs it up.

## Not decided
- An on-call rotation for the alert (deferred explicitly by Priya) `[OPEN]`.
- The 50% and 200% thresholds are `[TEMPORARY_MVP_DEFAULT]` until the customer confirms them.
- The backup owner `[OPEN]`.

## Consequences
- An order-total bug is caught within one `check-orders` period, not by a student.
- The alert does not prevent a bad price; it shortens detection. Prevention is ADR-008 and the per-currency tests.
