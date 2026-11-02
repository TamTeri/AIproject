# Part 5, Deliverable 1: Design changes after Discussion #5 (Call 5: Testing)

**CEN 4020 AI Project, Part 5 · Team: Ian Koratsky, Minh Tam Nguyen**

Call 5 was about testing, but it changed the design as well. Kenji's two security findings block release, Darnell's student testers found two usability problems, and Thuy listed three behaviours nobody had ever specified. Our own system testing then found things the customer and the team had both overlooked.

Below, each change lists what Call 5 said, what we changed (requirements, model, design, code), and why. New requirements are tagged `[Call 5]` in `features/*/requirements.md`. The changed C4 views are `Container_PostCall5` and `Component_PostCall5` in `workspace.dsl` (images: `diagrams/structurizr-1-Container_PostCall5.png` and `diagrams/structurizr-1-Component_PostCall5.png`, rendered from the Mermaid export in `diagrams/call5-export/`). The purchase-path decisions are in [ADR-007](../adr/ADR-007-duplicate-submissions-and-request-limits.md).

---

## 1. The double purchase is now defined: one order, and the repeat sees the same result

**What Call 5 said:** Thuy: "If the buy button fires twice (slow page, impatient thumb) do we create two orders? One? Reject the second? Nothing in the requirements says." Priya: "An accidental double purchase is the most common real-world checkout bug there is."

**What we found when we tested it:** two Quick Buy requests sent at the same moment created two orders (system test ST-31, first run). Two Pay requests created one order, but the second showed the buyer "This checkout is already finished", which looks like a failure after a success (ST-30).

**What we changed**
- **New purchase-014:** a purchase form submitted more than once is processed once. At most one hold or order is created, every repeat is shown the first result, and each repeat is audited as `replayed`. It is marked `[TEMPORARY_MVP_DEFAULT]` because the customer still has to confirm it (Priya put it on the requirement-gap list).
- **Design:** every purchase form carries a fresh one-time key. The `PurchaseCoordinator` claims the key in `idempotency_records` inside the purchase transaction and stores the result there. The table had been in the database schema since Part 4 (migration 0005) but nothing used it. PostgreSQL's primary key makes a simultaneous duplicate wait for the first request and then replay its result.
- Pages are sent with `Cache-Control: no-store`, so pressing Back shows a fresh form. The browser also ignores a second click on a purchase button, but that is only a convenience: scripts and retries bypass the browser, so the server is the guarantee.
- **C4:** a new relationship, Purchase → database `idempotency_records`.

**Why "replay" and not "reject the second":** rejecting the duplicate shows an error to a buyer whose purchase succeeded, which is what ST-30 caught. Replaying shows them their order. It is the only option where the buyer can neither pay twice nor be told something false.

## 2. Kenji's finding 1: the discount follows the *current* email

**What Call 5 said:** "I registered with a USF address, got the discount. Then I changed my account email to a non-USF address. My discount stayed." Darnell: "That's a hole in my budget." Adaeze: "Requirements gap; it goes to email."

**What we found:** our build priced every quote from the account's current email, but it had no way to change an email at all, so Kenji's exact test could not be run. Our white-box review then found the same hole in a different place: the price, including any discount, is frozen on the 10-minute checkout hold (purchase-013). A buyer could start checkout as a student, change the email, and still pay the student price.

**What we changed**
- **New identity-014:** buyers can change their email on the Account page. It needs the current password, and an email another account already uses is refused.
- **New pricing-011:** eligibility is decided from the current email every time a price is calculated and again at payment. If a frozen quote has a discount the buyer no longer qualifies for, the hold is released, nothing is charged, and the buyer is told to start again at the new price.
- The Account page now says whether the current email gets the student discount.
- **New pricing-012 `[OPEN]`:** proof that the buyer *owns* the USF address (verification, and re-checking after graduation) is for the customer to decide. The switch already exists (`require_verified_email`, off). Until then, someone can still register with a friend's address. We recorded this as an accepted risk rather than inventing a verification rule.
- **C4:** Purchase → Pricing `discount_still_applies()`; Buyer → Identity "changes email".

