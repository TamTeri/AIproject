#!/usr/bin/env python3
"""Warn when feature code changes but its requirements file does not (Call 4).

Maps app/<feature>/... -> features/<feature>/requirements.md.

    python scripts/check_spec_alignment.py                 # staged changes (pre-commit)
    python scripts/check_spec_alignment.py --base origin/main   # branch diff (CI)
    python scripts/check_spec_alignment.py --strict ...     # fail instead of warn

A warning is not always wrong (a pure refactor changes no requirement), so the
default is to warn loudly and let the reviewer decide.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

# app package -> features/<name>/requirements.md
FEATURE_MAP = {
    "identity": "identity",
    "catalog": "catalog",
    "pricing": "pricing",
    "inventory": "inventory",
    "purchase": "purchase",
    "orders": "orders",
    "audit": "audit",
    "admin": "admin",
    "web": "system",
    "config": "system",
    "db": "system",
}


def changed_files(base: str | None) -> list[str]:
    if base:
        command = ["git", "diff", "--name-only", f"{base}...HEAD"]
    else:
        command = ["git", "diff", "--name-only", "--cached"]
    output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


def missing_spec_updates(files: list[str]) -> dict[str, list[str]]:
    touched_specs = {f for f in files if f.startswith("features/") and f.endswith("requirements.md")}
    missing: dict[str, list[str]] = {}
    for name in files:
        parts = PurePosixPath(name).parts
        if len(parts) < 3 or parts[0] != "app" or not name.endswith(".py"):
            continue
        feature = FEATURE_MAP.get(parts[1])
        if feature is None:
            continue
        spec = f"features/{feature}/requirements.md"
        if spec not in touched_specs:
            missing.setdefault(spec, []).append(name)
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="compare HEAD with this ref instead of the staged changes")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a spec update is missing")
    args = parser.parse_args(argv)

    missing = missing_spec_updates(changed_files(args.base))
    if not missing:
        print("spec alignment: OK")
        return 0
    print("spec alignment WARNING: code changed but its requirements file did not:")
    for spec, files in sorted(missing.items()):
        print(f"  {spec}")
        for name in files:
            print(f"      <- {name}")
    print("If behaviour changed, update the requirements file. If not (pure refactor), say so in review.")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
