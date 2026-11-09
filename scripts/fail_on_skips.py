#!/usr/bin/env python3
"""Fail (exit 1) if a JUnit XML file has any skipped test or no tests at all (system-018).

    python scripts/fail_on_skips.py reports/junit.xml [more.xml ...]

A green run that silently skipped the PostgreSQL layer is not a green run.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def check(path: str) -> list[str]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    problems = []
    if not cases:
        problems.append(f"{path}: zero tests ran")
    for case in cases:
        if case.find("skipped") is not None:
            problems.append(f"{path}: skipped {case.get('classname')}::{case.get('name')}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: fail_on_skips.py JUNIT_XML [...]", file=sys.stderr)
        return 2
    problems = [p for path in argv for p in check(path)]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
