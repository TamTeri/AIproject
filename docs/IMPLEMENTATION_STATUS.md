# EventHub implementation status

**Status:** every version-one feature is built and tested. Policy values the customer has not confirmed run as labelled temporary defaults, which work in local, development and test environments only.

**Branch:** `eventhub/part4` (based on `main` @ `7ebc3a7`)
**Tests:** 216 passing against PostgreSQL. Without a database, 195 pass and 21 skip.

## Built and tested

| Feature | Code | Tests |
|---|---|---|
| Identity: register, login, hashed passwords, server-side sessions, 30-minute idle timeout, logout | `app/identity/` | `tests/unit/identity/`, contract, integration |
| Catalog: list, artist/venue search, no-match message, event page with availability, click/double-click | `app/catalog/`, `templates/events.html`, `app/web/static/eventhub.js` | `tests/unit/catalog/`, contract |
| Pricing: one calculator, discount eligibility, configured multi-currency rates | `app/pricing/` | `tests/unit/pricing/` (incl. Call 4 email cases) |
| Inventory: 10-minute holds, no overselling, release exactly once | `app/inventory/` | `tests/unit/purchase/`, integration concurrency |
| Purchase: server validation, limit, simulated payment, quick buy on the same path | `app/purchase/` | `tests/unit/purchase/`, integration |
| Orders: history, confirmation page, buyer-only access | `app/orders/` | `tests/unit/orders/`, contract, integration |
| Audit: every attempt recorded, append-only, internal-error record | `app/audit/`, `purchase/service.py` | unit, integration (database trigger) |
| Admin: rates and audit viewer; buyers blocked | `app/admin/` | `tests/unit/admin/`, contract, integration |
| Process: CI, pre-commit hooks, lint and style, spec-alignment warning, CONTRIBUTING | `.github/`, `.pre-commit-config.yaml`, `scripts/` | CI |

## Integration bugs fixed in this branch (from the separately built pieces on `main`)

1. `app/db/` (a package) replaced the `db` variable in `app/__init__.py`, so `create_app()` crashed. The app could not start.
2. The purchase code wrote outcomes like `payment_failed` to `purchase_attempts.outcome`, which only accepts `success`, `rejected`, `failed` or `replayed`. Every audit insert would have failed. Outcomes are now a category plus a `reason_code`.
3. `HoldStatus.RELEASED` did not exist in the database's allowed values. The enum now matches the database exactly.
4. A sold-out event made `allocate_hold()` return `None` and the purchase code then crashed on `hold.id`. It now returns `sold_out`.
5. The web layer always answered "service unavailable", because nothing connected the routes to real services. `app/wiring.py` now does that.
6. Pricing only allowed USD, but pricing-003 needs a choice of currency. USD is now the base currency and buyers can pay in any enabled currency.

## Still open (customer decisions)

- The discount percentage, discount scope by event type, and email verification for the discount.
- The organizational-account exception to the purchase limit (purchase-010).
- Administrator provisioning lifecycle (ADR-004).
- Audit retention and who besides administrators may read the audit log.
- Production session policy, load and performance targets, and production deployment.
- Idempotent retry of payments. The `idempotency_records` table exists but is not used, because the frozen requirements exclude it.

## Not done here

- `diagrams/*.png` were exported before Call 4. `workspace.dsl` now has a `Component_PostCall4` view. Re-export the PNGs from Structurizr to include it.
- Browser tests are not part of CI. `scripts/browser_check.py` drives Chrome through 15 scenarios, including single click and double click, and passed on the final code. It is run by hand because it needs Chrome and Playwright.
