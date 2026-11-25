<#
.SYNOPSIS
  Creates the kind cluster (1 control-plane + 2 workers) and deploys RiskPulse: build -> kind load -> apply -> rollout.
.PARAMETER Overlay        dev (1 replica, HPA 1..3, local images) or prod (2 replicas, HPA 2..6).
.PARAMETER NoBuild        Reuse the local images tagged ghcr.io/radahassan/riskpulse-*:dev.
.PARAMETER Security       Also apply NetworkPolicies, RBAC and the Kyverno policies (needs -InstallOperators once).
.PARAMETER Monitoring     Also install kube-prometheus-stack, ServiceMonitors, rules and the 10 dashboards.
.PARAMETER Recreate       Delete and recreate the cluster first.
#>
[CmdletBinding()]
param(
    [ValidateSet('dev', 'prod')][string]$Overlay = 'dev',
    [switch]$NoBuild,
    [switch]$Security,
    [switch]$Monitoring,
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$k8s = Join-Path $root 'infra/k8s'
$cluster = 'riskpulse'
$ns = 'riskpulse'
$ingressVersion = 'controller-v1.15.1'
$metricsServerVersion = 'v0.9.1'
$services = 'api-gateway', 'auth-service', 'customer-service', 'transaction-service', 'risk-service', 'notification-service', 'audit-service', 'ml-serving', 'frontend', 'mlflow', 'mlops-pipeline'

function Require($name) { if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "$name is required (see CLAUDE.md / winget install)." } }
function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function New-Secret([int]$bytes = 24) {
    $buf = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    return ([Convert]::ToBase64String($buf) -replace '[+/=]', 'x')
}
function Invoke-Kubectl { & kubectl @args; if ($LASTEXITCODE -ne 0) { throw "kubectl $($args -join ' ') failed" } }

Require docker; Require kind; Require kubectl
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is not running.' }

# 1. cluster -----------------------------------------------------------------------------------
$exists = (kind get clusters 2>$null) -contains $cluster
if ($exists -and $Recreate) { Step 'Deleting the existing cluster'; kind delete cluster --name $cluster; $exists = $false }
if (-not $exists) {
    Step 'Creating the kind cluster (1 control-plane + 2 workers)'
    kind create cluster --config (Join-Path $k8s 'kind/kind-config.yaml')
    if ($LASTEXITCODE -ne 0) { throw 'kind create cluster failed' }
}
Invoke-Kubectl config use-context "kind-$cluster" | Out-Null

# 2. cluster add-ons -----------------------------------------------------------------------------
if (-not (kubectl get ns ingress-nginx --ignore-not-found 2>$null)) {
    Step "Installing ingress-nginx $ingressVersion"
    Invoke-Kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/$ingressVersion/deploy/static/provider/kind/deploy.yaml"
}
if (-not (kubectl -n kube-system get deploy metrics-server --ignore-not-found 2>$null)) {
    Step "Installing metrics-server $metricsServerVersion (needed by the HPA)"
    Invoke-Kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/$metricsServerVersion/components.yaml"
    Invoke-Kubectl -n kube-system patch deployment metrics-server --type=json -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
}
Invoke-Kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=300s

# 3. images --------------------------------------------------------------------------------------
if ($Overlay -eq 'dev') {
    if (-not $NoBuild) {
        Step 'Building the Spring jars, then images (docker compose build)'
        Push-Location (Join-Path $root 'backend'); try { & ./mvnw -B -ntp -q -DskipTests package; if ($LASTEXITCODE -ne 0) { throw 'maven build failed' } } finally { Pop-Location }
        $envFile = Join-Path $root 'infra/docker/.env'
        $buildEnv = @{ COMPOSE_PARALLEL_LIMIT = '1' }
        foreach ($k in 'SERVICE_KEY', 'POSTGRES_PASSWORD', 'POSTGRES_AUTH_PASSWORD', 'POSTGRES_CUSTOMER_PASSWORD', 'POSTGRES_TRANSACTION_PASSWORD', 'POSTGRES_RISK_PASSWORD', 'POSTGRES_NOTIFICATION_PASSWORD', 'POSTGRES_AUDIT_PASSWORD', 'POSTGRES_MLFLOW_PASSWORD', 'POSTGRES_EXPORTER_PASSWORD', 'JWT_PRIVATE_KEY', 'JWT_PUBLIC_KEY', 'SEED_ADMIN_PASSWORD', 'SEED_ANALYST_PASSWORD', 'GRAFANA_ADMIN_PASSWORD') { $buildEnv[$k] = 'build-only' }
        foreach ($k in $buildEnv.Keys) { Set-Item -Path "env:$k" -Value $buildEnv[$k] }
        Push-Location (Join-Path $root 'infra/docker')
        try { docker compose build; if ($LASTEXITCODE -ne 0) { throw 'docker compose build failed' } } finally { Pop-Location }
    }
    Step 'Loading images into the kind nodes'
    foreach ($s in $services) {
        $image = "ghcr.io/radahassan/riskpulse-${s}:dev"
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) { throw "image $image not found: run without -NoBuild" }
        kind load docker-image $image --name $cluster
        if ($LASTEXITCODE -ne 0) { throw "kind load failed for $image" }
    }
}

