# EventHub greenfield bootstrap

This branch is the shared foundation for the EventHub Flask/PostgreSQL implementation. It intentionally contains no product behavior.

## Authority and policy labels

The planning ledger is `eventhub_frozen_target_v2.md` with `TRACEABILITY.md`, ADR-001..004, and the feature requirements from the supplied deliverables. The temporary defaults authorized in chat on **October 26, 2026** are recorded as `[TEMPORARY_MVP_DEFAULT]` / `[PROVISIONAL_LOCAL_ONLY]` in `docs/ownership.md` and `seed/config.example.json`. They are not stakeholder or Minh approval. Production, CI, staging, and acceptance must fail closed when an unresolved policy is required.

The reported confirmation rule is preserved: on-screen confirmation plus order-history reopening, with no confirmation email in version one. The direct email thread is absent; see `docs/acceptance-matrix.md`.

## Prerequisites

- Python 3.12 or newer.
- Docker and Docker Compose for the real PostgreSQL path.
- A local virtual environment; global Python packages are not used.

## Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[test]'
```

`requirements.lock` records the verified environment used for the bootstrap evidence.

## Disposable PostgreSQL

Start the test database:

```bash
docker compose -f docker-compose.test.yml up -d --wait
```

Use this test-only URL:

```bash
export DATABASE_URL='postgresql+psycopg://eventhub:eventhub@localhost:55432/eventhub_test'
export EVENTHUB_TEST_DATABASE_URL="$DATABASE_URL"
export EVENTHUB_ENVIRONMENT=test
export EVENTHUB_RESET_ENABLED=true
```

The application has no SQLite fallback. `DATABASE_URL` is required and must use PostgreSQL. Reset is refused unless explicitly enabled and the environment is local, development, or test.

## Bootstrap commands

```bash
.venv/bin/python -m app.config.commands reset
.venv/bin/python -m app.config.commands migrate
.venv/bin/python -m app.config.commands seed
```

Equivalent installed entrypoints are `eventhub-reset`, `eventhub-migrate`, and `eventhub-seed`. `reset` recreates the disposable `public` schema without seed rows; `seed` is deterministic and idempotent. The only migrated table is `eventhub_bootstrap`, an infrastructure marker—not a product table.

## Run the app factory

With `DATABASE_URL` set:

```bash
.venv/bin/flask --app 'app:create_app()' routes
.venv/bin/flask --app 'app:create_app()' run
```

`GET /healthz` returns the bootstrap health response. No product routes exist in this branch.

## Tests

App-factory test:

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py::test_app_factory_exposes_health_and_postgresql_configuration -q
```

Real PostgreSQL bootstrap test:

```bash
EVENTHUB_TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/python -m pytest tests/test_bootstrap.py::test_migration_seed_and_reset_entrypoints_round_trip_bootstrap_fixture -q
```

Affected suite:

```bash
.venv/bin/python -m pytest tests/ -q
```

## Evidence and ownership

- `docs/evidence/tdd/index.json` indexes raw RED/GREEN logs and exit codes.
- `docs/ownership.md` defines the shared-path owner, authority labels, reported confirmation rule, and temporary defaults.
- `docs/acceptance-matrix.md` separates bootstrap PASS from deferred or decision-blocked product rows.
- `docs/IMPLEMENTATION_STATUS.md` records the intentionally partial scope.

Clean up the disposable database with:

```bash
docker compose -f docker-compose.test.yml down -v
```
