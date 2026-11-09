# Part 6 simplification log

Prompt used for the AI review: "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."

Each suggestion was checked by reading the code. Only S-02, S-03, S-04 and S-08 were implemented (one commit each, on top of e2de805).

## S-01 - app/purchase/service.py: start_checkout / pay / purchase

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Extract a shared `_attempt` wrapper for the three flows.
- **Category:** Duplication / structure
- **Verdict:** DEFERRED
- **Human reasoning:** High risk to idempotency replay, audit-on-reject and the guard/audit/remember ordering; needs its own characterization tests first.
- **Before proof:** Not run (not implemented).
- **After proof:** Not run (not implemented).
- **Behaviour-preservation note:** No code changed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-02 - app/purchase/service.py: _owned_active_hold, _still_on_sale, _discount_still_applies, _complete, cancel

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Five call sites call `inventory.release_hold` with identical keyword args plus a reason; add `_release(tx, buyer_id, now, hold, reason)`.
- **Category:** Duplication
- **Verdict:** ACCEPTED
- **Human reasoning:** Pure call-site compression. The reason is audited, so each was kept exactly: EXPIRED (hold expired), CANCELLED (sales closed), CANCELLED (eligibility changed), PAYMENT_FAILED, CANCELLED (buyer cancel). Verified by reading the diff.
- **Before proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on e2de805: 383 passed, 39 skipped, 87 deselected; ruff clean.
- **After proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on fa4d788: 383 passed, 39 skipped, 87 deselected; ruff clean. Diff stat (fa4d788~1..fa4d788): 1 file changed, 8 insertions(+), 15 deletions(-).
- **Behaviour-preservation note:** Same arguments; _release returns release_hold unchanged. The suite was run on the combined S-02+S-03 tree and again on the S-03 commit; S-02 alone was not run in isolation because the commit was split after testing.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-03 - app/purchase/service.py:_AttemptFacts.extra; app/wiring.py:PricingAdapter.discount_percent/eligibility_domain; app/pricing/service.py:QuoteService.policy

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Delete four unused members.
- **Category:** Dead code
- **Verdict:** ACCEPTED
- **Human reasoning:** Grepped app/, templates/, tests/ (py and html): no reader of any of them (other hits are same-named PricingPolicy/QuoteSnapshot fields, which stay). `parse_quantity` and `app.web.format_when` deliberately kept: tests import them. The now-unused `field` import was removed by ruff.
- **Before proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on e2de805: 383 passed, 39 skipped, 87 deselected; ruff clean.
- **After proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on c9f8143: 383 passed, 39 skipped, 87 deselected; ruff clean. Diff stat (c9f8143~1..c9f8143): 3 files changed, 1 insertion(+), 14 deletions(-).
- **Behaviour-preservation note:** Nothing referenced the removed members, so no runtime path changes. No test edited.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-04 - app/orders/service.py, app/admin/service.py, app/catalog/service.py, app/db/transaction.py: id validation

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** The "ASCII digits, at most 18 chars" check is copied four times; expose one `is_db_id`.
- **Category:** Duplication
- **Verdict:** MODIFIED
- **Human reasoning:** Suggested home (beside db_id in app/db/transaction.py) is wrong: importing it would pull SQLAlchemy (app/db/__init__ imports it) into DB-free domain services. Put it in a new dependency-free app/ids.py instead; db_id uses it too. Each caller keeps its own reaction: orders and catalog strip then return None; admin does not strip and sets before_id=None; db_id strips then returns None. One copy removes the chance of reintroducing the "²" crash (ST-20/21).
- **Before proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on e2de805: 383 passed, 39 skipped, 87 deselected; ruff clean.
- **After proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on 252c7cb: 383 passed, 39 skipped, 87 deselected; ruff clean. Diff stat (252c7cb~1..252c7cb): 5 files changed, 21 insertions(+), 6 deletions(-).
- **Behaviour-preservation note:** Predicate identical (isascii and isdigit and len<=18; empty string still invalid). The ST-20/21 Selenium tests are among the skipped tests in this environment, so they were not run; unit/contract/integration tests that cover these paths passed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-05 - app/purchase: OUTCOME_MESSAGES

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Move outcome messages into the i18n catalog.
- **Category:** Structure / i18n
- **Verdict:** DEFERRED
- **Human reasoning:** OUTCOME_MESSAGES is asserted verbatim in tests, has pluralisation placeholders, and is only worth it once translated errors are in scope.
- **Before proof:** Not run (not implemented).
- **After proof:** Not run (not implemented).
- **Behaviour-preservation note:** No code changed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-06 - app/web/__init__.py: 9 views

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** A `login_required` decorator across the 9 views.
- **Category:** Duplication
- **Verdict:** DEFERRED
- **Human reasoning:** Each view has a different `next` target and the purchase pay path must keep writing an audit row.
- **Before proof:** Not run (not implemented).
- **After proof:** Not run (not implemented).
- **Behaviour-preservation note:** No code changed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-07 - app/web/__init__.py: error handling

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Single ServiceError handler.
- **Category:** Duplication
- **Verdict:** DEFERRED
- **Human reasoning:** Status codes and the 503 stub must stay identical; admin/account/login/register re-render forms.
- **Before proof:** Not run (not implemented).
- **After proof:** Not run (not implemented).
- **Behaviour-preservation note:** No code changed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-08 - app/wiring.py: register, set_preferred_currency

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** The "currency is enabled" check is written twice; add `_require_enabled_currency(tx, code)`. Optional `_session_service` helper.
- **Category:** Duplication
- **Verdict:** MODIFIED (currency helper accepted; _session_service rejected)
- **Human reasoning:** Helper keeps `strip().upper()` in the callers and the error code `unsupported-currency`. register still checks only when a code was given; set_preferred_currency always checks (an empty code is still rejected). `_session_service` skipped: it would save about one line in three methods of different shape, not a clear win.
- **Before proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on e2de805: 383 passed, 39 skipped, 87 deselected; ruff clean.
- **After proof:** `python -m pytest -q -p no:cacheprovider` + `ruff check .` + `ruff format --check .` on b3c0aa1: 383 passed, 39 skipped, 87 deselected; ruff clean. Diff stat (b3c0aa1~1..b3c0aa1): 1 file changed, 8 insertions(+), 4 deletions(-).
- **Behaviour-preservation note:** Same condition, message and 400 status; the check still runs inside the same unit of work and before account creation.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-09 - app/orders, app/purchase: HoldView/OrderView

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Shared BreakdownDisplay.
- **Category:** Structure
- **Verdict:** DEFERRED
- **Human reasoning:** Touches flat template fields and es/JPY formatting across locales.
- **Before proof:** Not run (not implemented).
- **After proof:** Not run (not implemented).
- **Behaviour-preservation note:** No code changed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.

## S-10 - app/purchase/service.py: idempotency / request_rate ports

- **Prompt:** "Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication."
- **AI suggestion:** Make the ports required.
- **Category:** Coupling
- **Verdict:** DEFERRED
- **Human reasoning:** Unit tests omit them; guard ordering.
- **Before proof:** Not run (not implemented).
- **After proof:** Not run (not implemented).
- **Behaviour-preservation note:** No code changed.
- **Reviewer note:** AI-generated; needs a human teammate to review the diff before merge.
