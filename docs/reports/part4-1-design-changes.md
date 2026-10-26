# Part 4, Deliverable 1: Design changes after Discussion #4 (Call 4: Implementation)

Call 4 did not add new product features. It changed **how** EventHub is built: the build order, where certain logic must live, which open questions block code, and the team's working practices. Below, each change is listed with what we changed in our requirements, model or design, and why.

The changed C4 view is `Component_PostCall4` in `workspace.dsl`. New and changed requirements are tagged `[Call 4]` in `features/*/requirements.md`.

---

## 1. The audit trail is part of the purchase path from day one, not added later

**What Call 4 said:** Priya: "the audit trail woven in as the purchase path is built, not bolted on after", because "the earliest, buggiest purchases are the ones you most want records of."

**What we changed**
- The audit write sits **inside** `PurchaseCoordinator` (`app/purchase/service.py`), in the same database transaction as the hold and order. No purchase route can skip it (audit-004).
- Every outcome produces a record, not just successes. That includes every validation rejection, sold out, limit exceeded, payment declined, hold expired and cancelled.
- **New: audit-007.** If the attempt itself crashes, the transaction is rolled back and an `internal_error` record is written in a fresh transaction. The buggiest attempts are exactly the ones that crash, so without this they would leave no trace.
- **New: audit-005.** Every record includes time, user, event, quantity, currency and outcome (Thuy's list). We store the outcome as a category (`success`, `rejected`, `failed`) plus a specific `reason_code` (for example `sold_out`), because the database only allows those four categories.

**Why:** Logging that is added later means the first, riskiest purchases have no records. Putting the audit write in the one shared purchase path makes it impossible to forget.

## 2. One pricing function, and the money format decided first

**What Call 4 said:** "One function takes base price, quantity, discount eligibility, and target currency, and returns the amount. Nobody computes money in a page template." Kenji also asked that the money-representation decision be "written in the decision record before the first price is computed."

**What we changed**
- **New ADR-005 (Money representation)**, written before the calculator:
  - money is stored as integers in the minor unit (cents);
  - exchange rates are exact decimals (`NUMERIC(18,8)` read as `Decimal`), never `float`;
  - the order of operations is discount → convert → round once, half-up.
- **New file `app/pricing/calculator.py`** contains `calculate_price()`, the only code that does money arithmetic. Templates receive ready-made strings such as `"41.40 EUR"`.
- **New: pricing-007 and pricing-008.**
- **Prices are frozen at hold time (new: purchase-013).** The quote is saved on the hold and copied to the order, so a rate an administrator changes mid-checkout cannot change what the buyer was shown.

**Why:** Rounding and currency bugs are invisible until an auditor or buyer notices. One function with one documented rule gives one place to test and fix.

## 3. The discount percentage is still unknown: a flagged constant, not a guess

**What Call 4 said:** The discount percentage "is still, incredibly, not written down anywhere." Priya: "Please don't make one up. A named constant with a loud comment, fine, but flag it."

**What we changed**
- `STUDENT_DISCOUNT_PERCENT_PLACEHOLDER = 10` sits in `app/pricing/config.py` with a loud `[TEMPORARY_MVP_DEFAULT] NOT APPROVED BY THE CUSTOMER` comment.
- Tests use the constant, not the number 10, so changing it later won't break them.
- The pricing policy **fails closed**: it only runs in local, development and test environments. In production nothing can be priced until a real decision is recorded.
- **New: pricing-010.**

**Why:** Shipping a made-up number risks charging the wrong price. Blocking all work until the customer answers would stall the build. A clearly flagged, single-location placeholder lets us build and test now and change one line later.

## 4. Discount eligibility is its own small, testable function

**What Call 4 said:** Kenji: "normalize the email before checking. UPPERCASE@USF.EDU should qualify. And what about plus signs, name+party@usf.edu? Subdomains, @mail.usf.edu? None of that is specified." Priya: "Build eligibility as its own small, testable function; then when those answers arrive, they land in one place."

**What we changed**
- **New C4 component "Discount eligibility"**, used by Pricing. In code it is `evaluate_student_eligibility()` in `app/pricing/eligibility.py`.
- The email is trimmed and lower-cased first, so `UPPERCASE@USF.EDU` qualifies.
- The open questions are switches on the pricing policy: `allow_plus_addressing`, `allow_subdomains` and `require_verified_email`. All are **off** for now, so `name+party@usf.edu` and `@mail.usf.edu` do not qualify. When the customer answers, only those switches change.
- Each decision returns a reason (`eligible`, `plus_address_not_allowed`, `domain_not_eligible` and so on), which is saved with the quote.
- **New: pricing-009**, and Kenji's cases became unit tests (`test_call4_email_cases`).

**Why:** Unanswered questions should change one function, not be scattered through the code.

## 5. Who can read the audit trail, and for how long

**What Call 4 said:** Thuy: "who can read these, and how long do we keep them? They contain user activity." Marcus: "Presumably the admin area covers reading. Retention, no idea."

**What we changed**
- **New: audit-006.** Only administrators can read audit records. This is enforced twice: in the route, and again in `AdminService`.
- The audit table stays append-only: a database trigger rejects updates and deletes.
- **Retention is recorded as `[OPEN]`.** The temporary default is to keep records indefinitely.

**Why:** Audit records are personal activity data. Access needed a firm rule now. Retention is a policy decision we cannot make for the customer, so it is listed as open rather than guessed.

## 6. Double-click Quick Buy moved into the first build

**What Call 4 said:** Marcus wants "single click opens the page, and the double-click instant buy" in the first build so the customer can demo it. Priya agreed, since the event list comes with the catalog.

**What we changed**
- Before Call 4, the team's temporary decision was "explicit Quick Buy button first, double-click deferred". We changed it (`seed/config.example.json`, `docs/ownership.md`).
- The event cards now open the event page on a single click and Quick Buy one ticket on a double click. A 250 ms delay tells the two apart (`app/web/static/eventhub.js`).
- The double-click posts to the **same** server purchase path as checkout (purchase-011). It is not a shortcut around validation, limits or audit.
- The explicit Quick Buy button stays, because phones turn a double-tap into zoom.
- **New: catalog-011.** The C4 model has a new relation, Catalog → Purchase `quick_buy()`.

**Why:** It is a customer-visible demo feature, and it fits the catalog build. Routing it through the one purchase path keeps it safe.

## 7. Team practices: checks, CI and a definition of done

**What Call 4 said:**
- Make small reviewed changes, and review AI-written code twice as carefully.
- Add a contributing document, automatic style checks and pre-commit scripts.
- Add a specification-alignment check that warns when code changes but the spec doesn't.
- Run tests locally and in CI, where "the automatic run has the final say".
- A feature is done only when it ticks all four boxes: reviewed, tested, spec updated and checks passing.

**What we changed**
- `CONTRIBUTING.md` holds the workflow, the AI-review rule and the four-box definition of done.
- `.pre-commit-config.yaml` runs lint (`ruff check`), formatting (`ruff format`), the spec-alignment warning and the unit tests before each commit.
- `scripts/check_spec_alignment.py` warns when `app/<feature>/` changes without `features/<feature>/requirements.md`.
- `.github/workflows/ci.yml` runs lint, style and **all** tests against a real PostgreSQL on every push and pull request.
- **New: system-009, system-010 and system-011.**

**Why:** These turn the team's agreements into checks a machine enforces, so they don't depend on memory or goodwill.

## 8. Standalone feature modules so every feature can be unit-tested

**What the assignment and Call 4 said:**
- Modules must be standalone to support testing.
- Each feature lives in its own files that a unit-test program can include, and the main program includes all of them.
- Priya: building every piece separately "and connecting them in the final week cannot" be justified.

**What we changed (new ADR-006)**
- Each feature package has a `service.py` with its rules in plain Python. It talks to storage through a small interface (a "port"), and a `postgres.py` adapter implements that interface.
- `app/wiring.py` is the single place that connects services to adapters.
- `create_app()` is the main program that includes every feature. `tests/test_main_program.py` checks this.
- Unit tests use in-memory fakes, so they run without a database. Integration tests run the real adapters and the whole app against PostgreSQL on every upload.
- **New: system-012.**

**Why:** Standalone modules make unit testing possible. Integration tests on every upload stop the pieces from drifting apart. Section 1 of Deliverable 2 shows that drift really happened to us.

## 9. Smaller design decisions made during implementation

| Decision | Why |
|---|---|
| Server-side sessions: only a SHA-256 hash of the token is stored in `account_sessions`, with a 30-minute idle timeout and logout revocation (identity-013) | Logout and timeouts must actually end the session; a cookie alone cannot be revoked |
| The purchase locks the event row (`SELECT ... FOR UPDATE`) before checking the limit and capacity | Two simultaneous buyers can never both get the last ticket; tested with 10 parallel buyers |
| Administrators are created only by the `create-admin` operator command (ADR-004 temporary) | Who may be an admin is still `[OPEN]`; no self-service promotion is safest |
| CSRF token on every form, plus security headers (CSP, frame denial) | The admin area changes money-related data |
| Multi-currency: USD is the base, and buyers pay in any enabled currency (USD/EUR/GBP/CAD in the seed) | pricing-003 requires a currency choice; the earlier pricing code only allowed USD |

## What Call 4 said was settled, but we did not have the text for

Marcus said the hold, discount-scope, confirmation and purchase-limit questions were "settled in the emails". The email thread is not in our repository. We therefore kept the team's recorded temporary values and labelled them, rather than inventing the email's answers:
- 10-minute hold;
- discount applies to all events;
- on-screen confirmation and order history, with no email;
- 4 tickets per account per event.

If the emails differ, each value lives in one place (see the README table).
