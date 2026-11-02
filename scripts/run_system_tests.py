#!/usr/bin/env python3
"""Run every EventHub system test at the press of a button (Part 5 / Call 5).

    python scripts/run_system_tests.py               # everything, headless Chrome
    python scripts/run_system_tests.py --headed      # watch the browser
    python scripts/run_system_tests.py --browser edge
    python scripts/run_system_tests.py -k st11       # one test (any pytest -k expression)
    python scripts/run_system_tests.py --no-perf     # skip the load test

Windows users can also double-click run-system-tests.cmd in the project folder.

What it does:
1. Uses EVENTHUB_TEST_DATABASE_URL, or starts the throwaway PostgreSQL from
   docker-compose.test.yml (localhost:55432) and uses that. THE DATABASE IS RESET.
2. Runs pytest on tests/system: the tests start EventHub themselves, drive a real
   browser with Selenium, and check the results.
3. Writes reports/system-tests.html (open it in any browser), reports/system-tests.xml
   (JUnit, for CI) and a screenshot for every failure in reports/screenshots/.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DOCKER_URL = "postgresql+psycopg://eventhub:eventhub@localhost:55432/eventhub_test"


def ensure_database(use_docker: bool) -> str:
    url = os.environ.get("EVENTHUB_TEST_DATABASE_URL")
    if url:
        return url
    if not use_docker:
        sys.exit("Set EVENTHUB_TEST_DATABASE_URL, or drop --no-docker to start the test database.")
    if shutil.which("docker") is None:
        sys.exit("Docker was not found. Install Docker, or set EVENTHUB_TEST_DATABASE_URL.")
    print("Starting the test PostgreSQL (docker compose)...", flush=True)
    subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.test.yml"), "up", "-d", "--wait"],
        check=True,
        cwd=ROOT,
    )
    return DOCKER_URL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--browser", choices=["chrome", "edge", "firefox"], default=None)
    parser.add_argument("--no-docker", action="store_true", help="never start Docker")
    parser.add_argument("--no-perf", action="store_true", help="skip the performance test")
    parser.add_argument("--open", action="store_true", help="open the HTML report when done")
    parser.add_argument("-k", dest="keyword", help="only tests matching this pytest -k expression")
    args, extra = parser.parse_known_args(argv)

    env = dict(os.environ)
    env["EVENTHUB_TEST_DATABASE_URL"] = ensure_database(not args.no_docker)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if args.headed:
        env["EVENTHUB_HEADED"] = "1"
    if args.browser:
        env["EVENTHUB_BROWSER"] = args.browser

    REPORTS.mkdir(exist_ok=True)
    marker = "system and not performance" if args.no_perf else "system"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/system",
        "-m",
        marker,
        "-v",
        f"--html={REPORTS / 'system-tests.html'}",
        "--self-contained-html",
        f"--junitxml={REPORTS / 'system-tests.xml'}",
    ]
    if args.keyword:
        command += ["-k", args.keyword]
    command += extra
    print("Running:", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, env=env)

    report = REPORTS / "system-tests.html"
    print(f"\nReport: {report}")
    if args.open and report.exists():
        webbrowser.open(report.as_uri())
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
