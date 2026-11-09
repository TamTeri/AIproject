# Part 6, Deliverable 2: How the GenAI maintenance process went

**CEN 4020 AI Project, Part 6 · Team: Ian Koratsky, Minh Tam Nguyen**

This report covers how the maintenance work went: what changed because of Discussion #6 (Call 6), what changed for maintainability, and why. What the design now looks like, with every Call 6 item traced to a requirement, code and test, is in the companion [Deliverable 1](part6-1-design-changes.md). We do not repeat that trace table here.

## Summary

- **What we did:** we treated Call 6 (a 1.3 release that charged 4,500 yen as 45 yen, rolled back in eleven minutes, followed by Darnell's request for Spanish and regional formats) as a maintenance job on the Part 5 code. We went requirements, then ADRs and models, then code, then tests, with no shortcuts, which was Priya's condition in the call.
- **What is real and what is not:** the incident comes from the assignment's scenario. This repository never deployed a 1.2 or a 1.3. The Part 5 result is tagged `v1.2.0`; the maintenance release is `1.3.0` (pyproject and `/healthz` say so). The git tag `v1.3.0` is created only after a green CI run, and that has not happened yet.
- **The exact bug could not happen here, but its pattern could.** JPY was allowed (ADR-005) but not seeded. The same latent pattern was present: a silent default exponent of 2 at four sites, a hardcoded `("USD", 2)` list price in two places, and a contract-test fake that formatted with `/100:.2f`. We removed all of it. A missing exponent is now an error.
- **How we worked:** five adversarial AI reviewers read the Call 6 transcript against the repository. Three planners turned that into plans. Then we split the work into five streams in separate git worktrees with disjoint file ownership. All five merged with no textual conflicts, and integration still needed four fixes. A two-lens review of the merged diff found ten problems, which we fixed.
- **GenAI simplification:** we asked the tool to find code to simplify. It returned ten suggestions (S-01 to S-10). We accepted four and deferred six, because the code those six touch has no characterization tests. We think that decision is part of the maintainability work, not a gap in it.
- **Verification, stated exactly:** on the merged branch the unit and contract suite gives 383 passed, 39 skipped (PostgreSQL), 87 deselected (Selenium). Ruff is clean. `requirement-coverage --strict` and spec alignment pass. **We did not run** any PostgreSQL integration test (including the three new files) or any Selenium system test, because the development machine has no Docker or PostgreSQL. Their proof is the GitHub Actions run after the push, which has not happened. A proof checklist for that is in the section "Proof checklist and open human decisions".

## Tools

| What | Tool |
|---|---|
| Analysis, planning, code, tests, docs | Claude Code (Anthropic Claude Sonnet 5.5), working in the repository, using subagents for review and planning |
| Parallel work | git worktrees, one per stream, merged into one integration branch |
| Checks run locally | pytest, ruff, `requirement-coverage --strict`, spec alignment check |
| Checks that need CI | PostgreSQL 16 integration tests and the skip gate (`ci.yml`), Selenium tests (`system-tests.yml`) |
| Models | Structurizr DSL (`workspace.dsl`) with `PostCall6` views |

## How we asked the GenAI tool

We gave the tool the assignment, the Call 6 transcript and the repository, and asked for work in this order. The prompts are summarised here and the simplification prompt is verbatim in Appendix A.

1. **Do not trust the story, check it against the code.** Five reviewer subagents each took one angle and tried to break the transcript's claims: QA, security, requirements and traceability, architecture, and operations (as a devil's advocate). We asked them for findings the repository could prove or disprove, not for opinions.
2. **Plan before writing.** Three planner subagents produced a plan each, for the design report, the code and the process.
3. **We chose the scope.** The tool offered smaller and larger options. We chose the full scope and asked to restructure it for parallel work, so we could use five streams instead of one long sequence.
4. **Spec first, still.** The Call 6 requirements, three ADRs and the model changes were committed before the code that implements them (see the commit list in Appendix B).
5. **Review the merged result with fresh eyes**, as two lenses: correctness and security; tests and document consistency.
6. **Ask the tool what to simplify**, then judge each answer ourselves.

