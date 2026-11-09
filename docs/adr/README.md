# Architecture decision records

Short records of decisions that shape the code. Labels: `[STAKEHOLDER]` (customer decided), `[TEAM]` (team decided), `[TEMPORARY_MVP_DEFAULT]` (placeholder until someone decides), `[OPEN]` (not decided).

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](ADR-001-flask-monolith.md) | One Python/Flask web application (modular monolith) | `[TEAM]` accepted |
| [ADR-002](ADR-002-postgresql.md) | One PostgreSQL database for all persistent data | `[TEAM]` accepted |
| [ADR-003](ADR-003-admin-boundary.md) | Admin area limited to exchange rates and the purchase-attempt audit viewer | `[TEAM]` accepted |
| [ADR-004](ADR-004-admin-provisioning.md) | How an account becomes an administrator | `[OPEN]` (temporary: operator command) |
| [ADR-005](ADR-005-money-representation.md) | Money as integer minor units; exact decimal rates; one rounding | `[TEAM]` accepted (Call 4) |
| [ADR-006](ADR-006-feature-modules-and-testing.md) | Standalone feature modules behind ports; one composition root | `[TEAM]` accepted (Call 4) |
| [ADR-007](ADR-007-duplicate-submissions-and-request-limits.md) | One-time form keys, a per-account request limit, and discount/sales re-checks in the purchase path | `[TEAM]` accepted (Call 5); numbers `[TEMPORARY_MVP_DEFAULT]` |
| [ADR-008](ADR-008-money-formatting-and-minor-units.md) | Money display and charge follow the currency's minor unit; a missing exponent is an error (refines ADR-005) | `[TEAM]` accepted (Call 6); JPY for real buyers `[OPEN]` |
| [ADR-009](ADR-009-release-restore-backup-and-order-alert.md) | Release gate, restorable tagged releases, database backup, out-of-range order alert | `[TEAM]` accepted (Call 6); thresholds `[TEMPORARY_MVP_DEFAULT]`, backup owner and rotation `[OPEN]` |
| [ADR-010](ADR-010-localization.md) | Message catalogs, allowlisted locale, regional dates and currency formats | `[TEAM]` accepted (Call 6); Spanish wording `[TEMPORARY_MVP_DEFAULT]` |
