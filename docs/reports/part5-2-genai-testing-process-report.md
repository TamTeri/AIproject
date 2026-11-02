# Part 5, Deliverable 2: How the GenAI test-creation process went

**CEN 4020 AI Project, Part 5 · Team: Ian Koratsky, Minh Tam Nguyen**

## Summary

- **Did the first generated test cases run without errors?** No. On the first run against the Part 4 application, 64 of 84 test runs passed and 20 failed (8 min 15 s). Every test *ran*: the harness, the browser and the server all worked first time. But 20 assertions failed.
- **Why not?** The 20 failures were three different things:
  - **9 were expected.** They tested Call 5 behaviour that did not exist yet (email change, the labelled amount charged, the currency explanation, distinct messages).
  - **10 were caused by real bugs** in the application (5 defects, some failing several test variants), including a double purchase that created two orders, tickets sold for an event that had already started, and an HTTP 500 crash from a quantity of "²".
  - **1 was a bug in our generated test**: it read the page before the browser had loaded the next one.
- **Also, some tests passed for the wrong reason.** Three looked green but proved less than they claimed. One had an expectation copied from the old behaviour, as Priya warned ("generated tests inherit the code's assumptions").
- **What we changed:**
  - **Code:** we fixed the application for every real bug and built the Call 5 changes (one-time form keys, a request limit, a discount re-check, email change, closed sales, specific messages, ASCII-only number parsing).
  - **Tests:** we fixed the broken test helper (and, in run 4, two more tests with the same timing race), corrected one wrong expectation, and updated older tests only where a new requirement changed the expected behaviour.
- **End state:** all 87 Selenium runs pass against the final application, in about 2 minutes. So do 286 unit, contract, integration and process tests, including the last-ticket race 200 times. The 20-buyer load test meets its target (p95 ≈ 0.3 s against 1 s).

## Tools

| What | Tool |
|---|---|
| Writing the test cases, the harness and the fixes | Claude Code (Anthropic Claude Opus 5.5) in VS Code, working in the repository |
| Browser automation | Selenium 4.52 WebDriver; Google Chrome 156 headless (Edge and Firefox also supported) |
| Test runner and report | pytest 9, pytest-html 4 (HTML report with a screenshot of every failure), JUnit XML |
| Application under test | The real `create_app()` on a local port, with a real PostgreSQL 16 (Docker) |
| Load test | Plain HTTP from 20 threads (no browser), so it measures the server rather than Chrome |

## How we asked the GenAI tool for the tests

We gave the tool the assignment, the Call 5 transcript, the repository and these rules (the full instruction is in Appendix A):

1. **Spec first.** Write the new Call 5 requirements into `features/*/requirements.md` before any test or code.
2. **Tests from the specification, not the code.** Expected values come from requirement lines, Call 5 and the seed data. Every test names its requirement ids, and a test with none must not run.
3. **Black-box edge cases.** List the edge cases a tester who only sees the screen and the requirements would try, then turn each into a Selenium test.
4. **White-box edge cases.** Separately, list the cases that only someone who knows the code would think of, and mark them `whitebox`.
5. **Run them against the unchanged Part 4 application first**, save the log, and sort every failure into "the app is wrong", "the test is wrong" or "not built yet" before changing anything.
6. **One button.** A single command, a double-click file and a CI workflow, all producing a report.

Rule 5 was the important one. If we had built the Call 5 changes first and generated tests afterwards, the tests would have been written to match the new code, and we would have learned nothing about the old code.

A note on "black-box": the tool had already read the templates, so the tests use the real element ids (`#quantity`, `dd.total`). What is black-box is the expected results, which come from the requirements, not from reading the implementation. For the new Call 5 screens the tests *defined* the ids (`#amount-charged`, `#currency-source`), and the implementation then had to provide them.

## Run 1: the first generated tests against the Part 4 application

[Log: `docs/evidence/system-tests/run-1-first-generation.log`]

**84 runs: 64 passed, 20 failed.** Nothing failed to *start*. The live-server fixture, the database reset, Selenium Manager (which found a chromedriver matching the installed Chrome by itself) and the pytest-html report all worked on the first run.

### The 20 failures, sorted