## Step 1: AI-assisted analysis of Call 6

Five reviewers read the transcript against the repository. These findings changed the plan:

| Finding | What it changed |
|---|---|
| JPY is allowed but not seeded, so the 45-yen failure cannot occur here | We stopped short of claiming we "reproduced" the incident and wrote the honesty section in Deliverable 1. We seeded JPY on purpose so the yen path is exercised by tests. |
| A contract-test fake formats money with `/100:.2f` | The test would have agreed with the bug. The fake now follows the same exponent rule as production. |
| The exponent silently defaults to 2 in four places | pricing-014: no default, fail loudly. |
| The audit table stores no totals, so an alert cannot run on audit rows | The alert (audit-009) runs on `orders`, which has the totals. |
| The database is PostgreSQL, not a file (Kenji asked about "that file") | The backup runbook uses `pg_dump`, not file copying. |
| Rate edits left no history | New table `exchange_rate_history` (migration 0007). |
| A green `pytest` can pass while the PostgreSQL and Selenium layers are skipped | A CI skip gate: any skipped test fails the CI job (system-017). |

Not every claim held up. One planner assumed JPY was already seeded. A reviewer found that the exchange-rate `CHECK` constraint already existed, so a migration we had planned for it was dropped. This is the main lesson of this step: AI statements about the code are leads and have to be checked against the code.

## Step 2: Planning and splitting into streams

We split the work into five streams, each in its own worktree, each owning a fixed set of files:

| Stream | Scope |
|---|---|
| A | Money core: calculator, single price presenter, required exponent, Currency type, JPY seed, money tests |
| B | Admin rates: history table, 25% change guard |
| C | Localization: en/es catalogs, locale resolution, regional date and money formatting, templates |
| D | Alert and operations: `check-orders`, order-watch workflow, backup/restore scripts, runbooks, `/healthz`, CI skip gate |
| E | Requirements, ADR-008 to ADR-010, `workspace.dsl`, project documents |

Disjoint ownership worked: **all five merged with zero textual conflicts.**

It was not clean. Every stream still touched one or two files it did not own. The ones we recorded: the confirm flag for the rate guard needed edits in `wiring.py` and the web services, and the stream changes needed edits in `test_bootstrap` and `test_schema`. Ownership alone is not enough; we needed a short shared list of "interface" files that any stream may touch, agreed before starting. We did not have one.

## Step 3: Integration

Merging without conflicts did not mean the result worked. Four things broke when the pieces met:

1. **Schema test counts.** Seeding JPY changed the number of seeded currencies from 4 to 5. `test_schema` and `test_bootstrap` counted 4.
2. **System test ST-61.** It edits the CAD rate from 2.00 to 1.50 as part of a flow. Stream B's 25% guard (a rate edit of more than 25% needs confirmation) correctly rejects the old test edit, which is +45%. We changed the test value to 1.50, a change within the limit. The behaviour under test is unchanged, and the guard is the new requirement, so we changed the test and not the guard. This test is a Selenium test and we did not run it locally.
3. **Missing test for system-023.** `requirement-coverage --strict` failed because the yen-under-localization requirement had no test naming it. We added the test.
4. **Catalogue.** The system-test catalogue had to be regenerated.

After these four fixes the local suite was green (numbers below).

## Step 4: Two-lens review of the merged diff

We ran the review after the suite was already green. It found ten things worth fixing and two sets of known limits.

**Fixed (commit `00856ce`):**

