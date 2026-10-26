# EventHub bootstrap acceptance matrix

Statuses use the planning vocabulary: `PASS`, `RUNNABLE`, `DECISION-BLOCKED`, `DEFERRED`, and `FAIL`. A bootstrap `PASS` proves only the foundation seam, not product behavior.

| Row | Authority/source | Bootstrap proof | Status | Notes |
|---|---|---|---|---|
| BOOTSTRAP-001 | User bootstrap request; ADR-001/002 | `tests/test_bootstrap.py::test_app_factory_exposes_health_and_postgresql_configuration` | PASS | Flask app factory, `/healthz`, and PostgreSQL SQLAlchemy URI seam pass in the project venv. |
| BOOTSTRAP-002 | QA plan G0; ADR-002 | `tests/test_bootstrap.py::test_migration_seed_and_reset_entrypoints_round_trip_bootstrap_fixture` | PASS | Real PostgreSQL: reset, fresh migration, idempotent seed, read-back, and reset-to-empty. |
| system-003 | `TRACEABILITY.md` system-003; `[STAKEHOLDER]` | BOOTSTRAP-001 | PASS (foundation only) | Python/Flask is wired; no product routes are claimed. |
| system-004 | `TRACEABILITY.md` system-004; `[TEAM]` D1 | BOOTSTRAP-001 | PASS (foundation only) | One Flask application factory. |
| system-005 | `TRACEABILITY.md` system-005; `[TEAM]` D1/D2 | BOOTSTRAP-002 | PASS (foundation only) | One PostgreSQL migration/seed/reset seam; product schema is not implemented. |
| system-006 | `TRACEABILITY.md` system-006; reported Part 2/email-thread decision | Later confirmation/order tests | DEFERRED | Preserve reported on-screen confirmation, order-history reopening, and no email in v1; direct email source is absent. |
| identity, catalog, pricing, inventory, purchase, orders, audit, admin | Frozen target v2 and feature requirements | Later lane-owned tests | DEFERRED | No product behavior is implemented in bootstrap. |
| pricing-006 and related policy rows | Frozen target v2 open items 1–5; user defaults artifact | Policy-gated product tests | DECISION-BLOCKED | Temporary local/demo defaults are visible but do not close acceptance. |
| inventory-005..007 | Frozen target v2 D5/item 13 | Hold-state tests | DECISION-BLOCKED | Ten-minute duration is recorded; release/conversion state machine remains open. |
| identity-012/admin-004 | ADR-004/D4 | Admin boundary tests | DECISION-BLOCKED | Seed/config-only is a temporary MVP default, not approved administrator provisioning. |
| purchase idempotency/replay | Frozen target v2 anti-contamination clause | Later contract revision | DECISION-BLOCKED | Temporary default is recorded, but the frozen requirements exclude idempotency acceptance. |
| load, browser, retention, governance | Frozen target v2 open/deferred items | Later approved gates | DEFERRED | No unsupported NFR or production-governance claim is made. |

## Required evidence for this branch

- Focused RED/GREEN logs and exit codes are indexed in `docs/evidence/tdd/index.json`.
- The real PostgreSQL command path is documented in `README.md` and exercised by the bootstrap test.
- A clean branch commit and pushed remote ref are required before handoff; the commit SHA is recorded in the implementation result artifact, not guessed here.
