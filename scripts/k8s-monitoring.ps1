<#
.SYNOPSIS
  Installs kube-prometheus-stack (Prometheus, Alertmanager, Grafana, kube-state-metrics, node-exporter) and the
  RiskPulse add-ons: ServiceMonitors, PrometheusRule (alerts), 10 Grafana dashboards, postgres-exporter, alert sink.
#>
[CmdletBinding()]
param([string]$ChartVersion = '93.10.0')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$mon = Join-Path $root 'infra/monitoring'
function Step($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function New-Secret([int]$bytes = 18) {
    $buf = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    return ([Convert]::ToBase64String($buf) -replace '[+/=]', 'x')
}
if (-not (Get-Command helm -ErrorAction SilentlyContinue)) { throw 'helm is required.' }

Step 'Namespace monitoring (node-exporter needs host access: this namespace is the only PSA exception)'
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - | Out-Null
kubectl label namespace monitoring pod-security.kubernetes.io/enforce=privileged pod-security.kubernetes.io/warn=baseline --overwrite | Out-Null

if (-not (kubectl -n monitoring get secret grafana-admin --ignore-not-found 2>$null)) {
    $pw = New-Secret
    kubectl -n monitoring create secret generic grafana-admin --from-literal=admin-user=admin "--from-literal=admin-password=$pw" | Out-Null
    Write-Host "  Grafana admin password: $pw" -ForegroundColor Green
}
if (-not (kubectl -n monitoring get secret alertmanager-webhook --ignore-not-found 2>$null)) {
    # default receiver = the in-cluster alert sink; replace the URLs (Slack/Teams/e-mail relay) with your own, never commit them
    kubectl -n monitoring create secret generic alertmanager-webhook `
        --from-literal=warning-url=http://alert-sink.monitoring.svc:9000/warning `
        --from-literal=critical-url=http://alert-sink.monitoring.svc:9000/critical | Out-Null
}

Step 'Rendering the PrometheusRule from the plain rules'
python (Join-Path $PSScriptRoot 'render_prometheus_rule.py')

Step "helm upgrade --install kube-prometheus-stack $ChartVersion"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update | Out-Null
helm repo update | Out-Null
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack --version $ChartVersion `
    --namespace monitoring -f (Join-Path $mon 'helm/kube-prometheus-stack-values.yaml') --wait --timeout 10m
if ($LASTEXITCODE -ne 0) { throw 'helm install failed' }

Step 'Loading the alert sink image and applying RiskPulse monitoring resources'
$sink = 'ghcr.io/radahassan/riskpulse-alert-sink:dev'
docker image inspect $sink *> $null
if ($LASTEXITCODE -eq 0) { kind load docker-image $sink --name riskpulse | Out-Null }
kubectl apply -k (Join-Path $mon 'exporters')
kubectl apply -k $mon
if ($LASTEXITCODE -ne 0) { throw 'kubectl apply -k infra/monitoring failed' }

Write-Host ''
Write-Host 'Monitoring is installed:' -ForegroundColor Green
Write-Host '  Grafana       kubectl -n monitoring port-forward svc/grafana 3000:80        -> http://localhost:3000'
Write-Host '  Prometheus    kubectl -n monitoring port-forward svc/kps-prometheus 9090    -> http://localhost:9090'
Write-Host '  Alertmanager  kubectl -n monitoring port-forward svc/kps-alertmanager 9093  -> http://localhost:9093'
