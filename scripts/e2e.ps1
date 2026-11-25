<#
.SYNOPSIS
  End-to-end test through the API gateway: login -> simulator -> decisions -> human review -> audit -> metrics.
  PowerShell twin of scripts/e2e.sh (same steps, used locally on Windows).
.PARAMETER Gateway / Prometheus / Mlflow
  Base URLs (defaults: localhost stack from scripts/dev-up.ps1).
#>
[CmdletBinding()]
param(
    [string]$Gateway = 'http://localhost:8080',
    [string]$Prometheus = 'http://localhost:9090',
    [string]$Mlflow = 'http://localhost:5000',
    [switch]$SkipPrometheus,
    [switch]$SkipMlflow
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$demoCsv = Join-Path $root 'ml/artifacts/demo_transactions.csv'
$envFile = Join-Path $root 'infra/docker/.env'
$secrets = @{}
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^(SEED_ADMIN_PASSWORD|SEED_ANALYST_PASSWORD)=' } | ForEach-Object { $k, $v = $_ -split '=', 2; $secrets[$k] = $v }
}
$adminPassword = if ($env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD } else { $secrets['SEED_ADMIN_PASSWORD'] }
$analystPassword = if ($env:ANALYST_PASSWORD) { $env:ANALYST_PASSWORD } else { $secrets['SEED_ANALYST_PASSWORD'] }
if (-not $adminPassword -or -not $analystPassword) { throw 'ADMIN_PASSWORD / ANALYST_PASSWORD are required (or infra/docker/.env).' }

$script:pass = 0; $script:fail = 0
function Check([string]$description, [bool]$condition) {
    if ($condition) { $script:pass++; Write-Host "  PASS $description" -ForegroundColor Green }
    else { $script:fail++; Write-Host "  FAIL $description" -ForegroundColor Red }
}

function Call([string]$Method, [string]$Path, [string]$Token = '', $Body = $null) {
    $headers = @{}
    if ($Token) { $headers['Authorization'] = "Bearer $Token" }
    $args = @{ Uri = "$Gateway$Path"; Method = $Method; Headers = $headers; UseBasicParsing = $true; ContentType = 'application/json' }
    if ($null -ne $Body) { $args['Body'] = ($Body | ConvertTo-Json -Depth 6 -Compress) }
    try {
        $resp = Invoke-WebRequest @args
        $status = [int]$resp.StatusCode; $text = $resp.Content
    } catch {
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            try { $reader = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream()); $text = $reader.ReadToEnd() } catch { $text = '' }
        } else { $status = 0; $text = $_.Exception.Message }
    }
    $json = $null
    if ($text) { try { $json = $text | ConvertFrom-Json } catch { $json = $null } }
    return [pscustomobject]@{ Status = $status; Body = $json; Raw = $text }
}

function Get-DemoRow([int]$fraud, [int]$n) {
    $count = 0
    foreach ($line in (Get-Content $demoCsv | Select-Object -Skip 1)) {
        $cols = $line -split ','
        if ([int]$cols[-1] -eq $fraud) {
            $count++
            if ($count -eq $n) {
                return @{ amount = [double]::Parse($cols[0], [Globalization.CultureInfo]::InvariantCulture); features = @($cols[1..28] | ForEach-Object { [double]::Parse($_, [Globalization.CultureInfo]::InvariantCulture) }) }
            }
        }
    }
}

Write-Host '== 1. platform is up'
Check 'gateway readiness is UP' ((Call GET '/actuator/health/readiness').Status -eq 200)
Check 'OpenAPI document is public' ((Call GET '/openapi.yaml').Status -eq 200)

Write-Host '== 2. authentication'
Check 'wrong password -> 401' ((Call POST '/api/auth/login' '' @{ username = 'admin'; password = 'definitely-wrong-password' }).Status -eq 401)
$r = Call POST '/api/auth/login' '' @{ username = 'admin'; password = $adminPassword }
Check 'admin login -> 200' ($r.Status -eq 200); $admin = $r.Body.accessToken
$r = Call POST '/api/auth/login' '' @{ username = 'analyst'; password = $analystPassword }
Check 'analyst login -> 200' ($r.Status -eq 200); $analyst = $r.Body.accessToken
Check 'anonymous request -> 401' ((Call GET '/api/customers').Status -eq 401)
Check 'internal API is not exposed -> 404' ((Call GET '/internal/audit/events' $admin).Status -eq 404)