| Finding | Why it mattered | Fix |
|---|---|---|
| `test_multicurrency.py` used the column name `currency` instead of `currency_code` | Would have failed the PostgreSQL CI run. We could not see it because we cannot run PostgreSQL locally. | Column name corrected |
| Rate lock race for a currency that has no row yet | Two edits at once could both pass the check | Lock the `currencies` row first |
| Alert windows could overlap or leave gaps; `--since-minutes 0` scanned about 19 years | Duplicate or missed alerts; a huge scan | Default 60 minutes; 0 is honoured as written |
| `restore.sh` had no confirmation guard | One mistyped command could overwrite a database | Needs `EVENTHUB_RESTORE_CONFIRM=yes` |
| `backup.sh` set `umask` after creating the file | A dump could briefly be world-readable | `umask` first |
| `order-watch.yml` had no `permissions:` block | Workflow ran with default token permissions | Minimal permissions block |
| Release runbook said 1.3.0 adds no migration | Migration 0007 exists; the rollback instructions would have been wrong | Runbook corrected |
| Acceptance matrix marked system-018 PASS (temporary) with no tag and no drill | Overclaim | Now OPEN |
| ADR-009 spoke of a "notification port" | There is no such abstraction; there is a log line and a failing scheduled job | Reworded to say that |
| A skip-gate test was labelled system-018 | It belongs to system-017 | Relabelled |
| `anomaly.py` used the literal 2 as the base exponent | The same silent-default pattern we had just removed | Imports `BASE_CURRENCY` |
| A test read the production default as its own expectation | A test that copies the code cannot catch the code being wrong | Hand-written literal |

Three of those (the acceptance matrix, the ADR wording and the runbook) were our documents overclaiming. We counted them as three separate cases in the lessons below.

**Known limits we did not fix:**

- The alert compares `total_minor` (which includes any discount) with the event's *current* base price. A discount of more than 50%, or a price edit after the order, can cause a false alarm. It never causes a missed incident of the kind in Call 6, but it can be noisy.
- `/healthz` returns 200 with `alembic_head: "unknown"` if the database is down. It is a liveness check, not a readiness check.
- The session cookie has no `Secure` flag.
- Selenium tests such as ST-02 assume an English default browser. Localization changes what a Spanish browser would see.
- `/admin` templates and flash messages are not translated.
- The two `PostCall6` diagram PNGs are not exported.

## What changed because of Discussion #6

This is the short version. The trace is in Deliverable 1.

- **Requirements:** 11 new ids tagged `[Call 6]`: pricing-014, admin-006, audit-009, and system-016 to system-023.
- **Decisions:** ADR-008 (money formatting and minor units), ADR-009 (release gate, restore, backup, order alert), ADR-010 (localization).
- **Code:** a single price presenter shared by checkout, confirmation and history; the exponent now required; JPY seeded; rate history and the 25% guard; the order monitor and `check-orders`; en/es catalogs with locale-aware dates and money; `/healthz` with version and Alembic head.
- **Operations:** `backup.sh`, `restore.sh`, two runbooks, a scheduled order-watch workflow, and a CI job that fails on skipped tests and checks the migration round trip.
- **Models:** components Localization and Order monitor, external system Alert channel, views `Container_PostCall6` and `Component_PostCall6`.

## What changed for maintainability, and why

We separate the structural changes from the cleanup because we think the first group mattered more.

### Structural changes

1. **One price presenter.** Checkout, confirmation and order history each used to build their own price breakdown. A bug fixed in one could stay in the others. `app/pricing/presenter.py` is now the only place that builds it. This is the change that makes the next currency, or the next display bug, a one-place fix.
2. **A required exponent, not a default.** A default of 2 is how a missing piece of data turns into a wrong amount in production. Now if the currency does not supply its exponent, the code raises. Failing loudly costs a crashed page in the worst case; failing quietly cost 4,455 yen per ticket in the scenario.
3. **A `Currency` type** that carries the code and its exponent together, so that the two cannot be passed separately and mismatched.
4. **Localization kept out of the money path.** ADR-010 decides that the locale chooses separators and symbol position, and the minor unit chooses the number of decimals. Locale never changes an amount (`test_locale_never_changes_the_amount`). Adding a language means adding a catalog file, not touching pricing.
5. **A CI skip gate.** A passing `pytest` could hide the fact that the PostgreSQL and Selenium layers never ran. `scripts/fail_on_skips.py` makes a skip a failure in CI.
6. **Runbooks and a recorded release process.** Release, rollback-first, backup and restore are now written down, with tags `v1.2.0` and `v1.3.0` so an old version can be checked out.
7. **Alert on the data we have.** The monitor reads `orders` and base prices, flags totals outside 50% to 200% of the base price per ticket (in USD equivalent), and puts no personal data in the message.

