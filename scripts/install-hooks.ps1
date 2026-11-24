<#
.SYNOPSIS
  Installs the local pre-commit hooks (gitleaks, hadolint, private-key detection, ruff, eslint).
.DESCRIPTION
  Installs `pre-commit` with pip if missing, then registers the git hooks and runs them once on all files.
  Re-run safely at any time.
#>
[CmdletBinding()]
param([switch]$SkipFirstRun)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command pre-commit -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing pre-commit with pip (user scope)...' -ForegroundColor Cyan
    python -m pip install --user --upgrade pre-commit
    $userScripts = python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"
    $env:Path = "$env:Path;$userScripts"
}

pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg
if ($LASTEXITCODE -ne 0) { throw 'pre-commit install failed' }

if (-not $SkipFirstRun) {
    Write-Host 'Running all hooks once (first run downloads the hook environments)...' -ForegroundColor Cyan
    pre-commit run --all-files
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Some hooks reported issues. Fix them before committing.' }
}
Write-Host 'Hooks installed. They run automatically on every `git commit`.' -ForegroundColor Green
