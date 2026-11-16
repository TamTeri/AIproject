#!/usr/bin/env python3
"""Trace a requirement to the code, tests and documents that mention it (Part 7, configuration management).

    python scripts/trace_requirement.py system-026
    python scripts/trace_requirement.py system-024 system-025 --code-only

The code in this repository names the requirement it implements in docstrings and comments
("system-020/024: ?lang= > cookie > ..."), and every test names what it proves with
@pytest.mark.requirement(...). This script reads those mentions, including the short forms
"system-020/024" and "system-020..023", so that before changing a configurable feature you
can see every place that implements it and every test that will tell you if you broke it.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AREAS = {
    "code": ("app", "templates", "scripts"),
    "tests": ("tests",),
    "docs": ("features", "docs"),
}
SUFFIXES = {".py", ".html", ".md", ".js", ".json", ".yml", ".yaml", ".dsl"}
SKIP = {"__pycache__", "evidence", "node_modules", ".venv"}
MENTION = re.compile(r"\b([a-z]+)-(\d{3})((?:\s*(?:/|\.\.|,\s*|–|-)\s*\d{3})*)")
TEST_DEF = re.compile(r"^\s*def (test_\w+)")


def ids_in(line: str) -> set[str]:
    """'system-020/024' -> {system-020, system-024}; 'system-020..023' -> 020, 021, 022, 023."""
    found: set[str] = set()
    for prefix, first, rest in MENTION.findall(line):
        numbers = [int(first)]
        for sep, number in re.findall(r"(/|\.\.|,|–|-)\s*(\d{3})", rest):
            if sep in {"..", "–"} and int(number) > numbers[-1] and int(number) - numbers[-1] < 50:
                numbers += range(numbers[-1] + 1, int(number) + 1)
            else:
                numbers.append(int(number))
        found.update(f"{prefix}-{n:03d}" for n in numbers)
    return found


def requirement_text(requirement: str) -> str | None:
    pattern = re.compile(rf"^- \*\*{re.escape(requirement)}\*\* \(([^)]*)\)(.*)$")
    for path in sorted((ROOT / "features").glob("*/requirements.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line.strip())
            if match:
                return f"{path.relative_to(ROOT).as_posix()}: ({match.group(1)}){match.group(2)}"
    return None


def _files(folders: tuple[str, ...]):
    for folder in folders:
        base = ROOT / folder
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in SUFFIXES and not SKIP & set(path.relative_to(ROOT).parts):
                yield path


def trace(requirement: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for area, folders in AREAS.items():
        for path in _files(folders):
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            rel = path.relative_to(ROOT).as_posix()
            for index, line in enumerate(lines):
                if requirement not in ids_in(line):
                    continue
                where = f"{rel}:{index + 1}"
                if area == "tests":
                    test = next(
                        (m.group(1) for m in map(TEST_DEF.match, lines[index : index + 12]) if m), None
                    )
                    found[area].append(f"{where}  {test or line.strip()[:100]}")
                elif area == "docs" and path.name == "requirements.md":
                    continue  # the definition itself is printed separately
                else:
                    found[area].append(f"{where}  {line.strip()[:110]}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("requirements", nargs="+", help="ids such as system-026")
    parser.add_argument("--code-only", action="store_true", help="only app/, templates/ and scripts/")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    status = 0
    for requirement in args.requirements:
        text = requirement_text(requirement)
        print(f"=== {requirement}")
        if text is None:
            print("  not found in features/*/requirements.md")
            status = 1
            continue
        print(f"  {text[:300]}")
        found = trace(requirement)
        for area in ("code", "tests", "docs"):
            if args.code_only and area != "code":
                continue
            print(f"  -- {area} ({len(found[area])})")
            for entry in found[area]:
                print(f"     {entry}")
        print()
    return status


if __name__ == "__main__":
    sys.exit(main())