# 4. namespace + secrets (random, never written to disk, never committed) ------------------------
Invoke-Kubectl apply -f (Join-Path $k8s 'base/namespace.yaml')
if (-not (kubectl -n $ns get secret riskpulse-secrets --ignore-not-found 2>$null)) {
    Step 'Generating random secrets (first deployment)'
    $keys = & java (Join-Path $PSScriptRoot 'GenKeys.java')
    if ($LASTEXITCODE -ne 0) { throw 'a JDK is required once to generate the JWT key pair' }
    $kv = @{}
    $keys | ForEach-Object { $a, $b = $_ -split '=', 2; $kv[$a] = $b }
    $admin = New-Secret 18
    $mlflowPw = New-Secret
    $args = @('-n', $ns, 'create', 'secret', 'generic', 'riskpulse-secrets',
        "--from-literal=SERVICE_KEY=$(New-Secret 32)",
        "--from-literal=JWT_PRIVATE_KEY=$($kv['JWT_PRIVATE_KEY'])", "--from-literal=JWT_PUBLIC_KEY=$($kv['JWT_PUBLIC_KEY'])",
        "--from-literal=SEED_ADMIN_PASSWORD=$admin", "--from-literal=SEED_ANALYST_PASSWORD=$(New-Secret 18)",
        "--from-literal=POSTGRES_PASSWORD=$(New-Secret)", "--from-literal=POSTGRES_EXPORTER_PASSWORD=$(New-Secret)",
        "--from-literal=POSTGRES_MLFLOW_PASSWORD=$mlflowPw",
        "--from-literal=MLFLOW_BACKEND_STORE_URI=postgresql://mlflow_user:$mlflowPw@postgres:5432/mlflow")
    foreach ($db in 'AUTH', 'CUSTOMER', 'TRANSACTION', 'RISK', 'NOTIFICATION', 'AUDIT') { $args += "--from-literal=POSTGRES_${db}_PASSWORD=$(New-Secret)" }
    & kubectl @args | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'secret creation failed' }
    Write-Host "  secret riskpulse-secrets created. Admin password: $admin  (also: kubectl -n $ns get secret riskpulse-secrets -o jsonpath='{.data.SEED_ADMIN_PASSWORD}')" -ForegroundColor Green
}

# 5. optional layers -----------------------------------------------------------------------------
if ($Security) {
    Step 'Applying cluster security (NetworkPolicies, RBAC, Kyverno policies)'
    & (Join-Path $PSScriptRoot 'k8s-security.ps1') -Overlay $Overlay
}

# 6. workloads -----------------------------------------------------------------------------------
Step "Applying overlay '$Overlay'"
Invoke-Kubectl apply -k (Join-Path $k8s "overlays/$Overlay")
foreach ($kind in 'statefulset/postgres', 'statefulset/mlflow') { Invoke-Kubectl -n $ns rollout status $kind --timeout=600s }
foreach ($d in 'auth-service', 'audit-service', 'notification-service', 'customer-service', 'transaction-service', 'risk-service', 'ml-serving', 'api-gateway', 'frontend') {
    Invoke-Kubectl -n $ns rollout status "deploy/$d" --timeout=600s
}

Step 'Running the MLflow pipeline job (register + deploy the champion model)'
Invoke-Kubectl -n $ns delete job mlops-pipeline --ignore-not-found
Invoke-Kubectl apply -k (Join-Path $k8s 'jobs')
Invoke-Kubectl -n $ns wait --for=condition=complete job/mlops-pipeline --timeout=600s

if ($Monitoring) {
    Step 'Installing the monitoring stack'
    & (Join-Path $PSScriptRoot 'k8s-monitoring.ps1')
}

Write-Host ''
Write-Host 'RiskPulse is running on Kubernetes:' -ForegroundColor Green
Write-Host '  UI + API   http://riskpulse.localtest.me:8088   (localtest.me resolves to 127.0.0.1)'
Write-Host "  Pods       kubectl -n $ns get pods -o wide"
Write-Host "  HPA        kubectl -n $ns get hpa"
Write-Host '  Roll back  scripts/k8s-rollback.ps1'
