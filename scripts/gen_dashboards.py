"""Generate the 10 provisioned Grafana dashboards (JSON, committed) from a compact description.

    python scripts/gen_dashboards.py

Dashboards are provisioned as code (Docker Compose volume / Kubernetes ConfigMap with the grafana_dashboard label).
The datasource is always the provisioned Prometheus with uid ``prometheus``.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "infra" / "monitoring" / "grafana" / "dashboards"
DS = {"type": "prometheus", "uid": "prometheus"}
SPRING = 'job="riskpulse-spring"'
ML = 'job="riskpulse-ml-serving"'
_id = 0


def _next() -> int:
    global _id
    _id += 1
    return _id


def target(expr: str, legend: str = "", ref: str = "A", instant: bool = False, fmt: str | None = None) -> dict:
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "instant": instant}
    if fmt:
        t["format"] = fmt
    return t


def _targets(items) -> list[dict]:
    out = []
    for i, it in enumerate(items):
        expr, legend = (it, "") if isinstance(it, str) else it
        out.append(target(expr, legend, chr(ord("A") + i)))
    return out


def ts(title, items, x, y, w=12, h=8, unit="short", desc="", stack=False, fill=10, minv=None, maxv=None) -> dict:
    custom = {"drawStyle": "line", "lineWidth": 1, "fillOpacity": fill, "showPoints": "never", "spanNulls": False,
              "stacking": {"mode": "normal" if stack else "none"}}
    defaults = {"unit": unit, "custom": custom}
    if minv is not None:
        defaults["min"] = minv
    if maxv is not None:
        defaults["max"] = maxv
    return {"id": _next(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": _targets(items),
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def stat(title, expr, x, y, w=4, h=4, unit="short", steps=None, desc="", mappings=None, text_mode="auto", color_mode="value") -> dict:
    steps = steps or [("green", None)]
    return {"id": _next(), "type": "stat", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": [target(expr, instant=True)],
            "fieldConfig": {"defaults": {"unit": unit, "mappings": mappings or [],
                                         "thresholds": {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}},
                            "overrides": []},
            "options": {"colorMode": color_mode, "graphMode": "area", "textMode": text_mode, "reduceOptions": {"calcs": ["lastNotNull"]}}}


def gauge(title, expr, x, y, w=4, h=6, unit="percentunit", steps=None, minv=0, maxv=1) -> dict:
    steps = steps or [("green", None), ("orange", 0.7), ("red", 0.8)]
    return {"id": _next(), "type": "gauge", "title": title, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [target(expr, instant=True)],
            "fieldConfig": {"defaults": {"unit": unit, "min": minv, "max": maxv,
                                         "thresholds": {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "showThresholdMarkers": True}}


def table(title, expr, x, y, w=12, h=8, desc="") -> dict:
    return {"id": _next(), "type": "table", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": [target(expr, instant=True, fmt="table")],
            "fieldConfig": {"defaults": {}, "overrides": []},
            "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True}}}],
            "options": {"showHeader": True}}


def heatmap(title, expr, x, y, w=12, h=8, desc="") -> dict:
    t = target(expr, "{{le}}", fmt="heatmap")
    return {"id": _next(), "type": "heatmap", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": [t],
            "options": {"calculate": False, "yAxis": {"axisPlacement": "left"}, "cellGap": 1,
                        "color": {"scheme": "Oranges", "mode": "scheme"}}}


def text(title, md, x, y, w=24, h=6) -> dict:
    return {"id": _next(), "type": "text", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "options": {"mode": "markdown", "content": md}}


def dashboard(uid, title, tags, panels, variables=None, desc="") -> dict:
    return {"uid": uid, "title": title, "description": desc, "tags": ["riskpulse", *tags], "timezone": "browser",
            "schemaVersion": 39, "version": 1, "editable": False, "refresh": "10s", "time": {"from": "now-1h", "to": "now"},
            "graphTooltip": 1, "annotations": {"list": []}, "templating": {"list": variables or []}, "panels": panels,
            "links": [{"title": "All RiskPulse dashboards", "type": "dashboards", "tags": ["riskpulse"], "asDropdown": True}]}


def var_query(name, query, label=None, multi=True) -> dict:
    return {"name": name, "label": label or name, "type": "query", "datasource": DS,
            "query": {"query": query, "refId": f"var-{name}"}, "definition": query, "refresh": 2, "sort": 1,
            "multi": multi, "includeAll": multi, "allValue": ".*", "current": {"text": "All", "value": "$__all"} if multi else {}}


APPS = 'application=~"$application"'

# --------------------------------------------------------------------------------------------------
def system_health() -> dict:
    return dashboard("rp-system-health", "RiskPulse — System health", ["overview"], [
        stat("Components up", f'sum(up{{job=~"riskpulse-.*"}})', 0, 0, 4, 4, steps=[("red", None), ("green", 9)]),
        stat("Components down", f'count(up{{job=~"riskpulse-.*"}} == 0) or vector(0)', 4, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        stat("Firing alerts", 'count(ALERTS{alertstate="firing", alertname!="Watchdog"}) or vector(0)', 8, 0, 4, 4, steps=[("green", None), ("orange", 1), ("red", 3)]),
        stat("Requests / s", f'sum(rate(http_server_requests_seconds_count{{{SPRING}, uri!~"/actuator.*"}}[2m]))', 12, 0, 4, 4, unit="reqps"),
        stat("p95 latency", f'histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{{{SPRING}, uri!~"/actuator.*"}}[5m])))', 16, 0, 4, 4, unit="s", steps=[("green", None), ("orange", 1), ("red", 2)]),
        stat("5xx ratio", f'sum(rate(http_server_requests_seconds_count{{{SPRING}, status=~"5.."}}[5m])) / sum(rate(http_server_requests_seconds_count{{{SPRING}}}[5m]))', 20, 0, 4, 4, unit="percentunit", steps=[("green", None), ("orange", 0.01), ("red", 0.05)]),
        table("Scrape targets", 'up{job=~"riskpulse-.*"}', 0, 4, 12, 9, desc="1 = up, 0 = down"),
        table("Firing alerts", 'ALERTS{alertstate="firing"}', 12, 4, 12, 9),
        ts("Availability per component", [('up{job=~"riskpulse-.*"}', "{{application}}")], 0, 13, 12, 7, minv=0, maxv=1, fill=0),
        ts("Request rate per service", [(f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, uri!~"/actuator.*"}}[2m]))', "{{application}}")], 12, 13, 12, 7, unit="reqps", stack=True),
        stat("Review queue", "riskpulse_review_queue_size", 0, 20, 4, 4, steps=[("green", None), ("orange", 10), ("red", 25)]),
        stat("ML model", "riskpulse_ml_model_info", 4, 20, 8, 4, text_mode="name", color_mode="none"),
        stat("Transactions / min", "sum(rate(riskpulse_transactions_total[5m])) * 60", 12, 20, 4, 4),
        stat("DB connections", "sum(pg_stat_activity_count)", 16, 20, 4, 4),
    ], desc="Is everything up? Errors, latency and alerts at a glance.")


def microservices() -> dict:
    var = [var_query("application", f'label_values(up{{{SPRING}}}, application)', "Service")]
    return dashboard("rp-microservices", "RiskPulse — Microservices (Spring Boot)", ["spring"], [
        ts("Request rate", [(f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, {APPS}, uri!~"/actuator.*"}}[2m]))', "{{application}}")], 0, 0, 8, 8, unit="reqps"),
        ts("Latency p50 / p95 / p99", [
            (f'histogram_quantile(0.50, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{SPRING}, {APPS}, uri!~"/actuator.*"}}[5m])))', "p50 {{application}}"),
            (f'histogram_quantile(0.95, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{SPRING}, {APPS}, uri!~"/actuator.*"}}[5m])))', "p95 {{application}}"),
            (f'histogram_quantile(0.99, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{SPRING}, {APPS}, uri!~"/actuator.*"}}[5m])))', "p99 {{application}}")], 8, 0, 8, 8, unit="s", fill=0),
        ts("HTTP errors (4xx / 5xx per second)", [
            (f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, {APPS}, status=~"5.."}}[2m]))', "5xx {{application}}"),
            (f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, {APPS}, status=~"4.."}}[2m]))', "4xx {{application}}")], 16, 0, 8, 8, unit="reqps"),
        ts("Slowest endpoints (p95)", [(f'topk(8, histogram_quantile(0.95, sum by (le, application, uri) (rate(http_server_requests_seconds_bucket{{{SPRING}, {APPS}, uri!~"/actuator.*"}}[5m]))))', "{{application}} {{uri}}")], 0, 8, 12, 8, unit="s", fill=0),
        ts("Process CPU", [(f'process_cpu_usage{{{SPRING}, {APPS}}}', "{{application}}")], 12, 8, 6, 8, unit="percentunit", maxv=1),
        ts("JVM heap used", [(f'sum by (application) (jvm_memory_used_bytes{{{SPRING}, {APPS}, area="heap"}})', "{{application}}")], 18, 8, 6, 8, unit="bytes"),
        ts("JVM GC pause (s/s)", [(f'sum by (application) (rate(jvm_gc_pause_seconds_sum{{{SPRING}, {APPS}}}[2m]))', "{{application}}")], 0, 16, 8, 7, unit="s"),
        ts("Live threads", [(f'jvm_threads_live_threads{{{SPRING}, {APPS}}}', "{{application}}")], 8, 16, 8, 7),
        ts("DB pool: active connections", [(f'hikaricp_connections_active{{{SPRING}, {APPS}}}', "{{application}}")], 16, 16, 8, 7),
        ts("Resilience4j circuit breaker state (1 = active)", [(f'resilience4j_circuitbreaker_state{{{SPRING}, {APPS}}} == 1', "{{application}} {{name}} {{state}}")], 0, 23, 12, 7, fill=0),
        ts("Gateway upstream requests (Spring Cloud Gateway)", [('sum by (routeId, httpStatusCode) (rate(spring_cloud_gateway_requests_seconds_count[2m]))', "{{routeId}} {{httpStatusCode}}")], 12, 23, 12, 7, unit="reqps"),
    ], variables=var, desc="Per-service golden signals and JVM health.")


def cluster() -> dict:
    ns = 'namespace="riskpulse"'
    return dashboard("rp-cluster", "RiskPulse — Kubernetes cluster", ["kubernetes"], [
        stat("Nodes ready", 'sum(kube_node_status_condition{condition="Ready", status="true"})', 0, 0, 4, 4, steps=[("red", None), ("green", 1)]),
        stat("Pods running (riskpulse)", f'sum(kube_pod_status_phase{{{ns}, phase="Running"}})', 4, 0, 4, 4),
        stat("Pods not running", f'sum(kube_pod_status_phase{{{ns}, phase=~"Pending|Failed|Unknown"}}) or vector(0)', 8, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        stat("Container restarts (1 h)", f'sum(increase(kube_pod_container_status_restarts_total{{{ns}}}[1h])) or vector(0)', 12, 0, 4, 4, steps=[("green", None), ("orange", 1), ("red", 5)]),
        gauge("Cluster CPU", '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', 16, 0, 4, 4),
        gauge("Cluster memory", '1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)', 20, 0, 4, 4),
        ts("Node CPU", [('1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))', "{{instance}}")], 0, 4, 12, 8, unit="percentunit", maxv=1),
        ts("Node memory used", [('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes', "{{instance}}")], 12, 4, 12, 8, unit="bytes"),
        ts("Pod CPU (cores)", [(f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{ns}, container!=""}}[2m]))', "{{pod}}")], 0, 12, 12, 8, unit="short"),
        ts("Pod memory (working set)", [(f'sum by (pod) (container_memory_working_set_bytes{{{ns}, container!=""}})', "{{pod}}")], 12, 12, 12, 8, unit="bytes"),
        ts("Network receive / transmit per pod", [
            (f'sum by (pod) (rate(container_network_receive_bytes_total{{{ns}}}[2m]))', "rx {{pod}}"),
            (f'-sum by (pod) (rate(container_network_transmit_bytes_total{{{ns}}}[2m]))', "tx {{pod}}")], 0, 20, 12, 8, unit="Bps"),
        ts("Pods by phase", [(f'sum by (phase) (kube_pod_status_phase{{{ns}}})', "{{phase}}")], 12, 20, 12, 8, stack=True),
        ts("CPU usage vs limit (alert threshold 80 %)", [(f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{ns}, container!=""}}[5m])) / sum by (pod) (kube_pod_container_resource_limits{{{ns}, resource="cpu"}})', "{{pod}}")], 0, 28, 12, 8, unit="percentunit", fill=0),
        ts("Memory usage vs limit", [(f'sum by (pod) (container_memory_working_set_bytes{{{ns}, container!=""}}) / sum by (pod) (kube_pod_container_resource_limits{{{ns}, resource="memory"}})', "{{pod}}")], 12, 28, 12, 8, unit="percentunit", fill=0),
    ], desc="Nodes, pods and resources (kube-state-metrics, cAdvisor, node-exporter).")


def load_scalability() -> dict:
    ns = 'namespace="riskpulse"'
    return dashboard("rp-load-scalability", "RiskPulse — Load & scalability", ["load", "hpa"], [
        stat("Gateway req/s", f'sum(rate(http_server_requests_seconds_count{{application="api-gateway", uri!~"/actuator.*"}}[1m]))', 0, 0, 4, 4, unit="reqps"),
        stat("Gateway p95", 'histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{application="api-gateway", uri!~"/actuator.*"}[1m])))', 4, 0, 4, 4, unit="s", steps=[("green", None), ("orange", 1), ("red", 2)]),
        stat("Gateway 5xx ratio", 'sum(rate(http_server_requests_seconds_count{application="api-gateway", status=~"5.."}[1m])) / sum(rate(http_server_requests_seconds_count{application="api-gateway"}[1m]))', 8, 0, 4, 4, unit="percentunit", steps=[("green", None), ("orange", 0.01), ("red", 0.05)]),
        stat("Current replicas (all HPAs)", f'sum(kube_horizontalpodautoscaler_status_current_replicas{{{ns}}})', 12, 0, 4, 4),
        stat("Desired replicas (all HPAs)", f'sum(kube_horizontalpodautoscaler_status_desired_replicas{{{ns}}})', 16, 0, 4, 4),
        stat("k6 virtual users", "max(k6_vus)", 20, 0, 4, 4),
        ts("Throughput by service", [(f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, uri!~"/actuator.*"}}[1m]))', "{{application}}")], 0, 4, 12, 8, unit="reqps", stack=True),
        ts("Latency p95 by service", [(f'histogram_quantile(0.95, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{SPRING}, uri!~"/actuator.*"}}[1m])))', "{{application}}")], 12, 4, 12, 8, unit="s", fill=0),
        ts("HPA: current vs desired vs max replicas", [
            (f'kube_horizontalpodautoscaler_status_current_replicas{{{ns}}}', "current {{horizontalpodautoscaler}}"),
            (f'kube_horizontalpodautoscaler_status_desired_replicas{{{ns}}}', "desired {{horizontalpodautoscaler}}"),
            (f'kube_horizontalpodautoscaler_spec_max_replicas{{{ns}}}', "max {{horizontalpodautoscaler}}")], 0, 12, 12, 8, fill=0),
        ts("CPU per pod vs HPA target (70 %)", [(f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{ns}, container!=""}}[1m])) / sum by (pod) (kube_pod_container_resource_requests{{{ns}, resource="cpu"}})', "{{pod}}")], 12, 12, 12, 8, unit="percentunit", fill=0),
        ts("k6: requests/s and failed requests/s", [("sum(rate(k6_http_reqs_total[30s]))", "requests"), ("sum(rate(k6_http_reqs_total{expected_response=\"false\"}[30s]))", "failed")], 0, 20, 12, 8, unit="reqps"),
        ts("k6: http_req_duration p95", [("k6_http_req_duration_p95", "p95"), ("k6_http_req_duration_p99", "p99")], 12, 20, 12, 8, unit="ms", fill=0),
        ts("Memory per pod", [(f'sum by (pod) (container_memory_working_set_bytes{{{ns}, container!=""}})', "{{pod}}")], 0, 28, 12, 8, unit="bytes"),
        ts("ml-serving inference rate", [("sum(rate(riskpulse_ml_inference_seconds_count[1m]))", "inferences/s")], 12, 28, 12, 8, unit="reqps"),
    ], desc="k6 phases (normal → high → overload → recovery): throughput, latency, errors, CPU/RAM, replicas and HPA activity.")


def high_availability() -> dict:
    ns = 'namespace="riskpulse"'
    return dashboard("rp-high-availability", "RiskPulse — High availability", ["ha", "kubernetes"], [
        stat("Deployments fully available", f'count(kube_deployment_status_replicas_available{{{ns}}} == kube_deployment_spec_replicas{{{ns}}})', 0, 0, 5, 4, steps=[("red", None), ("green", 1)]),
        stat("Deployments degraded", f'count(kube_deployment_status_replicas_available{{{ns}}} < kube_deployment_spec_replicas{{{ns}}}) or vector(0)', 5, 0, 5, 4, steps=[("green", None), ("orange", 1)]),
        stat("Deployments with 0 replica", f'count(kube_deployment_status_replicas_available{{{ns}}} == 0) or vector(0)', 10, 0, 5, 4, steps=[("green", None), ("red", 1)]),
        stat("Pod restarts (1 h)", f'sum(increase(kube_pod_container_status_restarts_total{{{ns}}}[1h])) or vector(0)', 15, 0, 5, 4, steps=[("green", None), ("orange", 1), ("red", 5)]),
        stat("Circuit breakers open", 'count(resilience4j_circuitbreaker_state{state="open"} == 1) or vector(0)', 20, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        ts("Available replicas per deployment", [(f'kube_deployment_status_replicas_available{{{ns}}}', "{{deployment}}")], 0, 4, 12, 8, fill=0),
        ts("Unavailable replicas", [(f'kube_deployment_status_replicas_unavailable{{{ns}}}', "{{deployment}}")], 12, 4, 12, 8, stack=True),
        ts("Component availability (up)", [('up{job=~"riskpulse-.*"}', "{{application}} {{instance}}")], 0, 12, 12, 8, minv=0, maxv=1, fill=0),
        ts("Pod restarts", [(f'increase(kube_pod_container_status_restarts_total{{{ns}}}[5m])', "{{pod}}")], 12, 12, 12, 8),
        ts("PodDisruptionBudget: disruptions allowed", [(f'kube_poddisruptionbudget_status_pod_disruptions_allowed{{{ns}}}', "{{poddisruptionbudget}}")], 0, 20, 12, 8, fill=0),
        ts("Pods spread over nodes", [(f'count by (node) (kube_pod_info{{{ns}}})', "{{node}}")], 12, 20, 12, 8, stack=True),
        ts("Gateway success ratio (continuity during chaos)", ['1 - (sum(rate(http_server_requests_seconds_count{application="api-gateway", status=~"5.."}[1m])) / sum(rate(http_server_requests_seconds_count{application="api-gateway"}[1m])))'], 0, 28, 12, 8, unit="percentunit", minv=0, maxv=1, fill=0),
        ts("ML fallback decisions (ml-serving down → human review)", [("increase(riskpulse_risk_fallbacks_total[1m])", "fallbacks / min")], 12, 28, 12, 8),
    ], desc="Replicas, restarts, disruption budgets and service continuity while pods or nodes are killed.")


def ml_inference() -> dict:
    return dashboard("rp-ml-inference", "RiskPulse — ML inference", ["ml"], [
        stat("Model version", "riskpulse_ml_model_info", 0, 0, 8, 4, text_mode="name", color_mode="none"),
        stat("Predictions / s", "sum(rate(riskpulse_ml_predictions_total[1m]))", 8, 0, 4, 4, unit="reqps"),
        stat("Inference p95", "histogram_quantile(0.95, sum by (le) (rate(riskpulse_ml_inference_seconds_bucket[5m])))", 12, 0, 4, 4, unit="s", steps=[("green", None), ("orange", 0.05), ("red", 0.25)]),
        stat("Human-review share", 'sum(rate(riskpulse_ml_predictions_total{decision="HUMAN_REVIEW"}[5m])) / sum(rate(riskpulse_ml_predictions_total[5m]))', 16, 0, 4, 4, unit="percentunit"),
        stat("ml-serving up", f'up{{{ML}}}', 20, 0, 4, 4, steps=[("red", None), ("green", 1)]),
        ts("Inference time p50 / p95 / p99", [
            ("histogram_quantile(0.50, sum by (le) (rate(riskpulse_ml_inference_seconds_bucket[5m])))", "p50"),
            ("histogram_quantile(0.95, sum by (le) (rate(riskpulse_ml_inference_seconds_bucket[5m])))", "p95"),
            ("histogram_quantile(0.99, sum by (le) (rate(riskpulse_ml_inference_seconds_bucket[5m])))", "p99")], 0, 4, 12, 8, unit="s", fill=0),
        heatmap("Inference time distribution", "sum by (le) (increase(riskpulse_ml_inference_seconds_bucket[1m]))", 12, 4, 12, 8),
        ts("Predictions per decision", [("sum by (decision) (rate(riskpulse_ml_predictions_total[1m]))", "{{decision}}")], 0, 12, 12, 8, unit="reqps", stack=True),
        ts("FastAPI request latency p95 per endpoint", [(f'histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket{{{ML}}}[5m])))', "{{handler}}")], 12, 12, 12, 8, unit="s", fill=0),
        ts("FastAPI requests by status", [(f'sum by (status) (rate(http_requests_total{{{ML}}}[1m]))', "{{status}}")], 0, 20, 12, 8, unit="reqps", stack=True),
        ts("ml-serving CPU and memory", [(f'rate(process_cpu_seconds_total{{{ML}}}[1m])', "cpu (cores)"), (f'process_resident_memory_bytes{{{ML}}} / 1e9', "rss (GB)")], 12, 20, 12, 8),
    ], desc="Latency and throughput of the FastAPI inference service.")


def model_performance() -> dict:
    notes = (
        "**Offline benchmark (from `ml/artifacts`, 10 expanding chronological OOT windows)** — XGBoost PR-AUC 0.7682 "
        "(95 % CI [0.6881, 0.8360]), RF 0.7805, MLP 0.7663, LR 0.7613, SVM 0.2535. Friedman omnibus p = 0.000279; "
        "XGBoost is statistically indistinguishable from RF/MLP/LR (Holm-adjusted p ≥ 0.826) and beats SVM (p_adj = 0.0078).\n\n"
        "**Expected healthy human-review rate** of the causal router: 0.30 %–1.11 % per window (ml/README.md, v2.3.8). "
        "Live review rates far above this band indicate drift."
    )
    return dashboard("rp-model-performance", "RiskPulse — Model performance", ["ml", "model"], [
        stat("Model", "riskpulse_ml_model_info", 0, 0, 8, 4, text_mode="name", color_mode="none"),
        stat("Decisions (1 h)", "sum(increase(riskpulse_ml_predictions_total[1h]))", 8, 0, 4, 4),
        stat("Human review rate (1 h)", 'sum(increase(riskpulse_ml_predictions_total{decision="HUMAN_REVIEW"}[1h])) / sum(increase(riskpulse_ml_predictions_total[1h]))', 12, 0, 6, 4, unit="percentunit", desc="Expected healthy band on real traffic: 0.30 %–1.11 %"),
        stat("Decline rate (1 h)", 'sum(increase(riskpulse_ml_predictions_total{decision="DECLINE"}[1h])) / sum(increase(riskpulse_ml_predictions_total[1h]))', 18, 0, 6, 4, unit="percentunit"),
        ts("Decision mix over time", [("sum by (decision) (rate(riskpulse_ml_predictions_total[5m]))", "{{decision}}")], 0, 4, 12, 8, unit="reqps", stack=True),
        ts("Review / decline ratio (drift proxy)", [
            ('sum(rate(riskpulse_ml_predictions_total{decision="HUMAN_REVIEW"}[10m])) / sum(rate(riskpulse_ml_predictions_total[10m]))', "human review"),
            ('sum(rate(riskpulse_ml_predictions_total{decision="DECLINE"}[10m])) / sum(rate(riskpulse_ml_predictions_total[10m]))', "decline")], 12, 4, 12, 8, unit="percentunit", fill=0),
        ts("Business decisions (transaction-service)", [("sum by (decision) (increase(riskpulse_transactions_total[5m]))", "{{decision}}")], 0, 12, 12, 8, stack=True),
        ts("Fallback decisions (ML unavailable)", [("increase(riskpulse_risk_fallbacks_total[5m])", "fallbacks")], 12, 12, 12, 8),
        ts("Model versions in service", [("riskpulse_ml_model_info", "{{version}} ({{source}})")], 0, 20, 12, 6, minv=0, maxv=1, fill=0),
        ts("Risk assessments by decision (risk-service)", [("sum by (decision) (increase(riskpulse_risk_assessments_total[5m]))", "{{decision}}")], 12, 20, 12, 6, stack=True),
        text("Reference numbers", notes, 0, 26, 24, 6),
    ], desc="Live decision behaviour of the served model against its validated offline performance.")


def uncertainty() -> dict:
    return dashboard("rp-uncertainty", "RiskPulse — Uncertainty & human review", ["ml", "uncertainty"], [
        stat("Uncertain predictions (≥ 0.25)", '1 - sum(rate(riskpulse_ml_prediction_uncertainty_bucket{le="0.25"}[10m])) / sum(rate(riskpulse_ml_prediction_uncertainty_count[10m]))', 0, 0, 6, 4, unit="percentunit", steps=[("green", None), ("orange", 0.05), ("red", 0.10)], desc="Alert HighMlUncertainty fires above 10 %"),
        stat("Open review cases", "riskpulse_review_queue_size", 6, 0, 6, 4, steps=[("green", None), ("orange", 10), ("red", 25)]),
        stat("Median uncertainty", "histogram_quantile(0.5, sum by (le) (rate(riskpulse_ml_prediction_uncertainty_bucket[10m])))", 12, 0, 6, 4, unit="none"),
        stat("p99 uncertainty", "histogram_quantile(0.99, sum by (le) (rate(riskpulse_ml_prediction_uncertainty_bucket[10m])))", 18, 0, 6, 4, unit="none"),
        heatmap("Uncertainty distribution over time", "sum by (le) (increase(riskpulse_ml_prediction_uncertainty_bucket[2m]))", 0, 4, 12, 9, desc="2*min(p, 1-p): 0 = certain, 1 = coin flip"),
        ts("Uncertainty quantiles", [
            ("histogram_quantile(0.5, sum by (le) (rate(riskpulse_ml_prediction_uncertainty_bucket[5m])))", "p50"),
            ("histogram_quantile(0.9, sum by (le) (rate(riskpulse_ml_prediction_uncertainty_bucket[5m])))", "p90"),
            ("histogram_quantile(0.99, sum by (le) (rate(riskpulse_ml_prediction_uncertainty_bucket[5m])))", "p99")], 12, 4, 12, 9, fill=0),
        ts("Human-review decisions / min", [("sum(increase(riskpulse_ml_human_review_total[1m]))", "routed to human review")], 0, 13, 12, 8),
        ts("Review queue size and growth", [("riskpulse_review_queue_size", "open cases"), ("deriv(riskpulse_review_queue_size[15m]) * 60", "growth / min")], 12, 13, 12, 8, fill=0),
        ts("Uncertain share by threshold", [
            ('1 - sum(rate(riskpulse_ml_prediction_uncertainty_bucket{le="0.1"}[10m])) / sum(rate(riskpulse_ml_prediction_uncertainty_count[10m]))', "≥ 0.10"),
            ('1 - sum(rate(riskpulse_ml_prediction_uncertainty_bucket{le="0.25"}[10m])) / sum(rate(riskpulse_ml_prediction_uncertainty_count[10m]))', "≥ 0.25"),
            ('1 - sum(rate(riskpulse_ml_prediction_uncertainty_bucket{le="0.5"}[10m])) / sum(rate(riskpulse_ml_prediction_uncertainty_count[10m]))', "≥ 0.50")], 0, 21, 12, 8, unit="percentunit", fill=0),
        ts("Declines vs reviews (uncertain predictions are never auto-declined)", [
            ('sum(rate(riskpulse_ml_predictions_total{decision="DECLINE"}[5m]))', "DECLINE"),
            ('sum(rate(riskpulse_ml_predictions_total{decision="HUMAN_REVIEW"}[5m]))', "HUMAN_REVIEW")], 12, 21, 12, 8, unit="reqps"),
    ], desc="Where the model is unsure and how many cases land in the human review queue.")


def errors_alerts() -> dict:
    return dashboard("rp-errors-alerts", "RiskPulse — Errors & alerts", ["alerts", "errors"], [
        stat("Firing", 'count(ALERTS{alertstate="firing"}) or vector(0)', 0, 0, 4, 4, steps=[("green", None), ("orange", 1), ("red", 3)]),
        stat("Critical", 'count(ALERTS{alertstate="firing", severity="critical"}) or vector(0)', 4, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        stat("Warning", 'count(ALERTS{alertstate="firing", severity="warning"}) or vector(0)', 8, 0, 4, 4, steps=[("green", None), ("orange", 1)]),
        stat("Pending", 'count(ALERTS{alertstate="pending"}) or vector(0)', 12, 0, 4, 4),
        stat("5xx ratio (all services)", f'sum(rate(http_server_requests_seconds_count{{{SPRING}, status=~"5.."}}[5m])) / sum(rate(http_server_requests_seconds_count{{{SPRING}}}[5m]))', 16, 0, 4, 4, unit="percentunit", steps=[("green", None), ("orange", 0.01), ("red", 0.05)]),
        stat("Audit delivery failures (1 h)", "sum(increase(riskpulse_audit_failures_total[1h])) or vector(0)", 20, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        table("Active alerts", 'ALERTS{alertstate=~"firing|pending"}', 0, 4, 24, 8),
        ts("5xx per service", [(f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, status=~"5.."}}[2m]))', "{{application}}")], 0, 12, 12, 8, unit="reqps"),
        ts("4xx per service", [(f'sum by (application) (rate(http_server_requests_seconds_count{{{SPRING}, status=~"4.."}}[2m]))', "{{application}}")], 12, 12, 12, 8, unit="reqps"),
        ts("Errors by endpoint (5xx)", [(f'topk(10, sum by (application, uri, status) (rate(http_server_requests_seconds_count{{{SPRING}, status=~"5.."}}[5m])))', "{{application}} {{uri}} {{status}}")], 0, 20, 12, 8, unit="reqps"),
        ts("Rate limiting and auth rejections (gateway 401/403/429)", [('sum by (status) (rate(http_server_requests_seconds_count{application="api-gateway", status=~"401|403|429"}[2m]))', "{{status}}")], 12, 20, 12, 8, unit="reqps"),
        ts("Alert history (firing over time)", [('count by (alertname) (ALERTS{alertstate="firing"})', "{{alertname}}")], 0, 28, 12, 8, stack=True),
        ts("Circuit breaker state / notifications", [('resilience4j_circuitbreaker_state{state="open"}', "open {{application}} {{name}}"), ("sum(rate(alertmanager_notifications_total[5m]))", "alert notifications/s")], 12, 28, 12, 8, fill=0),
    ], desc="HTTP errors, rejected requests and every firing alert.")


def security_posture() -> dict:
    return dashboard("rp-security-posture", "RiskPulse — Security posture", ["security", "devsecops"], [
        stat("Critical vulnerabilities", 'sum(trivy_image_vulnerabilities{severity="Critical"}) or vector(0)', 0, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        stat("High vulnerabilities", 'sum(trivy_image_vulnerabilities{severity="High"}) or vector(0)', 4, 0, 4, 4, steps=[("green", None), ("orange", 1), ("red", 10)]),
        stat("Medium vulnerabilities", 'sum(trivy_image_vulnerabilities{severity="Medium"}) or vector(0)', 8, 0, 4, 4),
        stat("Exposed secrets", "sum(trivy_image_exposedsecrets) or vector(0)", 12, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        stat("Config audit: critical/high", 'sum(trivy_resource_configaudits{severity=~"Critical|High"}) or vector(0)', 16, 0, 4, 4, steps=[("green", None), ("orange", 1), ("red", 5)]),
        stat("RBAC assessment: high+", 'sum(trivy_role_rbacassessments{severity=~"Critical|High"}) or vector(0)', 20, 0, 4, 4, steps=[("green", None), ("red", 1)]),
        ts("Vulnerabilities by severity", [("sum by (severity) (trivy_image_vulnerabilities)", "{{severity}}")], 0, 4, 12, 8, stack=True),
        table("Images with CRITICAL / HIGH findings", 'sum by (image_repository, image_tag, severity) (trivy_image_vulnerabilities{severity=~"Critical|High"}) > 0', 12, 4, 12, 8),
        ts("Kyverno admission decisions", [("sum by (rule_result, policy_name) (rate(kyverno_policy_results_total[5m]))", "{{policy_name}} {{rule_result}}")], 0, 12, 12, 8),
        ts("Kyverno: blocked admissions", [('sum by (policy_name) (increase(kyverno_policy_results_total{rule_result="fail"}[15m]))', "{{policy_name}}")], 12, 12, 12, 8, stack=True),
        ts("Gateway: authentication failures and throttling", [('sum by (status) (rate(http_server_requests_seconds_count{application="api-gateway", status=~"401|403|429"}[5m]))', "{{status}}")], 0, 20, 12, 8, unit="reqps"),
        ts("Account lockouts & refresh-token reuse (audit failures proxy)", [('sum(increase(http_server_requests_seconds_count{application="auth-service", uri="/api/auth/login", status="423"}[15m]))', "locked logins"), ('sum(increase(http_server_requests_seconds_count{application="auth-service", uri="/api/auth/refresh", status="401"}[15m]))', "refresh rejected")], 12, 20, 12, 8),
        ts("Pods not compliant (restarts / failed)", [('sum(kube_pod_status_phase{namespace="riskpulse", phase=~"Failed|Unknown"})', "failed pods")], 0, 28, 12, 6),
        text("What feeds this dashboard", "Trivy Operator (continuous image / config / RBAC scans), Kyverno (admission policies, `verifyImages`), "
             "gateway and auth-service request metrics. CI gates (CodeQL, Semgrep, Trivy, Gitleaks, ZAP…) report in the GitHub Security tab.", 12, 28, 12, 6),
    ], desc="Continuous security posture: vulnerabilities, misconfigurations, admission control and abuse signals.")


DASHBOARDS = [system_health, microservices, cluster, load_scalability, high_availability, ml_inference,
              model_performance, uncertainty, errors_alerts, security_posture]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for build in DASHBOARDS:
        dash = build()
        path = OUT / f"{dash['uid'].removeprefix('rp-')}.json"
        path.write_text(json.dumps(dash, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(OUT.parents[3])} ({len(dash['panels'])} panels)")


if __name__ == "__main__":
    main()
