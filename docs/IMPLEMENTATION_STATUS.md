# EventHub implementation status

**Status:** `PARTIAL` — bootstrap foundation implemented; product lanes intentionally untouched.

**Base:** `3bd9414cd7c2f130fc00fbdad1ee1aa1bd03253`
**Branch:** `eventhub/bootstrap`
**Authority date:** October 26, 2026

## Implemented and verified

- Project dependency manifest (`pyproject.toml`) and reproducible `requirements.lock`.
- Flask `create_app()` factory with a `/healthz` bootstrap route.
- SQLAlchemy/Flask-SQLAlchemy extension seam and PostgreSQL-only configuration validation.
- Alembic migration stream containing only the bootstrap infrastructure marker table.
- Deterministic JSON seed fixture and guarded reset command.
- `python -m app.config.commands {migrate,seed,reset}` plus installed console-script entrypoints.
- Disposable PostgreSQL Compose configuration.
- Focused RED/GREEN evidence for the app factory and the real PostgreSQL migration/seed/reset round trip.
- Ownership, authority, acceptance, and temporary-default documentation.

## Not implemented by design

- No identity, catalog, pricing, inventory, purchase, orders, audit, administration, or web product behavior.
- No stakeholder-policy closure. Temporary defaults are labeled `[TEMPORARY_MVP_DEFAULT]` / `[PROVISIONAL_LOCAL_ONLY]` and are not consumed by this bootstrap.
- No production session, admin provisioning, purchase limit, hold state machine, idempotency, audit durability, or route/service contract.
- No claim of product acceptance, performance, browser, concurrency, or production readiness.

## Known blockers for later lanes

- Frozen target open items and ADR-004 remain open unless separately approved and recorded.
- The reported on-screen confirmation/order-history/no-email rule is retained, but the direct email thread is not present in the repository.
- Product lanes must add their own strict RED → GREEN evidence and independent review.