Write-Host '== 3. customers and ownership (BOLA)'
$suffix = "$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())$(Get-Random -Maximum 9999)"
function New-Customer([string]$name) { (Call POST '/api/customers' $admin @{ firstName = 'E2E'; lastName = $name; email = "e2e-$name-$suffix@example.com"; country = 'FR'; segment = 'STANDARD' }).Body.id }
$c1 = New-Customer 'one'; $c2 = New-Customer 'two'
Check 'customers created' ($c1 -and $c2)
$pw = "E2e-Passw0rd-$suffix"
Check 'customer user 1 created' ((Call POST '/api/auth/users' $admin @{ username = "cust1-$suffix"; password = $pw; role = 'CUSTOMER'; customerId = $c1 }).Status -eq 201)
Check 'customer user 2 created' ((Call POST '/api/auth/users' $admin @{ username = "cust2-$suffix"; password = $pw; role = 'CUSTOMER'; customerId = $c2 }).Status -eq 201)
$t1 = (Call POST '/api/auth/login' '' @{ username = "cust1-$suffix"; password = $pw }).Body.accessToken
$t2 = (Call POST '/api/auth/login' '' @{ username = "cust2-$suffix"; password = $pw }).Body.accessToken
Check 'customer reads own record' ((Call GET "/api/customers/$c1" $t1).Status -eq 200)
Check 'customer cannot read another customer (403)' ((Call GET "/api/customers/$c2" $t1).Status -eq 403)
Check 'customer cannot list customers (403)' ((Call GET '/api/customers' $t1).Status -eq 403)
Check 'customer cannot read the audit trail (403)' ((Call GET '/api/audit/events' $t1).Status -eq 403)
Check 'customer cannot reach ml endpoints (403)' ((Call GET '/api/ml/model/info' $t1).Status -eq 403)

Write-Host '== 4. decisions'
$legit = Get-DemoRow 0 3
$tx = Call POST '/api/transactions' $t1 @{ customerId = $c1; amount = $legit.amount; features = $legit.features; merchant = 'e2e legit' }
Check 'legit transaction accepted (201)' ($tx.Status -eq 201)
Check 'legit transaction is APPROVED' ($tx.Body.decision -eq 'APPROVE')
$legitTx = $tx.Body.id
Check 'customer 2 cannot read customer 1 transaction (403)' ((Call GET "/api/transactions/$legitTx" $t2).Status -eq 403)
Check 'customer 1 reads own transaction' ((Call GET "/api/transactions/$legitTx" $t1).Status -eq 200)
Check 'customer cannot submit for another customer (403)' ((Call POST '/api/transactions' $t2 @{ customerId = $c1; amount = $legit.amount; features = $legit.features }).Status -eq 403)
$flagged = 0
foreach ($n in 1..6) {
    $f = Get-DemoRow 1 $n
    $res = Call POST '/api/transactions' $t1 @{ customerId = $c1; amount = $f.amount; features = $f.features; merchant = 'e2e fraud-like' }
    if ($res.Body.decision -ne 'APPROVE') { $flagged++ }
}
Check "fraud-like transactions are not all approved ($flagged/6 flagged)" ($flagged -ge 1)

Write-Host '== 5. simulator'
Check 'customer cannot use the simulator (403)' ((Call POST '/api/transactions/simulate' $t1 @{ count = 10 }).Status -eq 403)
$sim = Call POST '/api/transactions/simulate' $admin @{ count = 100; fraudRatio = 0.6 }
Check 'admin simulator runs' ($sim.Status -eq 200)
Check '100 simulated transactions processed' ($sim.Body.processed -eq 100)
Check "decisions add up ($($sim.Body.approved)/$($sim.Body.humanReview)/$($sim.Body.declined))" (($sim.Body.approved + $sim.Body.humanReview + $sim.Body.declined) -eq 100)

