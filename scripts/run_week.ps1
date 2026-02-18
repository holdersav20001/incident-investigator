param(
  [Parameter(Mandatory=$true)]
  [ValidateRange(1, 8)]
  [int]$Week,
  [string]$RepoRoot = (Get-Location).Path
)

$weekStr = "{0:D2}" -f $Week
$promptPath = Join-Path $RepoRoot ("ai\handoff\project2\WEEK{0}_PROMPT.md" -f $weekStr)
$planPath   = Join-Path $RepoRoot ("ai\handoff\project2\WEEK{0}_PLAN.md" -f $weekStr)

if (!(Test-Path $promptPath)) {
  Write-Error "Prompt not found: $promptPath"
  exit 1
}
if (!(Test-Path $planPath)) {
  Write-Warning "Plan not found: $planPath"
}

Write-Host "Opening Week $Week artifacts in VS Code..." -ForegroundColor Cyan
code -r $promptPath $planPath

Write-Host "`nRunning checks..." -ForegroundColor Cyan

Push-Location $RepoRoot
try {
  if (Test-Path (Join-Path $RepoRoot "Makefile")) {
    # Prefer Makefile targets if present
    if ((make -n test 2>$null) -ne $null) {
      make test
    } else {
      python -m pytest -q
    }
  } else {
    python -m pytest -q
  }

  # Optional: run eval harness if present
  $evalRunner = Join-Path $RepoRoot "eval\runner.py"
  if (Test-Path $evalRunner) {
    Write-Host "`nRunning eval harness..." -ForegroundColor Cyan
    python $evalRunner
  }

  Write-Host "`n✅ Checks completed." -ForegroundColor Green
}
finally {
  Pop-Location
}
