# Contributing to EventHub

These rules come from Call 4 (Implementation). They apply to everyone, including Marcus.

## Workflow
1. Make small changes on a branch, never directly on `main`.
2. Open a pull request. **Someone else reviews it** before it merges.
3. **AI-generated code gets the same review, twice as carefully.** If a tool wrote it, a human reads every line before it goes in. In the PR description, say which parts were AI-generated.
4. CI must be green. **If the automatic run fails, the change does not go in.** No exceptions.

## Definition of done (all four boxes)
- [ ] Code reviewed by someone other than the author
- [ ] Tests written and passing, each naming the requirement it proves (Call 5), including `python scripts/run_system_tests.py` when a page or the purchase path changed
- [ ] The feature's `features/<name>/requirements.md` updated (or the PR explains why no requirement changed)
- [ ] Every automatic check passes (lint, style, spec alignment, tests)

## Setup
```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pre-commit install        # runs checks before every commit
```

## Checks that run before each commit
| Check | Catches |
|---|---|
| `ruff check` | obvious errors: unused imports, undefined names, likely bugs |
| `ruff format` | formatting / style |
| `scripts/check_spec_alignment.py` | **warns** when `app/<feature>/` changes but `features/<feature>/requirements.md` does not |
| unit + contract tests | broken behaviour, without needing a database |

CI (`.github/workflows/ci.yml`) runs the same checks plus the PostgreSQL tests and the requirement-coverage check on every push and pull request. `.github/workflows/system-tests.yml` runs the Selenium system tests on every push and pull request, and from the **Run workflow** button.

## System tests (Part 5 / Call 5)
- Run them all: `python scripts/run_system_tests.py`, or double-click `run-system-tests.cmd` on Windows.
- Every system test needs `@pytest.mark.requirement("<id>")` with a real id from `features/`. The run stops otherwise.
- Write the expected result from the requirement, not from what the code does today (Priya, Call 5).
- After adding or renaming a system test, run `python scripts/list_system_tests.py --write` (a test checks the catalogue is current).

## Where code goes
- Feature rules belong in `app/<feature>/service.py`. Plain Python only, no Flask and no SQL.
- SQL belongs in `app/<feature>/postgres.py`.
- Wiring belongs only in `app/wiring.py`.
- Pages: routes go in `app/web/__init__.py` and templates in `templates/`.
- **Nobody computes money in a template or a route.** All prices come from `app/pricing/calculator.py`. See ADR-005.
- Every purchase goes through `PurchaseCoordinator`, including quick buy, so validation and audit cannot be skipped.

## Temporary decisions
Mark any value the customer has not confirmed as `[TEMPORARY_MVP_DEFAULT]`, put it in one named constant, and list it in `docs/IMPLEMENTATION_STATUS.md`. Do not make up numbers silently.
