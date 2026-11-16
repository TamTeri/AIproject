"""Part 7 (configuration management): requirements can be traced to the code that implements them.

scripts/trace_requirement.py reads the requirement ids that code, templates and tests
name. These tests check the reader, and that every Part 7 requirement is named by the
application code that implements it, so the next change to the language configuration
can start from `python scripts/trace_requirement.py system-024`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tracer():
    name = "trace_requirement"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@pytest.mark.requirement("system-015")
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("system-020/024: ?lang= > cookie", {"system-020", "system-024"}),
        ("(system-020..022, and system-024..025)", {f"system-02{n}" for n in (0, 1, 2, 4, 5)}),
        ("system-016, pricing-014", {"system-016", "pricing-014"}),
        ("purchase-017 (Call 5)", {"purchase-017"}),
        ("released 2026-11-016", set()),  # a date is not a requirement
    ],
)
def test_short_forms_are_expanded(line, expected):
    assert _tracer().ids_in(line) == expected


@pytest.mark.requirement("system-024", "system-025", "system-026", "system-027")
@pytest.mark.parametrize("requirement", ["system-024", "system-025", "system-026", "system-027"])
def test_every_part7_requirement_is_named_by_the_code_that_implements_it(requirement):
    tracer = _tracer()
    assert tracer.requirement_text(requirement)
    found = tracer.trace(requirement)
    implementing = [e for e in found["code"] if e.startswith(("app/", "templates/"))]
    assert implementing, f"no file in app/ or templates/ names {requirement}"
    assert found["tests"], f"no test names {requirement}"
