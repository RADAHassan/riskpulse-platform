#!/usr/bin/env bash
# End-to-end test through the API gateway: login -> simulator -> decisions -> human review -> audit -> metrics.
# Used locally (Docker Compose), in CI (kind) and after every rollout.
#
# Env: GATEWAY (default http://localhost:8080)  ADMIN_USER/ADMIN_PASSWORD  ANALYST_USER/ANALYST_PASSWORD
#      PROMETHEUS (default http://localhost:9090, set E2E_SKIP_PROM=1 to skip)  MLFLOW (default http://localhost:5000, E2E_SKIP_MLFLOW=1)
#      DEMO_CSV (default ml/artifacts/demo_transactions.csv)
set -euo pipefail

GATEWAY="${GATEWAY:-http://localhost:8080}"
PROMETHEUS="${PROMETHEUS:-http://localhost:9090}"
MLFLOW="${MLFLOW:-http://localhost:5000}"
ADMIN_USER="${ADMIN_USER:-admin}"
ANALYST_USER="${ANALYST_USER:-analyst}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_CSV="${DEMO_CSV:-$ROOT/ml/artifacts/demo_transactions.csv}"

if [[ -f "$ROOT/infra/docker/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source <(grep -E '^(SEED_ADMIN_PASSWORD|SEED_ANALYST_PASSWORD)=' "$ROOT/infra/docker/.env" | tr -d '\r'); set +a
fi
ADMIN_PASSWORD="${ADMIN_PASSWORD:-${SEED_ADMIN_PASSWORD:-}}"
ANALYST_PASSWORD="${ANALYST_PASSWORD:-${SEED_ANALYST_PASSWORD:-}}"
[[ -n "$ADMIN_PASSWORD" && -n "$ANALYST_PASSWORD" ]] || { echo "ADMIN_PASSWORD / ANALYST_PASSWORD are required"; exit 2; }

command -v jq >/dev/null || { echo "jq is required"; exit 2; }
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
check() { # check "<description>" <command...>
  local d="$1"; shift
  if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi
}

BODY=""; STATUS=""
call() { # call METHOD PATH [TOKEN] [JSON]
  local method="$1" path="$2" token="${3:-}" data="${4:-}"
  local args=(-sS -o /tmp/e2e.body -w '%{http_code}' -X "$method" "$GATEWAY$path" -H 'Content-Type: application/json')
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$data" ]] && args+=(--data "$data")
  STATUS="$(curl "${args[@]}" || true)"; BODY="$(cat /tmp/e2e.body 2>/dev/null || true)"
}
status_is() { [[ "$STATUS" == "$1" ]]; }
jq_eq() { [[ "$(jq -r "$1" <<<"$BODY")" == "$2" ]]; }

row_json() { # row_json <fraud 0|1> <n>  -> {"amount":..,"features":[..]} of the n-th matching row
  awk -F, -v want="$1" -v n="$2" 'NR>1 && $NF==want { c++; if (c==n) { printf "{\"amount\":%s,\"features\":[", $1; for (i=2;i<=29;i++) printf "%s%s", $i, (i<29?",":""); print "]}"; exit } }' "$DEMO_CSV"
}

echo "== 1. platform is up"
call GET /actuator/health/readiness; check "gateway readiness is UP" status_is 200
call GET /openapi.yaml; check "OpenAPI document is public" status_is 200

echo "== 2. authentication"
call POST /api/auth/login "" '{"username":"'"$ADMIN_USER"'","password":"definitely-wrong-password"}'; check "wrong password -> 401" status_is 401
call POST /api/auth/login "" '{"username":"'"$ADMIN_USER"'","password":"'"$ADMIN_PASSWORD"'"}'; check "admin login -> 200" status_is 200
ADMIN="$(jq -r .accessToken <<<"$BODY")"
call POST /api/auth/login "" '{"username":"'"$ANALYST_USER"'","password":"'"$ANALYST_PASSWORD"'"}'; check "analyst login -> 200" status_is 200
ANALYST="$(jq -r .accessToken <<<"$BODY")"
call GET /api/customers; check "anonymous request -> 401 (problem+json)" status_is 401
call GET /internal/audit/events "$ADMIN"; check "internal API is not exposed -> 404" status_is 404

echo "== 3. customers and ownership (BOLA)"
SUFFIX="$(date +%s)$RANDOM"
mk_customer() { call POST /api/customers "$ADMIN" '{"firstName":"E2E","lastName":"'"$1"'","email":"e2e-'"$1-$SUFFIX"'@example.com","country":"FR","segment":"STANDARD"}'; jq -r .id <<<"$BODY"; }
C1="$(mk_customer one)"; C2="$(mk_customer two)"
check "customers created" test -n "$C1" -a "$C1" != null -a -n "$C2" -a "$C2" != null
mk_user() { call POST /api/auth/users "$ADMIN" '{"username":"'"$1-$SUFFIX"'","password":"E2e-Passw0rd-'"$SUFFIX"'","role":"CUSTOMER","customerId":"'"$2"'"}'; }
mk_user cust1 "$C1"; check "customer user 1 created" status_is 201
mk_user cust2 "$C2"; check "customer user 2 created" status_is 201
call POST /api/auth/login "" '{"username":"cust1-'"$SUFFIX"'","password":"E2e-Passw0rd-'"$SUFFIX"'"}'; T1="$(jq -r .accessToken <<<"$BODY")"
call POST /api/auth/login "" '{"username":"cust2-'"$SUFFIX"'","password":"E2e-Passw0rd-'"$SUFFIX"'"}'; T2="$(jq -r .accessToken <<<"$BODY")"
call GET "/api/customers/$C1" "$T1"; check "customer reads own record" status_is 200
call GET "/api/customers/$C2" "$T1"; check "customer cannot read another customer (403)" status_is 403
call GET /api/customers "$T1"; check "customer cannot list customers (403)" status_is 403
call GET /api/audit/events "$T1"; check "customer cannot read the audit trail (403)" status_is 403
call GET /api/ml/model/info "$T1"; check "customer cannot reach ml endpoints (403)" status_is 403

echo "== 4. decisions"
LEGIT="$(row_json 0 3)"; FRAUD1="$(row_json 1 1)"
call POST /api/transactions "$T1" "$(jq -c --arg c "$C1" '. + {customerId:$c, merchant:"e2e legit"}' <<<"$LEGIT")"
check "legit transaction accepted (201)" status_is 201
check "legit transaction is APPROVED" jq_eq .decision APPROVE
LEGIT_TX="$(jq -r .id <<<"$BODY")"
call GET "/api/transactions/$LEGIT_TX" "$T2"; check "customer 2 cannot read customer 1 transaction (403)" status_is 403
call GET "/api/transactions/$LEGIT_TX" "$T1"; check "customer 1 reads own transaction" status_is 200
call POST /api/transactions "$T2" "$(jq -c --arg c "$C1" '. + {customerId:$c}' <<<"$LEGIT")"; check "customer cannot submit for another customer (403)" status_is 403
NOT_APPROVED=0
for n in 1 2 3 4 5 6; do
  call POST /api/transactions "$T1" "$(jq -c --arg c "$C1" '. + {customerId:$c, merchant:"e2e fraud-like"}' <<<"$(row_json 1 $n)")"
  [[ "$(jq -r .decision <<<"$BODY")" != "APPROVE" ]] && NOT_APPROVED=$((NOT_APPROVED+1))
done
check "fraud-like transactions are not all approved ($NOT_APPROVED/6 flagged)" test "$NOT_APPROVED" -ge 1

echo "== 5. simulator"
call POST /api/transactions/simulate "$T1" '{"count":10}'; check "customer cannot use the simulator (403)" status_is 403
call POST /api/transactions/simulate "$ADMIN" '{"count":100,"fraudRatio":0.6}'; check "admin simulator runs" status_is 200
check "100 simulated transactions processed" jq_eq .processed 100
SUM="$(jq '.approved + .humanReview + .declined' <<<"$BODY")"
check "decisions add up ($SUM)" test "$SUM" = 100
echo "     simulator: $(jq -c . <<<"$BODY")"

echo "== 6. human review"
call GET "/api/reviews?status=OPEN&size=5" "$ANALYST"; check "analyst reads the review queue" status_is 200
OPEN="$(jq -r .totalElements <<<"$BODY")"
check "review queue is not empty ($OPEN open)" test "$OPEN" -ge 1
REVIEW="$(jq -r '.content[0].id' <<<"$BODY")"; REVIEW_TX="$(jq -r '.content[0].transactionId' <<<"$BODY")"
check "review exposes probability, uncertainty and model version" jq -e '.content[0] | (.probability != null or .reason != null) and .modelVersion != null' <<<"$BODY"
call POST "/api/reviews/$REVIEW/resolve" "$T1" '{"resolution":"APPROVE"}'; check "customer cannot resolve a review (403)" status_is 403
call POST "/api/reviews/$REVIEW/resolve" "$ANALYST" '{"resolution":"APPROVE","note":"e2e: verified with the customer"}'; check "analyst resolves the review" status_is 200
check "review is APPROVED" jq_eq .status APPROVED
call POST "/api/reviews/$REVIEW/resolve" "$ANALYST" '{"resolution":"REJECT"}'; check "second resolution -> 409" status_is 409
sleep 1
call GET "/api/transactions/$REVIEW_TX" "$ADMIN"; check "transaction reflects the human decision" jq_eq .status APPROVED

echo "== 7. audit trail and notifications"
call GET "/api/audit/events?action=RISK_DECISION&size=5" "$ANALYST"; check "audit holds RISK_DECISION events" status_is 200
check "audit events carry the model version" jq -e '.content[0].modelVersion != null' <<<"$BODY"
call GET "/api/audit/events?action=REVIEW_RESOLVED&resourceId=$REVIEW_TX" "$ANALYST"; check "review resolution is audited" jq -e '.totalElements >= 1' <<<"$BODY"
call GET /api/audit/events/verify "$ADMIN"; check "audit hash chain is intact" jq_eq .valid true
call GET /api/notifications "$ANALYST"; check "notifications exist for review/decline" jq -e '.totalElements >= 1' <<<"$BODY"

echo "== 8. model serving"
call GET /api/ml/model/info "$ANALYST"; check "model info reachable by analyst" status_is 200
echo "     model: $(jq -c '{model_version, registry_version, model_source, alias}' <<<"$BODY")"
call POST /api/ml/predict "$ADMIN" '{}'; check "/predict is not exposed through the gateway" test "$STATUS" = 404 -o "$STATUS" = 403
call GET /api/ml/projections "$ANALYST"; check "projections endpoint" jq -e '.points | length > 0' <<<"$BODY"

if [[ "${E2E_SKIP_MLFLOW:-0}" != 1 ]]; then
  echo "== 9. MLflow registry"
  code="$(curl -sS -o /tmp/e2e.mlflow -w '%{http_code}' "$MLFLOW/api/2.0/mlflow/registered-models/alias?name=riskpulse-fraud&alias=champion" || true)"
  check "model riskpulse-fraud has a champion alias" test "$code" = 200
fi

if [[ "${E2E_SKIP_PROM:-0}" != 1 ]]; then
  echo "== 10. Prometheus metrics"
  q() { curl -sSG "$PROMETHEUS/api/v1/query" --data-urlencode "query=$1" | jq -r '.data.result[0].value[1] // "0"'; }
  for _ in $(seq 1 12); do
    [[ "$(q 'sum(riskpulse_transactions_total)')" != "0" && "$(q 'sum(riskpulse_ml_predictions_total)')" != "0" ]] && break; sleep 5
  done
  check "riskpulse_transactions_total > 0" test "$(q 'sum(riskpulse_transactions_total) > 0')" != 0
  check "riskpulse_ml_predictions_total > 0" test "$(q 'sum(riskpulse_ml_predictions_total) > 0')" != 0
  check "riskpulse_review_queue_size is exported" test "$(curl -sSG "$PROMETHEUS/api/v1/query" --data-urlencode 'query=riskpulse_review_queue_size' | jq '.data.result | length')" -ge 1
  check "all scrape targets are up" test "$(q 'count(up{job=~"riskpulse-.*"} == 0) or vector(0)')" = 0
fi

echo
echo "e2e: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
