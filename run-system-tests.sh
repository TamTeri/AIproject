#!/usr/bin/env sh
# Run every EventHub system test (Selenium + Chrome). Needs Docker and Chrome.
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" scripts/run_system_tests.py "$@"
