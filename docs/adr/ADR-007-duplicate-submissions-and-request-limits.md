# ADR-007: Duplicate submissions, request limits and re-checks in the purchase path

**Status:** `[TEAM]` accepted (Call 5). The numbers are `[TEMPORARY_MVP_DEFAULT]` until the customer confirms them.

## Context
Call 5 raised three problems with the one purchase path (`PurchaseCoordinator`):

1. **The buy button can fire twice** (Thuy, Priya). The requirements never said what should happen. Our first system test run proved it matters: two Quick Buy requests sent at the same moment created two orders (ST-31), and a second Pay showed the buyer an error page even though the first had succeeded (ST-30).
2. **Nothing limits how fast requests arrive** (Kenji, finding 2). A script sending 200 purchase requests a minute looked like an enthusiastic student.
3. **The student discount was decided once and trusted forever** (Kenji, finding 1). In our build the price is frozen on the hold for 10 minutes (purchase-013), so a buyer could start checkout with a `usf.edu` email, switch to another address, and still pay the discounted price.

## Decision

### One-time form keys (purchase-014)
- Every purchase form (Continue to checkout, Pay, Quick Buy, and the hidden form on each event card) carries a random `idempotency_key` (`secrets.token_urlsafe(24)`), made fresh each time the page is shown. HTML pages are sent with `Cache-Control: no-store`, so Back shows a fresh form.
- Inside the purchase transaction the coordinator inserts `(buyer, key)` into `idempotency_records` (the table existed since migration 0005 but was unused). The first request owns the key; its result is stored in the same transaction.
- A repeat with the same key gets the stored result back (the same hold or order), creates nothing, and is audited as `replayed`. A key used for a *different* request is refused (`idempotency_conflict`). A missing or malformed key is refused (`idempotency_key_required`).
- Concurrency comes from PostgreSQL: a second insert of the same primary key waits for the first transaction. If it commits, the second sees the stored result; if it rolls back, the second runs as new. Tested with 5 threads sending the same key (`tests/integration/test_call5_postgres.py`).
- The browser also ignores a second click on a purchase button (`data-single-submit` in `eventhub.js`). This is only a convenience: the server is the guarantee, because scripts, retries and slow networks bypass the browser.
- Keys are remembered for 24 hours (`IDEMPOTENCY_RETENTION_HOURS`), longer than the 12-hour maximum session. A buyer's expired keys are deleted when that buyer claims a new one.
- If a new request is over the request limit, its key is released again, so the same form works once the minute has passed.

### Request limit (purchase-015)
- At most 10 purchase requests per account per 60 seconds (`PurchasePolicy.rate_limit_requests` / `rate_limit_window_seconds`). Checkout starts, payments and quick buys all count, accepted or not. A normal purchase uses 2.
- Fixed window, one row per account in the new `purchase_rate_windows` table (migration 0006), updated with one `INSERT ... ON CONFLICT DO UPDATE`. It works across several web workers because the count lives in the database, not in process memory.
- Over the limit: HTTP 429, "Too many purchase attempts from your account. Please wait a minute and try again.", audited as `rate_limited`.

### Discount re-checked at payment (pricing-011)
- Eligibility was already decided from the account's email each time a quote is made. Call 5 adds a second check when the buyer pays: if the frozen quote has a discount and the current email no longer qualifies, the hold is released, nothing is charged, and the buyer is asked to start again (`eligibility_changed`).
- Accounts can now change their email (identity-014). It needs the current password, and an address another account already uses is refused. After 5 wrong passwords the session is ended, so a stolen session cannot be used to guess the password.

### Also in the purchase path
- **Sales close when the event starts** (purchase-018): checked when the hold is made and again at payment.
- **Specific rejection reasons** (purchase-017): `quantity_zero`, `quantity_negative`, `invalid_quantity`, `not_enough_tickets` (with the number left), `sold_out`, `limit_exceeded`, `sales_closed`, `rate_limited`, `not_authenticated`.
- **Purchases from people who are not logged in are recorded** (purchase-016) with no buyer, and nothing else is created. Recording is best effort (the redirect to login always works) and happens at most once per browser session every 10 seconds.

Validation order: auth → form key (a repeat is answered here, so it is never rate-limited or counted) → request limit → event → sales closed → currency → quantity → (pay: hold, sales closed, discount) → purchase limit → price → inventory → payment.

## Consequences
- An accidental double purchase cannot happen through any route, and every repeat is visible in the audit log.
- One buyer's purchase requests are handled one at a time (they share the counter row). Different buyers are not slowed down (tested, ST-37).
- Every caller of the purchase path must send a form key. The integration tests were updated to do so.
- **Accepted risks, recorded for the customer:**
  - The limit is per account. Someone with many accounts, or sending requests while logged out, is not limited by it. IP-based limiting belongs at the web server or proxy in front of EventHub.
  - Not-logged-in purchase attempts are recorded at most once per browser session every 10 seconds. A script that starts a new session for every request can still add rows; a CSRF token is still required.
  - A hold the system releases (sales closed, discount no longer valid) is stored with status `cancelled`, like a buyer's own cancel, because the database allows only the existing statuses. The audit row for that attempt records the real reason (`sales_closed`, `eligibility_changed`).
  - A fixed window allows up to 20 requests across the boundary of two windows.
  - Email ownership is not verified (pricing-012 `[OPEN]`). Someone can still register with an address they don't own. Only email verification, which the customer has not asked for yet, closes that.
