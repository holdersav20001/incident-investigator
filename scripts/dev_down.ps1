# dev_down.ps1 — stop the local development stack
# Usage: .\scripts\dev_down.ps1
#        .\scripts\dev_down.ps1 -Volumes   # also delete the Postgres data volume

param(
    [switch]$Volumes   # pass to also remove named volumes (destroys data)
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

Write-Host "==> Stopping development stack..." -ForegroundColor Cyan

if ($Volumes) {
    docker compose --project-directory $Root down --volumes
} else {
    docker compose --project-directory $Root down
}

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "==> Dev stack stopped." -ForegroundColor Green
