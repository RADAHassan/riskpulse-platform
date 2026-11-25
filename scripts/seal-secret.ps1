<#
.SYNOPSIS
  Encrypts the application secrets into a SealedSecret that is safe to commit (only the cluster's Sealed Secrets
  controller can decrypt it). Secrets are generated randomly: there is no default value anywhere.
.EXAMPLE
  scripts/seal-secret.ps1 -Output infra/k8s/overlays/prod/sealed-riskpulse-secrets.yaml
.NOTES
  Needs the controller (scripts/k8s-security.ps1 -InstallOperators) and the `kubeseal` CLI
  (winget install Bitnami.kubeseal or https://github.com/bitnami-labs/sealed-secrets/releases).
  The ciphertext is bound to the namespace/name: re-seal after recreating the cluster (its key pair changes).
#>
[CmdletBinding()]
param(
    [string]$Output = 'infra/k8s/overlays/prod/sealed-riskpulse-secrets.yaml',
    [string]$Namespace = 'riskpulse',
    [string]$ControllerNamespace = 'kube-system'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command kubeseal -ErrorAction SilentlyContinue)) { throw 'kubeseal is required (see the notes of this script).' }
function New-Secret([int]$bytes = 24) {
    $buf = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    return ([Convert]::ToBase64String($buf) -replace '[+/=]', 'x')
}

$keys = & java (Join-Path $PSScriptRoot 'GenKeys.java')
if ($LASTEXITCODE -ne 0) { throw 'a JDK is required to generate the JWT key pair' }
$kv = @{}; $keys | ForEach-Object { $a, $b = $_ -split '=', 2; $kv[$a] = $b }
$mlflowPw = New-Secret
$values = [ordered]@{
    SERVICE_KEY = New-Secret 32; JWT_PRIVATE_KEY = $kv['JWT_PRIVATE_KEY']; JWT_PUBLIC_KEY = $kv['JWT_PUBLIC_KEY']
    SEED_ADMIN_PASSWORD = New-Secret 18; SEED_ANALYST_PASSWORD = New-Secret 18
    POSTGRES_PASSWORD = New-Secret; POSTGRES_EXPORTER_PASSWORD = New-Secret; POSTGRES_MLFLOW_PASSWORD = $mlflowPw
    MLFLOW_BACKEND_STORE_URI = "postgresql://mlflow_user:$mlflowPw@postgres:5432/mlflow"
}
foreach ($db in 'AUTH', 'CUSTOMER', 'TRANSACTION', 'RISK', 'NOTIFICATION', 'AUDIT') { $values["POSTGRES_${db}_PASSWORD"] = New-Secret }

# plain Secret manifest lives only in memory / a temp file that is deleted right away
$tmp = New-TemporaryFile
try {
    $lines = @('apiVersion: v1', 'kind: Secret', 'metadata:', '  name: riskpulse-secrets', "  namespace: $Namespace", 'type: Opaque', 'stringData:')
    foreach ($k in $values.Keys) { $lines += "  ${k}: '$($values[$k])'" }
    [System.IO.File]::WriteAllText($tmp.FullName, ($lines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
    $dest = Join-Path $root $Output
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    kubeseal --controller-namespace $ControllerNamespace --controller-name sealed-secrets-controller --format yaml < $tmp.FullName | Set-Content -Encoding utf8 $dest
    if ($LASTEXITCODE -ne 0) { throw 'kubeseal failed' }
} finally {
    Remove-Item -Force $tmp.FullName
}
Write-Host "SealedSecret written to $Output (safe to commit). Admin password (shown once): $($values['SEED_ADMIN_PASSWORD'])" -ForegroundColor Green
