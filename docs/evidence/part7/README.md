# Part 7 evidence

Machine: Windows 11, Python 3.12.10, PostgreSQL 16 in Docker (`docker-compose.test.yml`), headless Chrome. Both runs used a database, so no PostgreSQL test was skipped.

| File | What it shows |
|---|---|
| `pytest-before.log` | Release 1.3.0 (`2a39d28`, tag `v1.3.0`) before any Part 7 change: unit, contract, process and PostgreSQL tests |
| `system-before.log` | Release 1.3.0: all Selenium system tests |
| `pytest-after.log` | Release 1.4.0 (`eventhub/part7`): the same suites plus the Part 7 tests |
| `system-after.log`, `system-tests-after.html`, `system-tests-after.xml` | Release 1.4.0: all Selenium system tests, including ST-71 to ST-76 (HTML report with requirement columns) |
| `restore-drill-v1.3.0.log` | `v1.3.0` checked out in a separate worktree runs its own unit and contract suite (system-018) |
| `screenshots/en-*.png`, `screenshots/es-*.png` | The same four pages from a server started with `EVENTHUB_LANGUAGE=en` and one started with `es`. The browser asks for English in both. `*-healthz.json` is each server's `/healthz`. |
| `trace/` | How the code to change was found: graph queries, grep inventories, the untranslated-text scanner before and after, the mutation check, and the requirement trace. See [Deliverable 2](../../reports/part7-2-genai-tracing-report.md). |
