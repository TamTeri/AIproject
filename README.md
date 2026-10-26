# EventHub

A ticketing website for campus events, built with Python, Flask and PostgreSQL for CEN 4020 (AI Project, Part 4).

Buyers can:
- register and log in;
- search events by artist or venue;
- buy tickets in USD, EUR, GBP or CAD (USF students get a discount);
- reopen any order confirmation later.

Administrators update exchange rates and read the purchase-attempt audit log.

## Quick start

You need Python 3.12+ and a PostgreSQL database. Docker is the easiest way to get one.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'

docker compose -f docker-compose.test.yml up -d --wait     # PostgreSQL on localhost:55432

export DATABASE_URL='postgresql+psycopg://eventhub:eventhub@localhost:55432/eventhub_test'
export EVENTHUB_ENVIRONMENT=development EVENTHUB_RESET_ENABLED=true

.venv/bin/python -m app.db.commands reset     # empty schema, migrated
.venv/bin/python -m app.db.commands seed      # 6 demo events, 4 currencies
EVENTHUB_ADMIN_EMAIL=admin@eventhub.test EVENTHUB_ADMIN_PASSWORD='change-me-123' \
  .venv/bin/python -m app.db.commands create-admin

.venv/bin/flask --app 'app:create_app()' run
```

Open http://127.0.0.1:5000. Register with an `@usf.edu` email to see the student discount.

**Demo tips**
- On the events page, **click** a card to open it and **double-click** a card to Quick Buy one ticket.
- At checkout, pick the "declines" test card to see the payment-failure path.
- Log in as the admin to see every attempt at `/admin/audit`.

## Run the tests

```bash
.venv/bin/python -m pytest                    # unit + contract tests; PostgreSQL tests skip
EVENTHUB_TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/python -m pytest   # everything (216 tests)
```

The PostgreSQL tests reset the database they are given, so point them at a throwaway one.

**Real-browser check (optional):** with the server running on port 5055, `pip install playwright`, then run `.venv/bin/python scripts/browser_check.py`. It resets the database, drives Google Chrome through 15 scenarios (including single click and double click on event cards and the phone layout), and saves screenshots to `browser-shots/`.

| Folder | What it tests | Needs a database |
|---|---|---|
| `tests/unit/<feature>/` | Each feature's rules, using in-memory fakes | no |
| `tests/contract/` | Every page, redirect, CSRF check and admin block, using fake services | no |
| `tests/test_main_program.py` | `create_app()` includes and wires every feature | no |
| `tests/integration/` | Real SQL, 10 buyers racing for 2 tickets, and the full app end to end | yes |

## How the code is organised

```
app/
  __init__.py      main program: create_app() includes every feature
  wiring.py        connects each feature's service to its PostgreSQL adapter
  identity/        accounts, login, server-side sessions (30-min idle timeout)
  catalog/         event list, artist/venue search, event page
  pricing/         calculator.py (the only money math), eligibility.py, quotes
  inventory/       ten-minute holds; availability = capacity - sold - held
  purchase/        PurchaseCoordinator: the one purchase path (checkout + quick buy)
  orders/          order history and confirmation pages (buyer-scoped)
  audit/           append-only purchase-attempt records
  admin/           exchange rates + audit viewer (administrators only)
  web/             Flask routes, CSRF, security headers, eventhub.js
  db/              migrations runner, seed, reset, create-admin, transactions
templates/          HTML pages (responsive)
features/           requirements per feature (EARS style)
docs/adr/           architecture decisions (money, DB, admin, modules)
docs/reports/       Part 4 reports
workspace.dsl       C4 model (Structurizr) incl. the after-Call-4 component view
```

Each feature's `service.py` is plain Python behind a small interface, so it can be tested alone. Its `postgres.py` holds the SQL. See [ADR-006](docs/adr/ADR-006-feature-modules-and-testing.md).

## Temporary decisions

The customer has not confirmed these values. They are marked `[TEMPORARY_MVP_DEFAULT]` in the code, and pricing refuses to run outside local, development and test environments.

| Topic | Temporary value | Where |
|---|---|---|
| Student discount | 10% | `app/pricing/config.py` (`STUDENT_DISCOUNT_PERCENT_PLACEHOLDER`) |
| Eligibility | exact `usf.edu`, any letter case; no `+` addresses; no subdomains | `app/pricing/config.py`, `eligibility.py` |
| Purchase limit | 4 tickets per account per event | `app/purchase/models.py` (`PurchasePolicy`) |
| Hold length | 10 minutes | `PurchasePolicy` |
| Session | 30 minutes idle, 12 hours maximum | `app/identity/policy.py`, `sessions.py` |
| Admin accounts | operator command only | ADR-004 |
| Audit retention | kept indefinitely, append-only | migration `0005` |

See also [CONTRIBUTING.md](CONTRIBUTING.md), [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) and the [Part 4 reports](docs/reports/).
