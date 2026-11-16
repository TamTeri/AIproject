# EventHub implementation status

**Status:** every version-one feature is built and tested. Policy values the customer has not confirmed run as labelled temporary defaults, which work in local, development and test environments only.

**Branch:** `eventhub/part5` (based on `main` @ `5a98b90`, the merged Part 4)
**Tests:** 286 passing against PostgreSQL (without a database, the PostgreSQL ones skip), plus **87 Selenium system test runs** passing against the final application (`python scripts/run_system_tests.py`).

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
- Production session policy and production deployment.
- Call 5 placeholders the customer must confirm: the double-purchase behaviour (purchase-014), 10 purchase requests per minute (purchase-015), sales closing at the start time (purchase-018), and the performance sentence (system-013, Marcus).
- Proof of USF email ownership for the discount (pricing-012).

## Not done here

- `diagrams/*.png` were exported before Call 4. `workspace.dsl` now has a `Component_PostCall4` view. Re-export the PNGs from Structurizr to include it.
- The Call 5 views (`diagrams/structurizr-1-Container_PostCall5.png`, `...Component_PostCall5.png`) were rendered from Structurizr's Mermaid export (`diagrams/call5-export/`), so their layout differs from the earlier Structurizr Lite PNGs. Re-export them from Structurizr Lite for a matching look.

## Added in Part 5 (Call 5: testing)

| What | Code | Tests |
|---|---|---|
| Selenium system tests: one command, double-click file, CI on every change and a Run button, HTML report with failure screenshots | `tests/system/`, `scripts/run_system_tests.py`, `run-system-tests.cmd`, `.github/workflows/system-tests.yml` | 57 cases / 87 runs |
| Same form submitted twice: processed once (purchase-014) | `app/purchase/service.py`, `PostgresIdempotency` | ST-30..35, `test_call5_rules.py`, 5-thread PostgreSQL test |
| 10 purchase requests per account per minute (purchase-015) | `PostgresRequestRate`, migration `0006` | ST-36, ST-37, unit, PostgreSQL |
| Discount re-checked at payment; email change (pricing-011, identity-014) | `QuoteService.discount_still_applies`, `IdentityService.change_email` | ST-38..40, unit, PostgreSQL |
| Labelled amount charged (orders-006); home currency explained (identity-015, catalog-012) | templates | ST-41..43, contract |
| Specific rejection messages; logged-out attempts audited (purchase-016/017, audit-008) | `classify_quantity`, `OUTCOME_MESSAGES` | ST-11..23, unit, contract |
| No sales after the event starts (purchase-018) | `PostgresPurchasableEvents.sales_closed` | ST-44, ST-69, unit, PostgreSQL |
| ASCII-only number parsing: "²" no longer crashes the server | `db_id`, catalog, orders, admin, `classify_quantity` | ST-20, ST-21, ST-23 |
| Last-ticket race 200 times (inventory-009) | — | `test_call5_postgres.py` |
| Performance target (system-013, temporary) | — | ST-70 |
| Every requirement named by a test; catalogue generated from the tests | `scripts/check_requirement_coverage.py`, `scripts/list_system_tests.py` | `tests/test_project_process.py`, CI |

## Part 6 (Call 6: maintenance), release 1.3.0

**Branch/tag:** work branched from tag `v1.2.0` (the known-good baseline); the maintenance release is tagged `v1.3.0` when the lead merges the five streams. Integrated unit+contract run: 383 passed, 39 skipped (Postgres), 87 deselected (Selenium); the Postgres and Selenium layers are proven only by the CI run.

| What | Requirements | Status |
|---|---|---|
| Purchase test for every currency including JPY; minor-unit display and charge (the 1.3 yen incident) | system-016, pricing-014 | planned, see `docs/acceptance-matrix.md` |
| Admin rate edit used by next purchase; large-change confirmation; `exchange_rate_history` | admin-006, pricing-013 | planned |
| Localization: Spanish + English, regional dates and currency formats | system-020..023 | planned |
| Out-of-range order alert (`check-orders`) | audit-009 | planned; rotation `[OPEN]` |
| Release gate (skipped tests fail), restorable releases, backup | system-017..019 | planned; backup owner `[OPEN]` |

### Still open after Call 6
- Backup owner and the first restore drill (system-019).
- Who receives the order alert, and any on-call rotation (audit-009). Thresholds 50% and 200% and the 25% rate-edit confirmation are `[TEMPORARY_MVP_DEFAULT]`.
- Customer sign-off before JPY (or any currency) is offered to real buyers (pricing-014).
- Native-speaker review of the Spanish text.

### Diagrams to export
`workspace.dsl` has new views `Container_PostCall6` and `Component_PostCall6`. The PNGs are not regenerated here (no tooling). Export both from Structurizr, and re-export the PostCall3/4/5 views to check they did not change.
