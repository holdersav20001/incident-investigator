# dev_up.ps1 — start the local development stack
# Usage: .\scripts\dev_up.ps1
#
# Starts Postgres via docker compose and applies Alembic migrations.
# Requires Docker Desktop to be running.

param(
    [switch]$MigrateOnly   # skip compose if DB is already up
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

Write-Host "==> Starting development stack..." -ForegroundColor Cyan

if (-not $MigrateOnly) {
    docker compose --project-directory $Root up -d db
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "==> Waiting for Postgres to be healthy..." -ForegroundColor Cyan
    $retries = 10
    for ($i = 1; $i -le $retries; $i++) {
        $health = docker inspect --format="{{.State.Health.Status}}" "$(docker compose --project-directory $Root ps -q db)" 2>$null
        if ($health -eq "healthy") { break }
        Write-Host "    (attempt $i/$retries) not ready yet..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

Write-Host "==> Running Alembic migrations..." -ForegroundColor Cyan
Push-Location $Root
try {
    $env:DATABASE_URL = "postgresql://incidents:incidents@localhost:5432/incidents"
    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "==> Dev stack ready." -ForegroundColor Green
Write-Host "    API:      http://localhost:8000  (run: python main.py)" -ForegroundColor Green
Write-Host "    Postgres: localhost:5432 / incidents" -ForegroundColor Green