Write-Host '== 6. human review'
$q = Call GET '/api/reviews?status=OPEN&size=5' $analyst
Check 'analyst reads the review queue' ($q.Status -eq 200)
Check "review queue is not empty ($($q.Body.totalElements) open)" ($q.Body.totalElements -ge 1)
$review = $q.Body.content[0]
Check 'review exposes uncertainty and model version' ($null -ne $review.uncertainty -or $null -ne $review.reason)
Check 'customer cannot resolve a review (403)' ((Call POST "/api/reviews/$($review.id)/resolve" $t1 @{ resolution = 'APPROVE' }).Status -eq 403)
$res = Call POST "/api/reviews/$($review.id)/resolve" $analyst @{ resolution = 'APPROVE'; note = 'e2e: verified with the customer' }
Check 'analyst resolves the review' ($res.Status -eq 200 -and $res.Body.status -eq 'APPROVED')
Check 'second resolution -> 409' ((Call POST "/api/reviews/$($review.id)/resolve" $analyst @{ resolution = 'REJECT' }).Status -eq 409)
Start-Sleep -Seconds 1
Check 'transaction reflects the human decision' ((Call GET "/api/transactions/$($review.transactionId)" $admin).Body.status -eq 'APPROVED')

Write-Host '== 7. audit trail and notifications'
$a = Call GET '/api/audit/events?action=RISK_DECISION&size=5' $analyst
Check 'audit holds RISK_DECISION events with the model version' ($a.Status -eq 200 -and $a.Body.content[0].modelVersion)
Check 'review resolution is audited' ((Call GET "/api/audit/events?action=REVIEW_RESOLVED&resourceId=$($review.transactionId)" $analyst).Body.totalElements -ge 1)
Check 'audit hash chain is intact' ((Call GET '/api/audit/events/verify' $admin).Body.valid -eq $true)
Check 'notifications exist for review/decline' ((Call GET '/api/notifications' $analyst).Body.totalElements -ge 1)

Write-Host '== 8. model serving'
$m = Call GET '/api/ml/model/info' $analyst
Check 'model info reachable by analyst' ($m.Status -eq 200)
Write-Host "     model: $($m.Body.model_version) registry v$($m.Body.registry_version) via $($m.Body.model_source)"
$p = (Call POST '/api/ml/predict' $admin @{}).Status
Check '/predict is not exposed through the gateway' ($p -eq 404 -or $p -eq 403)
Check 'projections endpoint' ((Call GET '/api/ml/projections' $analyst).Body.points.Count -gt 0)

if (-not $SkipMlflow) {
    Write-Host '== 9. MLflow registry'
    try { $code = (Invoke-WebRequest -UseBasicParsing "$Mlflow/api/2.0/mlflow/registered-models/alias?name=riskpulse-fraud&alias=champion").StatusCode } catch { $code = 0 }
    Check 'model riskpulse-fraud has a champion alias' ($code -eq 200)
}

if (-not $SkipPrometheus) {
    Write-Host '== 10. Prometheus metrics'
    function Query([string]$expr) {
        try { $v = (Invoke-RestMethod -Uri "$Prometheus/api/v1/query?query=$([uri]::EscapeDataString($expr))").data.result } catch { return 0 }
        if ($v.Count -eq 0) { return 0 } else { return [double]$v[0].value[1] }
    }
    foreach ($i in 1..12) { if ((Query 'sum(riskpulse_transactions_total)') -gt 0 -and (Query 'sum(riskpulse_ml_predictions_total)') -gt 0) { break }; Start-Sleep -Seconds 5 }
    Check 'riskpulse_transactions_total > 0' ((Query 'sum(riskpulse_transactions_total)') -gt 0)
    Check 'riskpulse_ml_predictions_total > 0' ((Query 'sum(riskpulse_ml_predictions_total)') -gt 0)
    Check 'riskpulse_review_queue_size is exported' ((Invoke-RestMethod -Uri "$Prometheus/api/v1/query?query=riskpulse_review_queue_size").data.result.Count -ge 1)
    Check 'all scrape targets are up' ((Query 'count(up{job=~"riskpulse-.*"} == 0) or vector(0)') -eq 0)
}

Write-Host ''
Write-Host "e2e: $script:pass passed, $script:fail failed"
if ($script:fail -gt 0) { exit 1 }
