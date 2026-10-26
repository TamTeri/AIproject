# Part 4, Deliverable 2: How the GenAI code-generation process went

> Draft. The facts below come from our repository history, test logs and the AI session. Lines in *[brackets]* are for each team member to add their own observations before submitting.

## Summary

- **Was the first code complete?** No. The first round produced well-designed pieces (contracts, a database schema, and services for identity, pricing and purchase), but the app could not do anything for a buyer. Every web page answered "service unavailable", and nothing connected the pieces to the database.
- **Was it correct?** Each piece passed its own tests (20 passed). Put together, the pieces were wrong in at least six ways (listed below). One of them stopped the app from starting at all.
- **How did we get to correct code?** We changed what we gave the AI and what we asked it to prove:
  - we gave it the **whole** design at once (the C4 components and their relationships, the requirements, Call 4's rules and the real database schema);
  - we made **one** integration pass own the wiring;
  - we required tests that run the **real** app against a **real** PostgreSQL, including 10 buyers racing for 2 tickets.
- **End state:** all 216 tests pass against PostgreSQL. Without a database, 195 pass and 21 skip. Lint and style checks are clean, and CI runs everything on every upload.

## Tools

| Round | Tool | How it was used |
|---|---|---|
| 1 | An AI coding agent run by a teammate | Parallel "lanes": bootstrap, db-schema, identity-catalog, pricing, purchase-audit, web-ui. Each ran in its own git worktree and became its own pull request. |
| 2 | Claude Code (Claude Opus) in VS Code | One integration session over the whole repository: finish the features, wire them, test against PostgreSQL, write the docs. |

## How we described the C4 component diagram to the LLM

Pasting a diagram image was not enough. What worked was turning each C4 component into a short, structured text block. Our `workspace.dsl` is already close to that format, so we gave it to the AI directly alongside the requirements. For each component we gave:

1. **Name and one-line responsibility**, from the DSL: for example "Inventory: fixed capacity per event, availability, checkout holds, atomic check-and-decrement."
2. **Its interface**: the calls other components make to it. The DSL relationships became function names, such as `purchase -> inventory "hold() / commit(): atomic"`.
3. **Its data**: the exact tables it owns, from the migrations (`docs/architecture/table-ownership.md`).
4. **Its requirements**: the matching `features/<name>/requirements.md` lines, word for word.
5. **Rules that cross components**, from Call 4: one pricing function; audit inside the purchase path; no money in templates; quick buy uses the same path.
6. **Open decisions**: which values are `[TEMPORARY_MVP_DEFAULT]`, and the instruction to keep each in one named constant rather than invent an answer.

See the appendix for the prompt template.

## Round 1: separate lanes (complete? correct?)

The first round split the C4 components into lanes and generated each one separately. Each lane followed a red/green testing routine (see `docs/evidence/tdd/`) and was merged as its own pull request.

**What it did well**
- Careful contracts: frozen dataclasses and bounded audit fields.
- A strong PostgreSQL schema: availability derived from a view, and an audit table made append-only by a trigger.
- Password hashing, and a reasonable purchase orchestration design.

**Why it was not complete**
- Most lanes produced *interfaces* without implementations. For example, `AccountRepository` and `AtomicInventoryPort` existed, but nothing implemented them against the database.
- The web lane plugged in a placeholder service object that answers every request with HTTP 503.
- There was no price calculator, no login method, no admin area, no order history and no inventory code.
- The README in that round said so itself: "No product routes exist."

**Why it was not correct**

Once we put the merged pieces together and ran them, we found these bugs. None of them showed up in a single lane's tests:

| # | Bug | Cause |
|---|---|---|
| 1 | `create_app()` crashed: `module 'app.db' has no attribute 'init_app'` | The schema lane added a package `app/db/`. Its name replaced the `db` variable that the bootstrap lane defined in `app/__init__.py`. |
| 2 | Every audit insert would have been rejected by the database | The purchase lane wrote outcomes like `payment_failed`, but the schema lane's check constraint only allows `success`, `rejected`, `failed` or `replayed`. |
| 3 | The hold status `released` would be rejected by the database | The purchase lane invented its own status names; the schema lane used `cancelled`, `expired` and `payment_failed`. |
| 4 | A sold-out event would crash the purchase code | `allocate_hold()` returns `None` when sold out, and the coordinator then read `hold.id`. |
| 5 | The web pages could never work | Routes were written against placeholder services; there was no wiring. |
| 6 | Pricing only allowed USD | That lane's slice was "USD-only", but pricing-003 needs a choice of currency. |

**Why this happened:** each AI run only saw its own lane. Two lanes that never saw each other's output both had to agree on the database's allowed values and on names. Each lane's tests used its own fakes, which agreed with that lane's assumptions, so every lane looked green. This is exactly what Priya warned about in Call 4: building every piece separately and connecting them at the end.

## Round 2: one integration pass (what we told the AI differently)

**What we changed in our instructions**
1. **Read everything first.** The AI was asked to read the existing code, every migration, the tests and the templates *before* writing anything, and to build on the teammate's design rather than replace it. (It had started writing its own data model from an older zip; we stopped it and pointed it at the newest `main`.)
2. **The database schema is the source of truth.** Enum values in Python must match the database's allowed values exactly. This rule fixed bugs 2 and 3.
3. **Give it Call 4's rules as hard constraints:**
   - one calculator, and ADR-005 written first;
   - audit inside the purchase transaction;
   - eligibility as its own function;
   - quick buy through the same path;
   - flagged constants for unknown values.
4. **Prove it against the real thing.** Unit tests with fakes were not enough. We required:
   - integration tests against PostgreSQL, including a 10-thread race for 2 tickets and an 8-thread race against one buyer's limit;
   - end-to-end tests through `create_app()`;
   - a smoke script that registers, logs in, searches, checks out in EUR, pays, reopens the order and checks the admin pages.
5. **Wiring is a single job.** `app/wiring.py` is the only place that connects features to the database, and `tests/test_main_program.py` checks that every feature is wired.

**Was round 2 correct the first time?** Mostly, but not completely. These problems were caught by tests or by review during the session:

| Problem | How it was caught | Fix |
|---|---|---|
| Two leftover broken lines in the web module: a call to a method that doesn't exist (`request.referrer_path_hint()`) and a meaningless `setattr` | The AI's own re-read before running anything | Deleted; replaced with a simple `_login_target()` helper |
| The "Your session expired" message never appeared | Contract test `test_expired_session_is_dropped_and_login_says_so` | The flag was kept for one request only; it now survives the redirect in the session |
| Tests with the same file name in different folders broke pytest collection | First run of the new unit tests | Switched pytest to `--import-mode=importlib` |
| `app/pricing` had no `__init__.py` (a namespace package) | `test_main_program.py` | Added the package file |
| 47 lint findings (unused imports, outdated syntax, import order) | `ruff check` | Auto-fixed; `ruff` then added to pre-commit and CI |
| Two test expectations assumed the URL `/` would be encoded as `%2F` | Contract test failure | The test was wrong, not the app; the expectation was corrected |
| The smoke test's admin rate change returned 400 | Manual smoke script | The script reused a form token from before login. The app was right: login issues a new token. Script fixed. |

There was also an environment problem: Docker hung, so the PostgreSQL tests ran against a temporary local PostgreSQL 15 on the same port. CI uses PostgreSQL 16 in Docker.

### Round 2b: testing in a real browser

All automated tests passed, but they drive the app through Flask's test client, not a browser. As a final check, we ran the real server and drove Google Chrome with Playwright through 15 scenarios:
- register, log in, search;
- single-click a card to open it, double-click a card to Quick Buy;
- checkout with a declined card, then an approved one;
- limit and sold-out messages; cancel;
- order history; saved currency;
- buyer blocked from admin; another buyer blocked from my order;
- logout; the admin audit log and rate update;
- a phone-width layout.

This caught problems that none of the 214 tests had caught:

| Problem | Why the tests missed it | Fix |
|---|---|---|
| Confirmation page showed "0.92000000 EUR per USD" | The unit test compared `Decimal("0.92000000") == Decimal("0.92")`, which is true; nobody looked at the *text* | `format_rate()` display helper; tests now check the rendered text |
| The admin page would show a rate of 150 as "1.5E+2" | Same: the number was right, the display wasn't | Same helper, with a contract test for 150 |
| Dates appeared as raw timestamps (`2026-10-26 17:52:36.657126-04:00`) | Tests checked that the date was present, not that it was readable | A `when` template filter: "Mon, Oct 26, 2026 · 5:52 PM" |
| Browsers logged a 404 for `/favicon.ico` on every page | Only a browser asks for it | Empty inline favicon |

We also made mistakes in our *own* browser test, which is worth recording. The selector `text=Pay` also matched the label "Simulated card (no real **pay**ment…)". Our expected value for a GBP quick buy (31.99) was wrong: £40.50 × 0.79 = 31.995 rounds half-up to 32.00, so the app was right and the test was wrong. Lesson: when a test fails, check the test as carefully as the code.

After these fixes, all 15 browser scenarios pass with no JavaScript errors, and the test suite has 216 tests.

## What made the difference

1. **Context beats cleverness.** The same model wrote correct code once it could see the whole system, especially the migrations. Most round-1 bugs were caused by missing context, not by bad code.
2. **Describe components as contracts plus data plus rules.** A component's responsibility, its calls, its tables and its requirement lines, in plain text, was the most reliable way to "describe the C4 Component diagram to the LLM".
3. **Fakes can lie.** Every round-1 lane was green with its own fakes. Only tests that ran the real database and the real app exposed the mismatches. We now keep both: fast fake-based unit tests for each standalone feature, and real-database tests in CI.
4. **Make the AI prove claims.** We asked for evidence (test runs, a smoke script, concurrency tests) rather than accepting "done". When it was wrong, the evidence showed it.
5. **Look at the screen.** Passing tests proved the values were right; only a real browser showed they were displayed badly.
6. **Humans still review.** AI-written code goes through a human reviewer before merging (`CONTRIBUTING.md`). *[Add: what did your reviewer actually catch or question?]*

## Our own review notes

*[Each member: one or two paragraphs. What did you check by hand? What surprised you? What would you prompt differently next time?]*

## Numbers

| | Round 1 (`main` @ 7ebc3a7) | Round 2 (`eventhub/part4`) |
|---|---|---|
| Buyer can complete a purchase in the app | No | Yes |
| Tests | 20 pass, 1 fail, 4 skip | 216 pass with PostgreSQL; 195 pass and 21 skip without it |
| Features with real database adapters | 0 of 8 | 8 of 8 |
| Integration bugs found when combining | 6 (table above) | fixed, with a test for each |

## Appendix: prompt template per component

```text
You are implementing the <Component> component of EventHub (Python 3.12, Flask, PostgreSQL).

Responsibility (from the C4 model): <one line from workspace.dsl>
Called by: <components and the calls they make, from the DSL relationships>
Calls: <components and calls>
Owns tables (source of truth = migrations/versions/*.py): <tables + allowed values>
Requirements (implement all, cite IDs in tests): <paste features/<name>/requirements.md>
Cross-cutting rules (Call 4):
  - Money only in app/pricing/calculator.py (ADR-005: integer minor units, Decimal rates)
  - Every purchase attempt goes through PurchaseCoordinator and is audited in the same transaction
  - Unknown policy values: one named constant marked [TEMPORARY_MVP_DEFAULT]; never invent
Structure:
  - app/<name>/service.py: rules only, no Flask/SQL, depends on a Protocol port
  - app/<name>/postgres.py: SQL adapter for that port
  - tests/unit/<name>/: tests with in-memory fakes; tests/integration/: real PostgreSQL
Before finishing: run the whole test suite against PostgreSQL and show the output.
```
