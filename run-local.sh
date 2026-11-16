#!/usr/bin/env bash
# Boot EventHub locally on macOS or Linux: database (Docker), dependencies, schema, demo data, admin, web server.
#   ./run-local.sh              start everything (resets the LOCAL test database each time)
#   ./run-local.sh --no-reset   keep the data from the last run
#   ./run-local.sh --stop       stop the database container
#   ./run-local.sh --language es   run the Spanish version (EVENTHUB_LANGUAGE=es; also: en)
# Local-only test values below (the same ones the README uses); never use them anywhere real.
set -euo pipefail
cd "$(dirname "$0")"

fail() { printf '\n%s\n' "$1" >&2; exit 1; }

NO_RESET=0
LANGUAGE_SETTING=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-reset) NO_RESET=1 ;;
    --stop) STOP=1 ;;
    --language)
      [ $# -ge 2 ] || fail "usage: ./run-local.sh --language en|es"
      LANGUAGE_SETTING="$2"; shift ;;
    *) fail "usage: ./run-local.sh [--no-reset] [--language en|es] | --stop" ;;
  esac
  shift
done
case "$LANGUAGE_SETTING" in
  "" | en | es) ;;
  *) fail "--language must be en or es (EventHub refuses to start with any other value)" ;;
esac

# 1. Docker (the database runs in a container: docker-compose.test.yml, PostgreSQL on localhost:55432)
command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Install it, start it, then run this again:
  macOS:  brew install --cask docker     (then open Docker.app once)
  Linux:  https://docs.docker.com/engine/install/  (and add yourself to the 'docker' group)"
docker info >/dev/null 2>&1 || fail "Docker is installed but not running (or you lack permission). Start Docker Desktop / the docker service, wait until it is ready, then run this again."

if [ "${STOP:-0}" = "1" ]; then docker compose -f docker-compose.test.yml down; exit 0; fi

# 2. Python 3.12+ and a virtual environment in .venv
if [ ! -x .venv/bin/python ]; then
  PY=""
  for c in python3.14 python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  [ -n "$PY" ] || fail "Python 3.12 or newer is required and none was found. Install it (macOS: brew install python@3.12) and run this again."
  echo "Creating .venv with $PY ..."
  "$PY" -m venv .venv || fail "Could not create the virtual environment (on Debian/Ubuntu: sudo apt install python3-venv)."
fi
echo "Installing dependencies ..."
.venv/bin/python -m pip install -q -e ".[test]" || fail "pip install failed."

# 3. Database
echo "Starting PostgreSQL in Docker ..."
docker compose -f docker-compose.test.yml up -d --wait || fail "The database container did not become healthy."

export DATABASE_URL="postgresql+psycopg://eventhub:eventhub@localhost:55432/eventhub_test"
export EVENTHUB_ENVIRONMENT=development
export EVENTHUB_RESET_ENABLED=true
export EVENTHUB_ADMIN_EMAIL=admin@eventhub.test
export EVENTHUB_ADMIN_PASSWORD=change-me-123

if [ "$NO_RESET" = "0" ]; then
  echo "Resetting and seeding the local database (6 demo events, 5 currencies incl. JPY) ..."
  .venv/bin/python -m app.db.commands reset
  .venv/bin/python -m app.db.commands seed
  .venv/bin/python -m app.db.commands create-admin
fi

# 4. Web server (Ctrl+C to stop it; ./run-local.sh --stop stops the database)
URL="http://127.0.0.1:5000"
if [ -n "$LANGUAGE_SETTING" ]; then
  export EVENTHUB_LANGUAGE="$LANGUAGE_SETTING"   # Part 7 (system-024): the deployment language
fi
cat <<EOF

EventHub is starting at $URL
  Language:  ${EVENTHUB_LANGUAGE:-not configured (follows the browser)}; a visitor can still switch with ?lang=en or ?lang=es
  Health:    $URL/healthz
  Admin:     $URL/login   ->  admin@eventhub.test / change-me-123   (rates: $URL/admin/rates)
  Register your own buyer account on the site; pick JPY as the currency to see yen.
Press Ctrl+C to stop.

EOF
( sleep 4; { command -v open >/dev/null 2>&1 && open "$URL"; } || { command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL"; } || true ) >/dev/null 2>&1 &
exec .venv/bin/python -m flask --app "app:create_app()" run
