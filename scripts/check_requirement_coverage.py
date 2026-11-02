#!/usr/bin/env python3
"""Which requirements have a test that names them? (Call 5, Thuy and Priya)

Thuy's bar is "every requirement has a test that would actually fail if the
behaviour broke", not a coverage percentage. A script cannot judge "would
fail", but it can find requirements that no test even mentions.

    python scripts/check_requirement_coverage.py            # summary + gaps
    python scripts/check_requirement_coverage.py --table    # every requirement
    python scripts/check_requirement_coverage.py --strict   # exit 1 on an unexplained gap

A requirement counts as covered when its id (for example ``purchase-014``)
appears in a test file: in a @pytest.mark.requirement(...) marker, a docstring
or a comment. Requirements that wait on a customer decision ("When the approved
... is defined", ``[OPEN]``) are listed separately: there is nothing to test yet.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT = re.compile(r"^- \*\*([a-z]+-\d{3})\*\* \(([^)]*)\)(.*)$")
WAITING = re.compile(r"\[OPEN\]|When the approved|is approved|are approved|are defined", re.IGNORECASE)


def requirements() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted((ROOT / "features").glob("*/requirements.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = REQUIREMENT.match(line.strip())
            if match:
                found[match.group(1)] = match.group(3).strip()
    return found


def references(ids: set[str]) -> dict[str, dict[str, set[str]]]:
    """id -> {"system": files, "other": files}"""
    refs: dict[str, dict[str, set[str]]] = {i: {"system": set(), "other": set()} for i in ids}
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(ids))) + r")\b")
    for path in sorted((ROOT / "tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        layer = "system" if "tests/system/" in path.as_posix() else "other"
        for found in set(pattern.findall(text)):
            refs[found][layer].add(path.relative_to(ROOT).as_posix())
    return refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", action="store_true", help="print every requirement")
    parser.add_argument("--strict", action="store_true", help="exit 1 if a testable requirement has no test")
    args = parser.parse_args(argv)

    reqs = requirements()
    refs = references(set(reqs))
    covered_ids = {i for i in reqs if refs[i]["system"] or refs[i]["other"]}
    waiting = sorted(i for i, text in reqs.items() if WAITING.search(text) and i not in covered_ids)
    covered = sorted(i for i in reqs if refs[i]["system"] or refs[i]["other"])
    in_system = sorted(i for i in reqs if refs[i]["system"])
    gaps = sorted(i for i in reqs if i not in covered and i not in waiting)

    if args.table:
        print(f"{'requirement':<16} {'system tests':>12} {'other tests':>12}")
        for i in reqs:
            note = "  (waiting on a decision)" if i in waiting else ""
            print(f"{i:<16} {len(refs[i]['system']):>12} {len(refs[i]['other']):>12}{note}")
        print()

    print(f"requirements: {len(reqs)}")
    print(f"named by at least one test: {len(covered)}")
    print(f"named by a Selenium system test: {len(in_system)}")
    print(f"waiting on a customer decision (nothing to test yet): {', '.join(waiting) or 'none'}")
    if gaps:
        print("NO TEST NAMES THESE REQUIREMENTS:")
        for i in gaps:
            print(f"  {i}: {reqs[i][:100]}")
    else:
        print("every testable requirement is named by at least one test")
    return 1 if (args.strict and gaps) else 0


if __name__ == "__main__":
    sys.exit(main())