**Why:** the discount is money. A rule checked once and trusted forever is the bug Kenji described. Checking at the moment of payment closes it whatever the reason for the change: a new email, a policy change, or a graduation.

## 3. Kenji's finding 2: request speed is limited per account

**What Call 5 said:** "A script hammering the purchase endpoint two hundred times a minute looks, to the current build, like an enthusiastic student." Priya called it backlog. Kenji said his findings block release.

**What we changed**
- **New purchase-015:** at most 10 purchase requests per account per 60 seconds (`[TEMPORARY_MVP_DEFAULT]`). Checkout starts, payments and quick buys all count; a normal purchase uses 2. Over the limit, the buyer sees "Too many purchase attempts from your account. Please wait a minute and try again." (HTTP 429), and the attempt is audited as `rate_limited`.
- **Design:** a fixed-window counter per account in a new table, `purchase_rate_windows` (migration 0006), updated atomically inside the purchase transaction. It lives in the database, not in the web process, so it still holds with several web workers.
- **C4:** Purchase → database `purchase_rate_windows`.
- **Accepted residual risk (ADR-007):** the limit is per account. Many accounts, or requests from people who are not logged in, need IP-based limiting at the web server or proxy, which is a deployment decision.

**Why:** we treated it as release-blocking, as Kenji asked, rather than backlog. Counting in the database was the simplest design that cannot be bypassed by sending requests to different workers.

## 4. Darnell's finding: the confirmation page now says which amount hit the card

**What Call 5 said:** three of eleven students were confused about the exchange rate, and one thought she had been charged the original amount. "The page shows both amounts (base price and converted total) and she couldn't tell which one hit her card. Her word was 'sketchy.'" Thuy's exit criteria: "the confirmation page is reworded".

**What we changed**
- **New orders-006:** the checkout and confirmation pages show one boxed amount: "Amount charged to your card: 41.40 EUR. This is the only amount you paid, in EUR." The US-dollar price is labelled "Ticket list price: 45.00 USD each. This US-dollar price is for reference only and was not charged. Converted at 0.92 EUR per 1 USD." The summary line "Total" became "Total charged".
- No money is computed in the template (pricing-007): the USD reference comes from the price frozen in the quote, formatted by `format_minor()`.

**Why:** the amounts were correct; the labels were not. One labelled amount answers the question the student actually had.

## 5. Darnell's finding: the preselected currency says where it comes from

**What Call 5 said:** two students "had their currency preset wrong and didn't notice until the confirmation page. Where does the default currency even come from?" Thuy: "it's the account's home currency chosen at registration, but nothing on screen ever says that."

**What we found:** in our build there was no currency choice at registration at all. Everyone defaulted to USD unless they found the Account page.

**What we changed**
- **New identity-015:** registration has a Home currency choice (USD unless changed), with the explanation "Preselected at checkout and used for Quick Buy. You can change it any time on your Account page."
- **New catalog-012:** next to the currency choice on the event page: "Preselected: GBP, your saved home currency. Change your home currency." The Quick Buy button says "Quick Buy 1 ticket in GBP", and the event list says which currency a double-click uses.

**Why:** a default nobody can see is a surprise. Saying where the default comes from, at the moment it is used, fixes it without taking the default away.

## 6. Thuy's validation list: distinct messages, and everything logged

**What Call 5 said:** "zero quantity, negative quantity, quantity above availability, sold-out event, unsupported currency, purchases while logged out, all rejected with distinct messages, all logged."

**What we found (ST-11, first run):** zero and negative shared one message, "too many" and "sold out" shared another, and a purchase from someone not logged in redirected to login without any message and without any audit record.

