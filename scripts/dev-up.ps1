<#
.SYNOPSIS
  Starts the full RiskPulse stack locally with Docker Compose (random secrets, MLflow pipeline, health wait).
.DESCRIPTION
  1. generates infra/docker/.env with random secrets (only if it does not exist; the file is git-ignored)
  2. builds and starts every service (PostgreSQL, MLflow, ml-serving, 7 Spring services, frontend, Prometheus, Grafana, Alertmanager)
  3. waits until the gateway answers and the MLflow pipeline job has registered + deployed the champion model
.PARAMETER NoBuild
  Skip `docker compose build` (reuse local images).
#>
[CmdletBinding()]
param([switch]$NoBuild)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'infra/docker'
$envFile = Join-Path $compose '.env'

function New-Secret([int]$bytes = 24) {
    $buf = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    return ([Convert]::ToBase64String($buf) -replace '[+/=]', 'x')
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is required.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is not running: start Docker Desktop first.' }

if (-not (Test-Path $envFile)) {
    Write-Host 'Generating infra/docker/.env with random secrets...' -ForegroundColor Cyan
    if (-not (Get-Command java -ErrorAction SilentlyContinue)) { throw 'A JDK is required once to generate the JWT key pair (java scripts/GenKeys.java).' }
    $keys = & java (Join-Path $PSScriptRoot 'GenKeys.java')
    if ($LASTEXITCODE -ne 0) { throw 'Key generation failed.' }
    $adminPassword = New-Secret 18
    $lines = @(
        "POSTGRES_PASSWORD=$(New-Secret)",
        "POSTGRES_AUTH_PASSWORD=$(New-Secret)",
        "POSTGRES_CUSTOMER_PASSWORD=$(New-Secret)",
        "POSTGRES_TRANSACTION_PASSWORD=$(New-Secret)",
        "POSTGRES_RISK_PASSWORD=$(New-Secret)",
        "POSTGRES_NOTIFICATION_PASSWORD=$(New-Secret)",
        "POSTGRES_AUDIT_PASSWORD=$(New-Secret)",
        "POSTGRES_MLFLOW_PASSWORD=$(New-Secret)",
        "POSTGRES_EXPORTER_PASSWORD=$(New-Secret)",
        "SERVICE_KEY=$(New-Secret 32)",
        "JWT_KEY_ID=rp-local-$(Get-Date -Format yyyyMMdd)",
        "SEED_ADMIN_PASSWORD=$adminPassword",
        "SEED_ANALYST_PASSWORD=$(New-Secret 18)",
        "GRAFANA_ADMIN_PASSWORD=$(New-Secret 18)",
        "IMAGE_TAG=dev"
    ) + $keys
    # .env must be LF, no BOM
    [System.IO.File]::WriteAllText($envFile, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  .env created (git-ignored). Admin login: admin / $adminPassword" -ForegroundColor Green
}

Push-Location $compose
try {
    if (-not $NoBuild) {
        Write-Host 'Building the Spring jars (./mvnw -DskipTests package)...' -ForegroundColor Cyan
        Push-Location (Join-Path $root 'backend'); try { & ./mvnw -B -ntp -q -DskipTests package; if ($LASTEXITCODE -ne 0) { throw 'maven build failed' } } finally { Pop-Location }
        docker compose build; if ($LASTEXITCODE -ne 0) { throw 'docker compose build failed' } }
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

    Write-Host 'Waiting for the gateway...' -ForegroundColor Cyan
    $deadline = (Get-Date).AddMinutes(6)
    do {
        Start-Sleep -Seconds 5
        try { $ok = (Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8080/actuator/health/readiness' -TimeoutSec 3).StatusCode -eq 200 } catch { $ok = $false }
    } until ($ok -or (Get-Date) -gt $deadline)
    if (-not $ok) { docker compose ps; throw 'Gateway did not become ready in time (docker compose logs api-gateway).' }

    Write-Host 'Waiting for the MLflow pipeline job (train/import -> evaluate -> validate -> register -> deploy)...' -ForegroundColor Cyan
    $deadline = (Get-Date).AddMinutes(5)
    do {
        Start-Sleep -Seconds 5
        $state = docker inspect -f '{{.State.Status}}|{{.State.ExitCode}}' riskpulse-mlops-pipeline-1 2>$null
    } until ($state -like 'exited*' -or (Get-Date) -gt $deadline)
    if ($state -ne 'exited|0') { docker compose logs mlops-pipeline --tail 40; throw "Pipeline job state: $state" }

    Write-Host ''
    Write-Host 'RiskPulse is up:' -ForegroundColor Green
    Write-Host '  UI          http://localhost:5173   (admin / see infra/docker/.env -> SEED_ADMIN_PASSWORD)'
    Write-Host '  Gateway     http://localhost:8080   (OpenAPI: /openapi.yaml)'
    Write-Host '  MLflow      http://localhost:5000'
    Write-Host '  Grafana     http://localhost:3000   (admin / GRAFANA_ADMIN_PASSWORD)'
    Write-Host '  Prometheus  http://localhost:9090   Alertmanager http://localhost:9093'
    Write-Host '  End-to-end test: scripts/e2e.ps1'
} finally {
    Pop-Location
}
