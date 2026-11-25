<#
.SYNOPSIS
  Rolls a deployment back to its previous ReplicaSet (kubectl rollout undo) and waits until it is healthy.
.EXAMPLE
  scripts/k8s-rollback.ps1 -Deployment risk-service
  scripts/k8s-rollback.ps1 -All
  scripts/k8s-rollback.ps1 -Deployment risk-service -ToRevision 3
#>
[CmdletBinding()]
param(
    [string]$Deployment,
    [switch]$All,
    [int]$ToRevision = 0,
    [string]$Namespace = 'riskpulse'
)

$ErrorActionPreference = 'Stop'
if (-not $Deployment -and -not $All) { throw 'Specify -Deployment <name> or -All.' }
$targets = if ($All) { (kubectl -n $Namespace get deploy -o jsonpath='{.items[*].metadata.name}') -split ' ' } else { @($Deployment) }

foreach ($d in $targets) {
    Write-Host "==> $d : history" -ForegroundColor Cyan
    kubectl -n $Namespace rollout history "deploy/$d" | Select-Object -Last 4
    if ($ToRevision -gt 0) { kubectl -n $Namespace rollout undo "deploy/$d" "--to-revision=$ToRevision" } else { kubectl -n $Namespace rollout undo "deploy/$d" }
    if ($LASTEXITCODE -ne 0) { throw "rollout undo failed for $d" }
    kubectl -n $Namespace rollout status "deploy/$d" --timeout=300s
    if ($LASTEXITCODE -ne 0) { throw "$d did not become healthy after the rollback" }
    $image = kubectl -n $Namespace get "deploy/$d" -o jsonpath='{.spec.template.spec.containers[0].image}'
    Write-Host "    $d now runs $image" -ForegroundColor Green
}