**What we changed**
- **New purchase-017:** each reason has its own message. Zero: "Choose at least 1 ticket." Negative: "...cannot be negative." Not a whole number: "...as a whole number, such as 2." More than are left: "Only 3 tickets left for this event. Choose 3 or fewer." Sold out: "Sorry, this event is sold out." The currency, limit and not-logged-in messages are also distinct.
- **New purchase-016:** a purchase from someone not logged in is recorded (no buyer, reason `not_authenticated`), creates nothing, and the login page says "Please log in to buy tickets. You will come back to this event afterwards."
- **New audit-008:** `replayed`, `rate_limited`, `not_authenticated` and `sales_closed` each have their own reason code. The audit outcome stays one of the four values the database allows.

**Why:** "not enough tickets" for a sold-out event, and silence for a logged-out buyer, were the cases Thuy said were distinct and logged. They were not, so the requirement and the code changed.

## 7. Thuy: a performance target that can pass or fail

**What Call 5 said:** "At no point in thirteen weeks has anyone written down how fast is fast enough." Adaeze: "Marcus owes us that sentence."

**What we changed**
- **New system-013 `[TEMPORARY_MVP_DEFAULT]`:** "With 20 buyers purchasing at the same time, EventHub completes 95% of purchase requests within 1 second, and no request fails with a server error."
- **New test ST-70** measures that sentence. On the development laptop the p95 was 0.29–0.36 s over three runs.

**Why:** Marcus was absent, so we could not get the real sentence. Rather than leave the performance exit criterion blocked, we wrote a placeholder with a number in it, labelled it as temporary, and made the test read it from one place. When Marcus answers, one number changes.

## 8. Thuy and Priya: the oversell test, kept forever

**What Call 5 said:** "simultaneous purchase attempts against an event with one remaining ticket. Ran it two hundred times." Priya: "Keep it forever."

**What we changed:** new inventory-009, and a permanent integration test that races two buyers for one ticket 200 times against real PostgreSQL (`EVENTHUB_RACE_REPEATS` to change the count), plus a browser version with two real Chrome windows (ST-65).

**What it taught us:** the first version reused the same two buyers for all 200 rounds. After our own new request limit (section 3), round 11 was refused as `rate_limited`. The limit was right and the test was wrong: each round now uses two new buyers. Priya warned about this kind of quiet breakage, and here two of our own Call 5 changes caused it.

## 9. Priya: tests trace to the specification, not to the code

**What Call 5 said:** "generated tests inherit the code's assumptions... Tests should trace to the specification, not to the implementation." Thuy: "every test carries a requirement reference."

**What we changed**
- **New system-015:** every system test names the requirement ids it proves (`@pytest.mark.requirement(...)`). The test run stops if a test has none, or names an id that does not exist.
- **New `scripts/check_requirement_coverage.py`, run in CI:** lists requirements no test names. Its first run found 18 untraced requirements. Most had tests that never cited the id; a few (system-007, the process requirements) had no test at all. Now 95 of 100 are named, and the other 5 wait on customer decisions.
- Black-box system tests were written from the requirements and Call 5 before the code was changed, then run against the Part 4 application (Deliverable 2 shows the results).

## 10. Thuy: browser tests at the press of a button, on every change

**What Call 5 said:** "Automated browser tests cover the full journey: register, log in, search, open an event, buy in a foreign currency, see the confirmation, find it in order history. They run automatically on every code change." The assignment adds: one button, Selenium, and a report.

**What we changed**
- **New system-014.** The Selenium suite in `tests/system/` has 57 test cases (87 runs) and passes against the final application. ST-01 is Thuy's full journey.
- One command (`python scripts/run_system_tests.py`), a double-click file on Windows (`run-system-tests.cmd`), and a GitHub Actions workflow with a Run workflow button that also runs on every push and pull request. Every run writes an HTML report with a screenshot of every failure.
- **C4:** a new container, "System test suite", and a "QA / developer" person in `Container_PostCall5`.

## 11. Things nobody had noticed, found by our system testing