| # | Test | What failed | Kind of failure |
|---|---|---|---|
| 1 | ST-31 Quick Buy sent twice at once | Two orders were created | App bug (Call 5's double purchase, confirmed) |
| 2 | ST-30 Pay sent twice at once | One order, but the second request got HTTP 409 "This checkout is already finished" | App bug: a successful buyer is shown an error |
| 3 | ST-44 Event that started yesterday | The page said "50 tickets left" and sold a ticket | App bug that nobody had noticed (see below) |
| 4 | ST-14 Quantity "2.0" | The browser accepts it; the server said "Choose a whole number" | App bug (small) |
| 5–7 | ST-20 Quantity "²", "①", "٣" | "²" and "①" gave HTTP 500; "٣" was bought as 3 tickets | App bug (white-box) |
| 8–10 | ST-21 `/events/²`, `/orders/①`, `/checkout/²` | HTTP 500 Internal Server Error on a plain GET | App bug (white-box) |
| 11 | ST-11 Thuy's six rejections | 0 and -2 had the same message; "too many" and "sold out" had the same message; the logged-out attempt left no audit record | Not built yet (Call 5 requirement) |
| 12 | ST-17 Logged-out purchase | The login page gave no reason | Not built yet |
| 13 | ST-65 Two browsers, last ticket | The race itself worked (one winner), but the loser read "not enough tickets for that quantity", not "sold out" | Not built yet (message) |
| 14–16 | ST-38, ST-39, ST-40 Email change | No email-change form existed (timed out waiting for `#new-email`) | Not built yet |
| 17 | ST-41 Amount charged | No `#amount-charged` element | Not built yet |
| 18–19 | ST-42, ST-43 Currency source | No `#home-currency-help` / `#currency-source` | Not built yet |
| 20 | ST-36 Eleven requests in a minute | `WebDriverException: Node with given id does not belong to the document` | Test bug |

### Why the test bug happened (ST-36)

The generated helper clicked "Continue to checkout" and immediately read the page text. The click starts a navigation, but Selenium returns at once, so the test read the old page just as the browser threw it away. Chrome reported the node as no longer in the document.

It only showed up in ST-36 because that test submits ten forms in a tight loop. The other tests happened to wait for something on the next page first.

**Fix (test):** `click_button()` now waits until the old page is gone (`staleness_of` the old `<html>`) before returning. It takes `navigates=False` for the one case where the browser itself blocks the submit (ST-12).

### The real bugs, and why no earlier test had caught them

- **Double purchase (ST-30/31).** The Part 4 tests were unit tests, a Flask test client and a Playwright script. None of them ever sent the *same* form twice at the same moment. The Part 4 schema even had an `idempotency_records` table (migration 0005), but no code used it.
- **Selling tickets after the event started (ST-44).** No requirement mentioned it, so no test checked it. We only noticed because the seed's demo event was dated Nov 1, 2026, the day before we ran the tests, and the site happily sold it. The customer and the team had both overlooked it, which is the kind of thing the assignment asks testing to find.
- **"²" crashes the server (ST-20/21).** It came from white-box knowledge: the code checked numbers with Python's `str.isdigit()`, which is True for "²", "①" and "٣", but `int()` cannot read "²" or "①". A black-box tester would rarely type a superscript two. Someone who knows `isdigit()` thinks of it at once. The same helper (`db_id`) guarded every id in a URL, so `/events/²` was a 500 on a page anyone can open.

### Tests that passed, but for the wrong reason

A green test is only useful if it would go red when the behaviour broke. Reviewing the 64 passes, we found three that would not:

| Test | Why it passed | What we did |
|---|---|---|
| ST-13 "huge" (a 20-digit quantity) expected the message "whole number" | The old app had one catch-all quantity message, which happened to contain "whole number". The expectation had been written from the old behaviour, not from purchase-017. A 20-digit number *is* a whole number; what it breaks is the purchase limit. | Test was wrong. We moved it to a new test, ST-22, which expects the limit message. Priya had warned about this in Call 5: "If the code misunderstands the requirement, tests generated from the code pass beautifully while validating the wrong behavior." |
| ST-32 / ST-33 double-clicking Pay and Quick Buy | Chrome itself drops the second submission of a form that is already submitting, so the server only ever saw one request. The test was green even though the server had the double-purchase bug. | Kept, because they test what a real thumb does. ST-30 and ST-31 send two simultaneous `fetch()` requests from the page (as a slow network or a script would), and those exposed the bug. |
| ST-37 "one buyer's limit does not slow another buyer" | There was no limit at all, so nothing could slow anyone down | Kept as a guard. It only became meaningful once purchase-015 existed. |

## What we changed so the tests passed

### Changes to the application (one per failing behaviour)

| Failing test(s) | Requirement | Change |
|---|---|---|
| ST-30, ST-31 | purchase-014 | One-time key in every purchase form, claimed in `idempotency_records` inside the purchase transaction; repeats replay the first result and are audited `replayed`. `Cache-Control: no-store`. Browser ignores a second click. |
| ST-36, ST-37 | purchase-015 | Per-account counter in the new `purchase_rate_windows` table (migration 0006): 10 requests per 60 s, then HTTP 429 and `rate_limited` |
| ST-38, ST-39, ST-40 | identity-014, pricing-011 | Email change (needs the current password; no duplicates). The discount is re-checked at payment; a no-longer-eligible hold is released. |
| ST-41 | orders-006 | Boxed "Amount charged to your card"; the USD price labelled "for reference only and not charged" |
| ST-42, ST-43 | identity-015, catalog-012 | Home currency at registration; "Preselected: GBP, your saved home currency" next to the choice; Quick Buy names the currency |
| ST-44 | purchase-018 | No sales once the event has started (checked at hold and at payment); "Ticket sales have closed"; buy forms hidden |
| ST-11, ST-17, ST-65 | purchase-016, purchase-017, audit-008 | A specific message for each reason, including "Only 3 tickets left" vs "Sorry, this event is sold out"; logged-out attempts audited with a message on the login page |
| ST-14, ST-20, ST-21 | purchase-002, system-001 | Quantities and URL ids accept ASCII digits only; "2.0" accepted as 2; length checked before `int()` |

### Changes to the tests

| Test | Change | Why it was the test, not the app |
|---|---|---|
| `support.click_button` (ST-36) | Wait for the next page | Selenium timing, as explained above |
| ST-13 → ST-22 | A 20-digit quantity now expects the limit message | The expectation came from old behaviour, not the requirement |
| ST-44 | The forced POST now includes a form key | Once every purchase form carried a key, a key-less POST was refused as "form out of date" before it reached the sales-closed check. A script copying the form would send one. |
| ST-12 | `navigates=False` | The browser blocks the submit, so no new page is expected |

### Run 2: after the changes

[Log: `run-2-after-call5-changes.log`] 87 runs, 87 passed, 0 failed (7 min 3 s). The count went from 84 to 87 because ST-13 lost one case and ST-22 (three cases) and ST-23 were added.

### Run 3: making "the press of a button" fast enough to press

7 minutes was too slow to run on every change. Timing showed that about 4 of every 5 seconds per test were spent starting and quitting Chrome, which takes a long time on Windows.

The tests now borrow a browser from a pool and give it back wiped (cookies, storage and page cleared). Each test still starts logged out with no cookies.

[Log: `run-3-browser-pool.log`] 87 passed in 2 min 11 s.

### Run 4: a test that passed twice, then failed

[Log: `run-4-flaky-st68.log`] 86 passed, 1 failed. ST-68, the admin rate form, had passed in runs 2 and 3. This time it found no error message after the admin saved a rate of -1.

The app was fine. ST-68 (and ST-61) clicked the row's Save button directly and checked the page straight away. That is the same timing bug we had already fixed in ST-36, but those two tests did not use the fixed helper. Whether the check ran before or after the next page arrived depended on how busy the laptop was.

**Fix (test):** a `submit_with(button)` helper that waits for the next page, used by both tests. We then ran both tests 5 times in a row (all passed) before the final run.

The same run also gave a warning: the default JUnit format drops the values the tests record (requirement ids, performance numbers). We switched pytest to `junit_family = "xunit1"`, which keeps them.

### Run 5: the final run against the final code

[Log: `run-5-final.log`, report: `system-tests-final.html`] 87 passed in 2 min 16 s, no warnings, after the code-review fixes below. The load test's p95 in this run was 0.313 s.

## Code review of the finished work

Before submitting, we ran an automated code review (Claude Code's review command) over every Part 5 change. All tests were green at the time, and it still found 10 issues. We checked each against the code:

| Issue found | Fixed? | Change |
|---|---|---|
| A repeat of a successful purchase could be refused as "too many attempts" (the request limit was checked before the form key) | Yes | The form key is looked up first; a repeat is answered and never counted. If a new request is over the limit, its key is released. |
| The logged-out redirect now wrote to the database, so a database error would show a 500 page instead of the login page | Yes | Recording is best effort; the redirect always works |
| Logged-out attempts were not limited at all | Yes | At most one record per browser session every 10 seconds |
| "Your account email changed" was shown even when the discount ended for another reason | Yes | Reworded: "The student discount no longer applies to your account (for example, because your email changed)." |
| The email-change form allowed unlimited password guesses from a stolen session | Yes | After 5 wrong passwords the session is ended |
| Expired one-time keys were never deleted | Yes | Removed when the same buyer claims a new key |
| If a page load was aborted, the purchase button stayed disabled until reload | Yes | The browser guard unlocks after 4 seconds, and when a page is shown again |
| The discount rule was written out twice in the pricing service | Yes | One shared helper |
| The form key was normalised in several places | Yes | Once |
| A hold released because sales closed is stored as `cancelled`, like a buyer's cancel | No (documented) | The database allows only the existing statuses; the audit row records the real reason (ADR-007) |

Each fix has a new test (7 in total: unit, contract and PostgreSQL). This fits Thuy's point about coverage: a fully green suite only shows that what was tested works. The first issue in particular sits between two Call 5 features (duplicate submissions and the request limit), and no test had combined them.

## Second-order failures: what the fixes broke

Changing the purchase path broke older tests, and every one of those failures had to be judged too:

| After | Failures | Cause | Fixed in |
|---|---|---|---|
| The Call 5 code changes | 26 unit and contract tests | 19 used in-memory fakes that lacked the new interface methods (`sales_closed`, `available`, `discount_still_applies`, `record_unauthenticated`). The other 7 asserted the *old* behaviour: the outcomes for zero, negative and "not enough" quantities, the "sold out" message, the Quick Buy button text, and the route arguments (which now include the form key). | The fakes (test doubles must follow the interface). Expectations were changed only where a new requirement changed the behaviour (purchase-017, catalog-012, purchase-014), and each change cites the requirement. |
| Requiring a form key | 13 PostgreSQL integration tests | They called the purchase path without a key, which purchase-014 now refuses | The tests send a fresh key, as every real form does. The end-to-end tests read it from the rendered page. |
| The request limit | The new 200-round race test | It reused the same two buyers for 200 rounds, so from round 11 the new limit correctly refused them | Test redesigned: two new buyers per round. Two Call 5 changes interacted, which is why Priya wants this test kept. |

## Traceability: "every requirement has a test"

Thuy's bar was "every requirement has a test that would actually fail if the behavior broke", not a coverage percentage. A script cannot judge "would fail", but it can find requirements no test even mentions.

The first run of `scripts/check_requirement_coverage.py` found that 18 of 100 requirements were not named by any test:
- Most were tested by Part 4 tests that never cited the requirement id. For example, audit-007 had `test_unexpected_error_rolls_back_and_still_leaves_an_audit_record`.
- A few had no test at all: system-007 (no native app or seat map) and the process requirements system-009/010/011.

We added the ids to the existing tests and wrote `tests/test_project_process.py` for the rest. 95 of 100 are now named. The other 5 wait on customer decisions, such as the organizational exception to the purchase limit, so there is nothing to test yet. CI now fails if a testable requirement has no test.

## Performance (ST-70)

20 buyers bought 3 tickets each at the same moment, giving 120 timed purchase requests. Three runs on the development laptop:

| Run | Median | p95 | Max | Target (p95) |
|---|---|---|---|---|
| 1 | 0.203 s | 0.355 s | 0.460 s | ≤ 1.0 s |
| 2 | 0.191 s | 0.292 s | 0.403 s | ≤ 1.0 s |
| 3 | 0.192 s | 0.305 s | 0.420 s | ≤ 1.0 s |

No server errors, and every event ended with the expected number of tickets sold. This is Werkzeug's development server on a laptop, so it shows the purchase path keeps up under concurrency. It is not a production capacity figure; Marcus's real sentence, and a production-like server, are still needed for that.

## What we learned

1. **Run the generated tests against the old code first.** Five real defects, including a double purchase, only showed up because the new tests ran before anything was "fixed". Generating tests after the fix would have produced green tests for the new code and taught us nothing.
2. **The browser can hide server bugs.** Chrome drops a double-clicked form submission, so the realistic double-click test was green while the server could still create two orders. Testing the server's guarantee needed a test that sends the requests itself.
3. **A green generated test can still be wrong.** One expectation ("whole number" for a 20-digit number) was written from the old behaviour. It only became visible when the messages changed. Every green result deserves the same question as a red one: would this fail if the behaviour broke?
4. **Most failures were not test errors.** Out of 20, one was the test's fault. Treating red results as "probably the test" would have hidden five real defects.
5. **White-box and black-box find different things.** Black-box thinking found the double purchase and the closed-sales hole. Only knowing the code found the `isdigit()` crash. Each list missed what the other found.
6. **Fixes interact.** Our own request limit broke our own race test. Running everything, every time, is what caught it.
7. **Review after green.** A code review of the finished, fully passing work still found 9 issues worth fixing, most where two new features meet.
8. **One green run is not proof.** ST-68 passed twice and then failed on a timing race the helper had already been fixed for. When a fix is found, look for every other place with the same pattern, not just the test that failed.
9. **Speed is part of "at the press of a button".** A 7-minute suite is one people stop running. Reusing browsers cut it to about 2 minutes without weakening any test.

## What a teammate still needs to do

`CONTRIBUTING.md` says AI-generated code gets a human review before it merges. This work was produced in one GenAI session and checked by an automated code review (above), but it has not been reviewed by a teammate yet. Before merging:
- read the new purchase-path code (`app/purchase/service.py`, `app/purchase/postgres.py`) and ADR-007;
- run `python scripts/run_system_tests.py --headed` once and watch the browser;
- confirm with the customer the `[TEMPORARY_MVP_DEFAULT]` values Call 5 created: the double-purchase behaviour, 10 requests per minute, the 1-second p95 target, and sales closing at the start time;
- optionally re-export the two Call 5 C4 PNGs from Structurizr Lite. The committed ones were rendered from the Mermaid export, so their layout differs from the earlier diagrams.

## Numbers

| | Part 4 (start of Part 5) | Run 1 | Final |
|---|---|---|---|
| Selenium system test runs | 0 (one manual Playwright script) | 84 (64 pass, 20 fail) | 87 pass |
| System test time | — | 8 min 15 s | 2 min 16 s |
| Unit, contract, integration and process tests | 216 | 216 | 286 pass |
| Requirements | 84 | 100 | 100 (95 named by a test; 5 waiting on decisions) |
| Real bugs found by the new tests | — | 10 failing runs from 5 defects | fixed, each with a test |
| Last-ticket race | 10 buyers for 2 tickets, once | — | 2 buyers for 1 ticket, 200 times, every run |

## Appendix A: instructions given to the GenAI tool

```text
Context: EventHub (Flask + PostgreSQL), repository at the latest main. Read features/*/requirements.md,
workspace.dsl, the migrations and the Call 5 transcript before writing anything.

1. Turn every Call 5 gap and finding into a requirement line tagged [Call 5] in features/<name>/requirements.md.
   Values nobody has decided are [TEMPORARY_MVP_DEFAULT] in one named constant. Never invent them silently.
2. Write Selenium system tests in tests/system/ that drive a real browser against the real app.
   - Expected results come from the requirement lines, Call 5 and the seed data, not from the code.
   - Every test carries @pytest.mark.requirement("<id>", ...); a test without a real id must stop the run.
   - Black-box: list the edge cases a tester who sees only the screen and the requirements would try
     (boundaries, bad input the browser lets through, tampered forms, double submission, logged out,
     other users' URLs, timing). Make each one a test.
   - White-box: separately list edge cases that come from knowing the code (parsing, locking, time,
     rounding, SQL patterns) and mark them @pytest.mark.whitebox.
   - Include Thuy's full journey and her six-rejection list exactly as she stated them.
3. Run the new tests against the UNCHANGED application first. Save the log. For every failure, decide
   whether the app is wrong, the test is wrong, or the behaviour is not built yet, before changing anything.
4. Then change the application, requirement first, with unit and PostgreSQL tests for each change.
   Change an older test's expectation only when a new requirement changed the behaviour, and say which.
5. One button: a single command, a double-click file and a CI workflow (on every change, plus a manual
   Run button). Each run writes an HTML report with a screenshot of every failure.
6. In the report, say what failed first, why, and what was changed (code or test) to make it pass.
```

## Appendix B: evidence

| File | What it is |
|---|---|
| `docs/evidence/system-tests/run-1-first-generation.log` | First run of the generated tests against the Part 4 app (64 pass, 20 fail) |
| `docs/evidence/system-tests/run-2-after-call5-changes.log` | After the Call 5 changes and test fixes (87 pass, 7 min) |
| `docs/evidence/system-tests/run-3-browser-pool.log` | With browser reuse (87 pass, 2 min 11 s) |
| `docs/evidence/system-tests/run-4-flaky-st68.log` | One intermittent failure from a test timing race (86 pass, 1 fail) |
| `docs/evidence/system-tests/run-5-final.log`, `system-tests-final.html`, `system-tests-final.xml` | The final run against the final code (87 pass), its HTML report and JUnit XML |
| `docs/evidence/system-tests/performance-st70.log` | Three runs of the 20-buyer load test |
| `docs/testing/system-test-cases.md`, `docs/testing/system-test-catalogue.md` | The test cases (Deliverable 4) |