### GenAI simplification pass

We gave the tool this prompt (also in Appendix A):

> Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication.

It returned ten ranked suggestions, S-01 to S-10. The per-suggestion reasoning, verdict and before/after proof are in `docs/reports/part6-simplification-log.md` (written separately and merged separately; we cite it by id and do not copy it).

| Verdict | Suggestions | Short reason |
|---|---|---|
| Accepted | S-02 (`_release` helper), S-03 (dead code), S-04 (`is_db_id`), S-08 (enabled-currency helper) | Small, local, and the behaviour is already covered by tests that pass before and after |
| Deferred | S-01 | Touches idempotency and audit ordering; a reorder could change what is recorded on a replay |
| Deferred | S-05 | Tests assert messages verbatim; merging message code would break them or hide a changed message |
| Deferred | S-06 | Redirect targets differ between the cases it would merge |
| Deferred | S-07 | Status codes differ between the cases it would merge |
| Deferred | S-09 | Locale formatting spans several templates, and we had just changed them in stream C |
| Deferred | S-10 | Tests omit ports, so the refactor would not be protected by them |

The honest reading is that the tool is good at spotting duplication and bad at knowing what the existing tests do not pin down. Deferring a refactor that has no characterization test is the maintainability judgment, because a "simplification" that changes behaviour in an untested path is how Call 6 happened. Where we did simplify, a test that passed before had to pass after. We did not write new characterization tests for the six deferred areas. That is a possible next step if the customer wants those areas cleaned up.

## Numbers

| | Before (v1.2.0) | After (integrated tip) |
|---|---|---|
| Unit and contract tests | 257 passed, 29 skipped | 383 passed, 39 skipped, 87 deselected (Selenium) |
| PostgreSQL integration tests run locally | 0 (skipped) | 0 (skipped); 3 new files not run |
| Selenium system tests run locally | 0 in this environment | 0 |
| New requirement ids | n/a | 11 |
| New ADRs | ADR-001 to 007 | 3 more (ADR-008, 009, 010) |
| New migrations | up to 0006 | 1 (0007, rate history) |
| New modules and scripts | n/a | `app/pricing/presenter.py`, `app/audit/anomaly.py`, `app/i18n/` (`catalog`, `formatting`, `locales`, `en.json`, `es.json`), `scripts/backup.sh`, `scripts/restore.sh`, `scripts/fail_on_skips.py`, `.github/workflows/order-watch.yml` |
| Files changed, v1.2.0 to tip | n/a | 78 files, 2,422 insertions, 139 deletions |
| of which `app/` / `tests/` / `docs/` | n/a | 19 files (+652, -45) / 21 files (+1,052, -12) / 13 files (+351, -2) |
| Commits since v1.2.0 | n/a | 23 |
| Lint | n/a | ruff clean |
| Requirement coverage, spec alignment | n/a | `--strict` OK, OK |

The "before" test counts are the Part 5 final unit/contract figures stated by the team. The "after" counts are from the last local run on the integrated tip.

## Lessons and what went wrong