| Finding | Found by | Change |
|---|---|---|
| Tickets were still sold for an event that had already started. The seed's demo event (Nov 1, 2026) was in the past on the day we tested, and the site still sold it. | Writing ST-44 (black-box) | New purchase-018 `[TEMPORARY_MVP_DEFAULT]`: sales close at the start time. This is checked when the hold is made and again at payment, the event page says "Ticket sales have closed", and the buy forms are hidden. The customer should confirm the cut-off (door sales?). Seed dates moved to 2027. |
| A quantity of "²" or a URL like `/events/²` crashed the server (HTTP 500), and "٣" (Arabic-Indic 3) was quietly accepted as 3 tickets | White-box: `str.isdigit()` is True for these characters, but `int()` cannot read all of them | Only ASCII digits are accepted, in quantities and in every id parsed from a URL. Tests ST-20, ST-21 and ST-23 (a 5,000-digit quantity, which Python's `int()` also refuses). |
| "2.0" passed the browser's number check but the server refused it | Black-box edge case ST-14 | A whole number written as "2.0" is accepted as 2 |

## 12. Priya: specifications must keep matching the code

**What Call 5 said:** "Under deadline pressure, code gets patched and spec files quietly fall out of date. The automated checks will warn; the team just has to not ignore the warnings." Kenji: "That's why my two findings block release instead."

**What we changed**
- Every code change in this part started with its requirement line (tagged `[Call 5]`), and `scripts/check_spec_alignment.py` reports no feature changed without its requirements file.
- The test catalogue (`docs/testing/system-test-catalogue.md`) is generated from the tests, and a test fails if it is out of date.
- The requirement-coverage check fails CI rather than warning, because untraced requirements were the problem we found.
- Kenji's findings are fixed and tested, not left as warnings.

## 13. Thuy's test structure, and Kenji's "basics", re-run on every build

**What Call 5 said:** Thuy: "Three layers: unit tests on individual functions, integration tests on how the pieces work together, and end-to-end tests through the browser. Then Kenji's security pass, then Darnell breaks things as a real user." Kenji: "passwords hashed, checkout and history behind login, quantities validated on the server, currency validated against the supported list."

**What we changed:** each layer now exists in the repository and runs automatically, so a passing result in Call 5 cannot quietly turn into a failing one later.

| Thuy's layer | Ours | Runs |
|---|---|---|
| Unit | `tests/unit/<feature>/` (in-memory fakes) plus `tests/contract/` (every page with fake services) | every commit (pre-commit) and CI |
| Integration (the purchase path's seams: identity, catalog, pricing, inventory, audit) | `tests/integration/` against real PostgreSQL, including `test_call5_postgres.py` | CI |
| End-to-end through the browser | `tests/system/` (Selenium) | CI on every change, and the Run button |
| Kenji's security basics | ST-50 to ST-57: hashing, login walls, ownership, admin block, CSRF, open redirect, injection; plus server-side quantity and currency tampering (ST-13, ST-16, ST-20) | with the system tests |
| Darnell's real users | ST-41 to ST-43 turn his three findings into checks; ST-01 keeps the order history the students liked | with the system tests |

**Why:** Thuy's structure only protects the project if it runs on every change. Each of Call 5's findings is now a test that would fail if the problem came back.

## What we decided *not* to change

| Raised in Call 5 | Decision |
|---|---|
| "Tell Marcus the students still want an app" | No change. system-007 (no native app in version one) still stands; the responsive site passes the phone-width tests (ST-09). Recorded for the post-launch meeting. |
| Proof of USF email ownership | `[OPEN]` (pricing-012): a customer decision. |
| Limiting many accounts, or anonymous traffic, by IP address | Accepted risk; belongs at the web server or proxy (ADR-007). |

## Call 5 exit criteria

| Thuy's exit criterion | Status |
|---|---|
| Every requirement-linked test passes | Done. 286 unit, contract, integration and process tests plus 87 Selenium runs pass against the final application. |
| Both of Kenji's findings fixed or formally accepted | Fixed (sections 2 and 3). The remaining risks are formally accepted in ADR-007. |
| The confirmation page is reworded | Done (section 4). |
| The double-purchase behaviour is defined and tested | Done (section 1): purchase-014, ST-30 to ST-35, unit tests, and a 5-thread PostgreSQL test. |
| The performance sentence exists | Temporary (section 7): it exists and is tested, with a placeholder number until Marcus confirms it. |
