# ADR-006: Standalone feature modules and how they are tested

**Status:** `[TEAM]` accepted. Required by the Part 4 assignment ("modules must be standalone to support testing") and by Call 4's "definition of done".

## Decision
Each feature package contains:
- `service.py`: the rules, in plain Python. It knows nothing about Flask or SQL and talks to storage through a small interface (a "port").
- `postgres.py`: the PostgreSQL adapter that implements that port.

Two files pull everything together:
- `app/wiring.py` is the only place that connects services to adapters.
- `app/__init__.py:create_app()` is the main program. It builds the app with every feature included.

| Test layer | Folder | Needs | What it proves |
|---|---|---|---|
| Unit | `tests/unit/<feature>/` | nothing | Each feature's rules, using in-memory fakes |
| Contract | `tests/contract/` | nothing | Pages, redirects, CSRF and admin blocking, using fake services |
| Main program | `tests/test_main_program.py` | nothing | `create_app()` includes and wires every feature |
| Integration | `tests/integration/` | PostgreSQL | Adapters, concurrency and the full app end to end |

## Consequences
- `pytest` runs anywhere. Without `EVENTHUB_TEST_DATABASE_URL` the PostgreSQL tests skip, and CI always runs them.
- A feature can be developed and tested before the features it depends on exist. Call 4 also warned against building everything separately and connecting it only in the final week. The integration tests are the guard against that: they run on every upload.
