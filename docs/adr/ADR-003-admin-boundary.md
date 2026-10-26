# ADR-003: Administrator area boundary

**Status:** `[TEAM]` accepted (Call 3). Supports admin-001..003 and audit-003.

## Decision
- The admin area (`/admin`) does exactly two things: it edits configured exchange rates, and it reads the purchase-attempt audit log. Nothing else.
- Every admin route checks the role in the web layer. `AdminService` checks it again (defence in depth), so a forgotten decorator still cannot leak data to a buyer.
- Each rate change records who made it and when (`exchange_rates.updated_by` and `updated_at`). There is no rate-change history table.
- Rate changes apply only to new checkouts. A hold keeps the price it was quoted (purchase-013).
