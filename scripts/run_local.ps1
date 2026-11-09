# Boot EventHub locally on Windows: database (Docker), dependencies, schema, demo data, admin, web server.
#   run-local.cmd                 start everything (resets the LOCAL test database each time)
#   run-local.cmd -NoReset        keep the data from the last run
#   run-local.cmd -Stop           stop the database container
# Local-only test values below (the same ones the README uses); never use them anywhere real.
param([switch]$NoReset, [switch]$Stop)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Fail($msg) { Write-Host "`n$msg" -ForegroundColor Red; exit 1 }

# 1. Docker (the database runs in a container: docker-compose.test.yml, PostgreSQL on localhost:55432)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Fail @"
Docker is not installed. Install Docker Desktop, start it, then run this script again:
    winget install -e --id Docker.DockerDesktop
(it needs administrator rights and usually a restart)
"@
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker is installed but not running. Start Docker Desktop, wait until it says 'running', then run this again." }

if ($Stop) { docker compose -f docker-compose.test.yml down; exit 0 }

# 2. Python 3.12+ and a virtual environment in .venv
$py = $null
foreach ($v in "3.14", "3.13", "3.12") {
  & py "-$v" --version *> $null
  if ($LASTEXITCODE -eq 0) { $py = "-$v"; break }
}
$venvPy = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  if (-not $py) { Fail "Python 3.12 or newer is required (the 'py' launcher found none). Install it from python.org and run this again." }
  Write-Host "Creating .venv ..." -ForegroundColor Cyan
  & py $py -m venv .venv
  if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
}
Write-Host "Installing dependencies ..." -ForegroundColor Cyan
& $venvPy -m pip install -q -e ".[test]"
if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }

# 3. Database
Write-Host "Starting PostgreSQL in Docker ..." -ForegroundColor Cyan
docker compose -f docker-compose.test.yml up -d --wait
if ($LASTEXITCODE -ne 0) { Fail "The database container did not become healthy." }

$env:DATABASE_URL = "postgresql+psycopg://eventhub:eventhub@localhost:55432/eventhub_test"
$env:EVENTHUB_ENVIRONMENT = "development"
$env:EVENTHUB_RESET_ENABLED = "true"
$env:EVENTHUB_ADMIN_EMAIL = "admin@eventhub.test"
$env:EVENTHUB_ADMIN_PASSWORD = "change-me-123"

if (-not $NoReset) {
  Write-Host "Resetting and seeding the local database (6 demo events, 5 currencies incl. JPY) ..." -ForegroundColor Cyan
  & $venvPy -m app.db.commands reset;        if ($LASTEXITCODE -ne 0) { Fail "reset failed." }
  & $venvPy -m app.db.commands seed;         if ($LASTEXITCODE -ne 0) { Fail "seed failed." }
  & $venvPy -m app.db.commands create-admin; if ($LASTEXITCODE -ne 0) { Fail "create-admin failed." }
}

# 4. Web server (Ctrl+C to stop it; run-local.cmd -Stop stops the database)
$url = "http://127.0.0.1:5000"
Write-Host @"

EventHub is starting at $url
  Spanish:   $url/?lang=es
  Health:    $url/healthz
  Admin:     $url/login   ->  admin@eventhub.test / change-me-123   (rates: $url/admin/rates)
  Register your own buyer account on the site; pick JPY as the currency to see yen.
Press Ctrl+C to stop.

"@ -ForegroundColor Green
Start-Job { Start-Sleep 4; Start-Process $using:url } | Out-Null
& $venvPy -m flask --app "app:create_app()" run
