# Submission maps

**Team:** Ian Koratsky, Minh Tam Nguyen

## Part 6: Maintenance

| # | Deliverable | Weight | Where |
|---|---|---|---|
| 1 | Design changes from Discussion #6 and why | 20% | part6-1-design-changes.md (written) |
| 2 | Report on the GenAI maintenance process: what changed because of discussion #6, what changed for maintainability, and why | 60% | part6-2-genai-maintenance-process-report.md (written) |
| 3 | Simplification log: what the GenAI tool found that could be simplified, and what we did | supports 2 | part6-simplification-log.md (written) |
| 4 | Updated code with proof it still passes its system tests | 20% | merged; unit run saved in docs/evidence/part6/; Postgres and Selenium runs pending the GitHub Actions run (see process report, proof checklist) |

## Part 5: Integration and system testing

| # | Deliverable | Weight | Where |
|---|---|---|---|
| 1 | Design changes from Discussion #5 and why | 20% | [part5-1-design-changes.md](part5-1-design-changes.md) |
| 2 | Report on the GenAI test-creation process: did the first tests run, why not, what we changed | 60% | [part5-2-genai-testing-process-report.md](part5-2-genai-testing-process-report.md) |
| 3 | The test cases run against the final application | 15% | `python scripts/run_system_tests.py` or double-click `run-system-tests.cmd` (87 Selenium runs). Final run: [`../evidence/system-tests/`](../evidence/system-tests/) |
| 4 | The system test cases | 5% | [`../testing/system-test-cases.md`](../testing/system-test-cases.md) (how they were made, black-box and white-box lists), [`../testing/system-test-catalogue.md`](../testing/system-test-catalogue.md) (every case), code in [`../../tests/system/`](../../tests/system/) |

## Part 4: Implementation

| # | Deliverable | Weight | Where |
|---|---|---|---|
| 1 | Design changes from Discussion #4 and why | 20% | [part4-1-design-changes.md](part4-1-design-changes.md) |
| 2 | Report on the GenAI code-creation process | 60% | [part4-2-genai-process-report.md](part4-2-genai-process-report.md) |
| 3 | The final application runs all unit tests | 15% | `python -m pytest` (see the root README; 216 tests at the end of Part 4) |
| 4 | Source code and unit tests | 5% | `app/` (one package per feature), `tests/` (one test folder per feature) |