1. **Review caught real test bugs.** The wrong column name in `test_multicurrency.py` would have failed the first PostgreSQL CI run. We only found it because a reviewer read the test against the schema, not because anything ran.
2. **Our documents overclaimed in three places** (the acceptance matrix PASS, the ADR "notification port", the runbook saying no migration). Each was caught on review and corrected. Writing "done" is easy for the tool and for us; every "passed" in a document needs a log behind it.
3. **Parallel streams work if files are disjoint, and they never quite are.** Zero conflicts, but each stream still touched one or two files outside its list (`wiring.py`, the web services, `test_bootstrap`, `test_schema`). Next time we agree a list of shared interface files at the start.
4. **The AI agents cannot run PostgreSQL or Selenium here, so a human-run CI is required.** About a third of the new tests live in layers we could not run. We therefore wrote the reviews to include "would this fail in CI" and still cannot call those tests green.
5. **Localization puts English-asserting Selenium tests at risk.** Tests that assert English text assume an English browser. We did not run them against the new code.
6. **A new guard broke an old test (ST-61).** Correct behaviour on both sides; the test needed a new value. It is the same pattern as Part 5, where our own request limit broke our own race test.
7. **A test that reads the code's default as its expectation cannot fail.** We found one and replaced it with a hand-written literal. This is also the original lesson from Priya in Call 5.
8. **Re-verify every AI claim against the code.** A planner assumed JPY was seeded, and a planned migration was dropped when a reviewer found the `CHECK` already existed. In both cases the first answer was confident and wrong.

## Proof checklist and open human decisions

### Proof checklist (not done yet)

- [ ] Push the branch and open a pull request.
- [ ] Wait for the GitHub Actions run: `ci.yml` (PostgreSQL 16, skip gate, migration round trip) and `system-tests.yml` (Selenium). Fix anything that fails; we expect we may have missed something in the layers we could not run.
- [ ] Attach the Actions run URL and logs to `docs/evidence/part6/`.
- [ ] After a green run, create the tag `v1.3.0`.
- [ ] Demonstrate that an old release is restorable: `git checkout v1.2.0`, run its tests, and keep the log.
- [ ] Run the backup and restore drill once and record the result (system-019 stays OPEN until then).
- [ ] Export `Container_PostCall6` and `Component_PostCall6` from Structurizr to `diagrams/`.

### Human decisions still open

- Backup owner.
- Alert recipient and channel.
- JPY customer sign-off (Darnell's side).
- Native-speaker review of the Spanish text.
- Rollback authority: who may decide.
- Backup retention.
- Reviewer for the diff: `CONTRIBUTING.md` requires a human teammate other than the author. The AI work here has not had that review yet.

## Appendix A: instructions given to the GenAI tool

Simplification prompt, verbatim:

```text
Identify parts of this EventHub code that can be simplified so it is easier to add new functionality to and easier to review when errors are found, while still delivering the same required functionality. Prefer looser coupling between modules, refactoring complex code, and removing duplication.
```

Other instructions, summarised (not verbatim):

- Treat the Call 6 transcript as claims to check against the repository, and report what the code proves or disproves.
- Write the requirements, ADRs and model changes first; mark undecided values as open instead of inventing them.
- Split the implementation into streams with disjoint file ownership; each stream commits in its own worktree.
- Review the merged diff in two lenses (correctness and security; tests and document consistency).
- Never state that something passed unless it was run; say what was not run.

## Appendix B: evidence

| Item | Where |
|---|---|
| Design changes and Call 6 trace table | `docs/reports/part6-1-design-changes.md` |
| Per-suggestion simplification log (S-01 to S-10) | `docs/reports/part6-simplification-log.md` (merged separately) |
| Decisions | `docs/adr/ADR-008-money-formatting-and-minor-units.md`, `ADR-009-release-restore-backup-and-order-alert.md`, `ADR-010-localization.md` |
| Procedures | `docs/runbooks/backup-restore.md`, `docs/runbooks/release-and-rollback.md` |
| Requirements | `features/*/requirements.md` (entries tagged `[Call 6]`) |
| Review-fix commit | `00856ce` (rate-lock race, alert window, restore guard, wrong column, doc overclaims) |
| Integration commit | `499d70c` (JPY seed counts, ST-61, system-023 test, catalogue) |
| Full list | `git log --oneline v1.2.0..HEAD` (23 commits), `git diff v1.2.0..HEAD --stat` |
| CI evidence | `docs/evidence/part6/` (to be added after the Actions run) |
