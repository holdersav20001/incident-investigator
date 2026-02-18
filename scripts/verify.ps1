# verify.ps1 — end-to-end verification of the full stack
#
# Usage: .\scripts\verify.ps1
#        .\scripts\verify.ps1 -SkipIntegration   # unit tests only (no Docker)
#        .\scripts\verify.ps1 -SkipCompose        # assume DB already up
#
# Steps:
#   1. docker compose up -d db (unless -SkipCompose or -SkipIntegration)
#   2. alembic upgrade head    (unless -SkipIntegration)
#   3. pytest (unit tests, no Docker required)
#   4. pytest -m integration   (unless -SkipIntegration)
#
# Exit code matches the first failing step (0 = all green).

param(
    [switch]$SkipIntegration,  # skip steps 1-2 and step 4
    [switch]$SkipCompose       # skip docker compose up (assume DB already running)
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

function Step([string]$label) {
    Write-Host ""
    Write-Host "==> $label" -ForegroundColor Cyan
}

function Ok([string]$label) {
    Write-Host "    OK: $label" -ForegroundColor Green
}

function Fail([string]$label) {
    Write-Host ""
    Write-Host "FAILED: $label" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Step 1 — Start Postgres (optional)
# ---------------------------------------------------------------------------

if (-not $SkipIntegration -and -not $SkipCompose) {
    Step "Starting Postgres via docker compose..."
    docker compose --project-directory $Root up -d db
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up -d db" }

    Step "Waiting for Postgres to become healthy..."
    $retries = 15
    for ($i = 1; $i -le $retries; $i++) {
        $containerId = docker compose --project-directory $Root ps -q db 2>$null
        if ($containerId) {
            $health = docker inspect --format="{{.State.Health.Status}}" $containerId 2>$null
            if ($health -eq "healthy") {
                Ok "Postgres healthy"
                break
            }
        }
        if ($i -eq $retries) { Fail "Postgres did not become healthy in time" }
        Write-Host "    (attempt $i/$retries) waiting..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
}

# ---------------------------------------------------------------------------
# Step 2 — Alembic migrations (optional)
# ---------------------------------------------------------------------------

if (-not $SkipIntegration) {
    Step "Running Alembic migrations (upgrade head)..."
    Push-Location $Root
    try {
        $env:DATABASE_URL = "postgresql://incidents:incidents@localhost:5432/incidents"
        python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { Fail "alembic upgrade head" }
        Ok "Migrations applied"
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Step 3 — Unit tests (no Docker required)
# ---------------------------------------------------------------------------

Step "Running unit tests..."
Push-Location $Root
try {
    python -m pytest tests/ --ignore=tests/integration -q --tb=short
    if ($LASTEXITCODE -ne 0) { Fail "unit tests" }
    Ok "Unit tests passed"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# Step 4 — Integration tests (requires Docker)
# ---------------------------------------------------------------------------

if (-not $SkipIntegration) {
    Step "Running integration tests..."
    Push-Location $Root
    try {
        python -m pytest -m integration -q --tb=short
        if ($LASTEXITCODE -ne 0) { Fail "integration tests" }
        Ok "Integration tests passed"
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# All green
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  All checks passed." -ForegroundColor Green
if ($SkipIntegration) {
    Write-Host "  (Integration tests skipped — use without -SkipIntegration to run them)" -ForegroundColor Yellow
}
Write-Host "============================================" -ForegroundColor Green
