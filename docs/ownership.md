# EventHub bootstrap ownership and authority

## Scope

This branch owns the shared greenfield foundation only:

- `pyproject.toml` and `requirements.lock`;
- `app/__init__.py` and `app/config/**`;
- `migrations/**`, `alembic.ini`, `seed/**`, and `docker-compose.test.yml`;
- `tests/conftest.py` and `tests/test_bootstrap.py`;
- `README.md`;
- `docs/ownership.md`, `docs/acceptance-matrix.md`, `docs/IMPLEMENTATION_STATUS.md`, and bootstrap evidence.

Product lanes own identity, catalog, pricing, inventory, purchase, orders, audit, administration, and web behavior. This branch does not create those modules or claim their acceptance.

## One-writer rule

The bootstrap implementer is the only writer for the shared foundation paths above. Later lanes must not edit migrations, the application factory, configuration seam, dependency manifest, bootstrap tests, or these shared reports without coordinator reconciliation. Reviewers are read-only.

## Authority and provenance

- Base repository: `iankusf/AIproject`, branch `eventhub/bootstrap`, based on design-only commit `3bd9414cd7c2f130fc00fbdad1ee1aa1bd03253`.
- Planning authority: `eventhub_frozen_target_v2.md`, `TRACEABILITY.md`, ADR-001..004, and the nine feature requirement files. `[STAKEHOLDER]`, `[TEAM]`, and `[OPEN]` labels remain intact.
- ADR-001 selects one Flask monolith as a `[TEAM]` decision. ADR-002 selects PostgreSQL as a `[TEAM]` decision. ADR-003 selects an administrator rate-management boundary and purchase-attempt audit viewer as a `[TEAM]` decision. ADR-004 leaves administrator provisioning `[OPEN]`.
- The source-backed confirmation rule is retained: Part 2 reports on-screen confirmation plus order-history reopening and no confirmation email in version one. The direct email thread is absent from this checkout; this is recorded as a reported email-thread decision, not as newly verified stakeholder evidence.
- Chat authorization dated **October 26, 2026** authorized use of this GitHub repository, creation of this greenfield branch, temporary MVP defaults, and push after verification. No Minh approval or stakeholder closure is inferred from that authorization.

## Temporary defaults and open policy

`seed/config.example.json` (and `seed/catalog.json` for the values the app reads) is the source for the user-authorized temporary defaults. They are recorded here as `[TEMPORARY_MVP_DEFAULT]` / `[PROVISIONAL_LOCAL_ONLY]`, never as stakeholder decisions:

- USD-only Decimal cents; 10% discount and exact case-insensitive `usf.edu` eligibility only in local/demo;
- discount, then conversion, then half-up final rounding;
- ten-minute hold duration; database-time-at-mutation; PostgreSQL transaction/row-conditional allocation; no second inventory subtraction on conversion;
- temporary four-ticket per-account/per-event limit;
- buyer-scoped idempotency/hash/replay (acceptance remains blocked because the frozen target excludes it);
- recommended validation precedence;
- payment failure means no order, exactly-once release, and failure audit;
- thirty-minute session timeout;
- seed/config-only administrator provisioning; administrator-only paginated audit reads;
- indefinite append-only audit for MVP; production governance remains open;
- explicit-button Quick Buy first. Call 4 then brought double-click Quick Buy into the first build (`app/web/static/eventhub.js`); the explicit button stays for touch screens.

The bootstrap foundation does not consume these product defaults. Production, CI, staging, and acceptance must fail closed when an unresolved policy is required. The exact discount, currencies, verification, rounding, limits, session policy, administrator lifecycle, audit governance, hold mechanics, and wire contracts remain `[OPEN]` for final acceptance.

## Evidence ownership

- `docs/evidence/tdd/` contains raw focused RED/GREEN logs and exit codes.
- `docs/evidence/tdd/index.json` is the bootstrap evidence index.
- PostgreSQL evidence belongs to this bootstrap lane only for migration/seed/reset plumbing; product persistence and concurrency evidence belongs to later lanes.
