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
