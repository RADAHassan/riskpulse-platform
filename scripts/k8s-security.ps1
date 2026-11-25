<#
.SYNOPSIS
  Applies the cluster security layer: NetworkPolicies (default deny + allow-list), least-privilege RBAC,
  Kyverno admission policies and (with -InstallOperators) Kyverno, Sealed Secrets and Trivy Operator.
.PARAMETER Overlay            dev  -> image-signature policy in Audit (local images are unsigned)
                              prod -> image-signature policy ENFORCED (images must be signed by the CI)
.PARAMETER InstallOperators   Install Kyverno, Sealed Secrets controller and Trivy Operator (once per cluster).
.PARAMETER Falco              Also install Falco (runtime detection; optional, off by default: ~300 MB RAM).
#>
[CmdletBinding()]
param(
    [ValidateSet('dev', 'prod')][string]$Overlay = 'dev',
    [switch]$InstallOperators,
    [switch]$Falco
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sec = Join-Path $root 'infra/k8s/security'
function Step($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Invoke-Checked { & $args[0] @($args | Select-Object -Skip 1); if ($LASTEXITCODE -ne 0) { throw "$($args -join ' ') failed" } }

if ($InstallOperators) {
    Step 'Kyverno (admission control, CEL policies)'
    helm repo add kyverno https://kyverno.github.io/kyverno/ --force-update | Out-Null
    helm upgrade --install kyverno kyverno/kyverno --version 3.10.0 -n kyverno --create-namespace `
        --set admissionController.replicas=1 --set backgroundController.replicas=1 --set cleanupController.replicas=1 `
        --set reportsController.replicas=1 --set admissionController.serviceMonitor.enabled=false --wait --timeout 8m
    if ($LASTEXITCODE -ne 0) { throw 'kyverno install failed' }

    Step 'Sealed Secrets controller v0.41.2'
    Invoke-Checked kubectl apply -f 'https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.41.2/controller.yaml'

    Step 'Trivy Operator (continuous vulnerability / config / RBAC scanning, Prometheus metrics)'
    helm repo add aqua https://aquasecurity.github.io/helm-charts/ --force-update | Out-Null
    helm upgrade --install trivy-operator aqua/trivy-operator --version 0.38.1 -n trivy-system --create-namespace `
        -f (Join-Path $sec 'trivy-operator/values.yaml') --wait --timeout 8m
    if ($LASTEXITCODE -ne 0) { throw 'trivy-operator install failed' }
}

if ($Falco) {
    Step 'Falco (optional runtime detection)'
    helm repo add falcosecurity https://falcosecurity.github.io/charts --force-update | Out-Null
    helm upgrade --install falco falcosecurity/falco --version 9.2.2 -n falco --create-namespace `
        -f (Join-Path $sec 'falco/values.yaml') --wait --timeout 8m
    if ($LASTEXITCODE -ne 0) { throw 'falco install failed' }
}

Step 'NetworkPolicies and RBAC'
Invoke-Checked kubectl apply -k $sec

if (kubectl get crd validatingpolicies.policies.kyverno.io --ignore-not-found 2>$null) {
    Step "Kyverno policies (overlay '$Overlay')"
    Invoke-Checked kubectl apply -k (Join-Path $sec "kyverno/overlays/$Overlay")
    kubectl get validatingpolicies, imagevalidatingpolicies
} else {
    Write-Warning 'Kyverno is not installed: re-run with -InstallOperators to apply the admission policies.'
}
