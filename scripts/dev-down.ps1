<#
.SYNOPSIS
  Stops the local RiskPulse stack. Use -Purge to also delete the data volumes (PostgreSQL, MLflow, Prometheus, Grafana).
#>
[CmdletBinding()]
param([switch]$Purge)

$ErrorActionPreference = 'Stop'
$compose = Join-Path (Split-Path -Parent $PSScriptRoot) 'infra/docker'
Push-Location $compose
try {
    if ($Purge) { docker compose down --volumes --remove-orphans } else { docker compose down --remove-orphans }
} finally {
    Pop-Location
}
