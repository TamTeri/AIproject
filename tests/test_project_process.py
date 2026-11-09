"""The team's process requirements, checked like any other requirement.

system-009/010/011 (Call 4) and system-014/015 (Call 5) are about how the
project is built and tested. These tests fail if someone deletes a CI step, the
contributing guide's definition of done, a pre-commit check or the system test
button, which is how a rule "quietly falls out of date" (Priya, Call 5).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import create_app

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_ci_runs_lint_style_and_all_tests_on_every_upload():
    """system-009"""
    ci = read(".github/workflows/ci.yml")
    assert "push:" in ci and "pull_request:" in ci
    for step in ("ruff check", "ruff format --check", "python -m pytest"):
        assert step in ci, step


def test_contributing_guide_and_pre_commit_checks_exist():
    """system-010: contributing guide, pre-commit hooks, spec-alignment warning."""
    assert "Definition of done" in read("CONTRIBUTING.md")
    hooks = read(".pre-commit-config.yaml")
    for hook in ("ruff-lint", "ruff-format", "spec-alignment", "unit-tests"):
        assert f"id: {hook}" in hooks, hook


def test_definition_of_done_has_all_four_boxes():
    """system-011"""
    guide = read("CONTRIBUTING.md")
    boxes = re.findall(r"^- \[ \] (.+)$", guide, flags=re.MULTILINE)
    assert len(boxes) >= 4
    for words in ("reviewed", "Tests written", "requirements.md", "automatic check"):
        assert any(words in box for box in boxes), words


def test_system_tests_run_on_every_change_and_at_the_press_of_a_button():
    """system-014: Selenium suite, one command, every code change, a report."""
    workflow = read(".github/workflows/system-tests.yml")
    for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
        assert trigger in workflow, trigger
    assert "scripts/run_system_tests.py" in workflow
    runner = read("scripts/run_system_tests.py")
    assert "--html=" in runner and "--junitxml=" in runner
    assert (ROOT / "run-system-tests.cmd").exists() and (ROOT / "run-system-tests.sh").exists()
    journey = read("tests/system/test_st_buyer_journey.py")
    for step in ("register", "login", "search", "start_checkout", "EUR", "Order confirmed", "order_rows"):
        assert step in journey, step


def test_every_system_test_names_a_real_requirement():
    """system-015: the same check the system-test conftest runs before every run."""
    from tests.system.support import known_requirement_ids

    known = known_requirement_ids(ROOT / "features")
    named = set()
    for path in (ROOT / "tests" / "system").glob("test_*.py"):
        for marker in re.findall(r"@pytest\.mark\.requirement\(([^)]*)\)", path.read_text(encoding="utf-8")):
            named.update(re.findall(r'"([a-z]+-\d{3})"', marker))
    assert named and named <= known, named - known


def test_version_one_has_no_native_app_or_seat_map():
    """system-007: no native-app endpoints and no interactive seat-map selection."""
    app = create_app(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:1/never",
            "EVENTHUB_ENVIRONMENT": "test",
            "SECRET_KEY": "x",
        }
    )
    rules = [rule.rule.lower() for rule in app.url_map.iter_rules()]
    assert not [r for r in rules if "seat" in r or r.startswith("/api/mobile") or "/app/" in r], rules


def test_the_system_test_catalogue_matches_the_tests():
    """system-015: docs/testing/system-test-catalogue.md is regenerated whenever a system test changes."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "list_system_tests", ROOT / "scripts" / "list_system_tests.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = read("docs/testing/system-test-catalogue.md").replace("\r\n", "\n")
    assert committed == module.render(), "run: python scripts/list_system_tests.py --write"


@pytest.mark.requirement("system-018")
def test_ci_fails_on_skipped_tests_and_checks_the_migration_round_trip():
    """system-018: a green run that silently skipped a layer is not green."""
    ci = read(".github/workflows/ci.yml")
    for step in ("--junitxml", "scripts/fail_on_skips.py", "alembic downgrade -1", "alembic upgrade head"):
        assert step in ci, step
    assert "fail_on_skips.py" in read(".github/workflows/system-tests.yml")


@pytest.mark.requirement("system-018")
def test_fail_on_skips_script(tmp_path):
    """system-018"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("fail_on_skips", ROOT / "scripts" / "fail_on_skips.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def junit(body: str) -> str:
        path = tmp_path / f"{abs(hash(body))}.xml"
        path.write_text(f'<testsuites><testsuite name="s">{body}</testsuite></testsuites>')
        return str(path)

    assert module.main([junit('<testcase classname="a" name="ok"/>')]) == 0
    assert module.main([junit('<testcase classname="a" name="s"><skipped/></testcase>')]) == 1
    assert module.main([junit("")]) == 1
    assert module.main([]) == 2


@pytest.mark.requirement("audit-009")
def test_order_watch_workflow_only_runs_with_the_secret_and_holds_no_secret():
    """audit-009: scheduled check, skipped cleanly without the repository secret."""
    workflow = read(".github/workflows/order-watch.yml")
    assert "schedule:" in workflow and "check-orders" in workflow
    assert "secrets.EVENTHUB_DATABASE_URL" in workflow and "postgresql://" not in workflow


@pytest.mark.requirement("system-019")
def test_backup_and_restore_scripts_refuse_without_database_url_and_never_print_it():
    """system-019"""
    for name in ("backup.sh", "restore.sh"):
        script = read(f"scripts/{name}")
        assert "EVENTHUB_DATABASE_URL:?" in script, name
        assert 'echo "$EVENTHUB_DATABASE_URL' not in script and "set -x" not in script, name
    assert "pg_dump" in read("scripts/backup.sh") and "--format=custom" in read("scripts/backup.sh")
    assert "backups/" in read(".gitignore")
    for runbook in ("release-and-rollback.md", "backup-restore.md"):
        assert "[OPEN]" in read(f"docs/runbooks/{runbook}")
