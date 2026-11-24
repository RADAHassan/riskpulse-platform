"""Prometheus metrics (names fixed by docs/contracts/metrics.md)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

INFERENCE_SECONDS = Histogram(
    "riskpulse_ml_inference_seconds",
    "Model inference time per transaction",
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=REGISTRY,
)
UNCERTAINTY = Histogram(
    "riskpulse_ml_prediction_uncertainty",
    "Uncertainty score (2*min(p,1-p)) of served predictions",
    buckets=(0.0, 0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0),
    registry=REGISTRY,
)
PREDICTIONS = Counter(
    "riskpulse_ml_predictions_total",
    "Predictions by final decision",
    ["decision"],
    registry=REGISTRY,
)
HUMAN_REVIEW = Counter(
    "riskpulse_ml_human_review_total",
    "Predictions routed to human review",
    registry=REGISTRY,
)
MODEL_INFO = Gauge(
    "riskpulse_ml_model_info",
    "Loaded model (value is always 1)",
    ["version", "source"],
    registry=REGISTRY,
)
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "handler", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "handler"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=REGISTRY,
)

# Pre-create label children so the series exist (value 0) before the first request.
for _decision in ("APPROVE", "HUMAN_REVIEW", "DECLINE"):
    PREDICTIONS.labels(decision=_decision)


def set_model_info(version: str, source: str) -> None:
    MODEL_INFO.clear()
    MODEL_INFO.labels(version=version, source=source).set(1)
