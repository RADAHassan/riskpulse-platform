import json

from app import metrics


def test_health_endpoints_need_no_key(client):
    assert client.get("/health/live").json() == {"status": "UP"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["model_version"] == "riskpulse-29d-v2.0-canonical"


def test_predict_requires_service_key(client, legit_payload):
    assert client.post("/predict", json=legit_payload).status_code == 401
    assert client.post("/predict", json=legit_payload, headers={"X-Service-Key": "wrong"}).status_code == 401


def test_predict_contract(client, headers, legit_payload):
    r = client.post("/predict", json=legit_payload, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("prediction", "probability", "uncertainty", "decision", "model_version", "conformal_set"):
        assert key in body
    assert body["decision"] in {"APPROVE", "HUMAN_REVIEW", "DECLINE"}
    assert 0 <= body["probability"] <= 1
    assert body["prediction"] in (0, 1)
    assert body["model_source"] == "local-bundle"
    assert body["transaction_id"] == "t-1"
    assert body["inference_ms"] >= 0


def test_uncertain_prediction_never_declined(client, headers, fraud_like_payload):
    body = client.post("/predict", json=fraud_like_payload, headers=headers).json()
    if body["uncertainty"] >= 0.25 or body["conformal_set"] != ["FRAUD"]:
        assert body["decision"] != "DECLINE"


def test_validation_rejects_bad_payloads(client, headers):
    base = {"amount": 10.0, "features": [0.0] * 28}
    assert client.post("/predict", json={**base, "features": [0.0] * 27}, headers=headers).status_code == 422
    assert client.post("/predict", json={**base, "features": [0.0] * 29}, headers=headers).status_code == 422
    assert client.post("/predict", json={**base, "amount": -1}, headers=headers).status_code == 422
    assert client.post("/predict", json={**base, "extra": 1}, headers=headers).status_code == 422
    assert client.post("/predict", json={**base, "features": ["a"] * 28}, headers=headers).status_code == 422


def test_non_finite_values_are_rejected(client, headers):
    nan_body = '{"amount": 1, "features": [' + ",".join(["NaN"] + ["0"] * 27) + "]}"
    r = client.post("/predict", content=nan_body, headers={**headers, "content-type": "application/json"})
    assert r.status_code == 422
    inf_body = '{"amount": Infinity, "features": [' + ",".join(["0"] * 28) + "]}"
    r = client.post("/predict", content=inf_body, headers={**headers, "content-type": "application/json"})
    assert r.status_code == 422


def test_oversized_body_is_rejected(client, headers):
    r = client.post("/predict", content="x" * 2_000_000, headers={**headers, "content-type": "application/json"})
    assert r.status_code == 413


def test_batch(client, headers, legit_payload, fraud_like_payload):
    r = client.post("/predict/batch", json={"transactions": [legit_payload, fraud_like_payload]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_batch_size_limit(client, headers, legit_payload, monkeypatch):
    monkeypatch.setenv("MAX_BATCH_SIZE", "2")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        r = client.post("/predict/batch", json={"transactions": [legit_payload] * 3}, headers=headers)
        assert r.status_code == 413
    finally:
        monkeypatch.delenv("MAX_BATCH_SIZE")
        get_settings.cache_clear()


def test_model_info(client, headers):
    r = client.get("/model/info", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["model_source"] == "local-bundle"
    assert body["policy"]["conformal_q_fraud"] == 0.95251
    assert client.get("/model/info").status_code == 401


def test_model_reload_falls_back_to_local(client, headers):
    r = client.post("/model/reload", headers=headers)
    assert r.status_code == 200
    assert r.json()["model_source"] == "local-bundle"


def test_report_projections_and_figures(client, headers):
    report = client.get("/model/report", headers=headers).json()
    models = {row["Model"] for row in report["benchmark"]}
    assert {"XGBoost", "Random Forest", "Logistic Regression"} <= models
    assert report["friedman"]["friedman_5_models"]["df"] == 4
    assert report["statistical_tests"]
    assert report["conformal"]["serving_quantiles"]["q_fraud"] == 0.95251

    proj = client.get("/projections", headers=headers).json()
    assert len(proj["points"]) == 2900
    assert {"pca_x", "tsne_x", "umap_x", "true_label", "human_review"} <= set(proj["points"][0])

    assert client.get("/model/figures/reliability", headers=headers).headers["content-type"] == "image/png"
    assert client.get("/model/figures/nope", headers=headers).status_code == 404
    assert client.get("/model/figures/..%2f..%2fetc", headers=headers).status_code == 404


def test_metrics_exposed_with_contract_names(client, headers, legit_payload):
    client.post("/predict", json=legit_payload, headers=headers)
    text = client.get("/metrics").text
    for name in (
        "riskpulse_ml_inference_seconds_bucket",
        "riskpulse_ml_prediction_uncertainty_bucket",
        "riskpulse_ml_predictions_total",
        "riskpulse_ml_human_review_total",
        'riskpulse_ml_model_info{source="local-bundle",version="riskpulse-29d-v2.0-canonical"} 1.0',
        "http_request_duration_seconds_bucket",
    ):
        assert name in text, name


def test_metrics_counters_increase(client, headers, legit_payload):
    before = sum(s.value for m in metrics.PREDICTIONS.collect() for s in m.samples if s.name.endswith("_total"))
    client.post("/predict", json=legit_payload, headers=headers)
    after = sum(s.value for m in metrics.PREDICTIONS.collect() for s in m.samples if s.name.endswith("_total"))
    assert after == before + 1


def test_openapi_is_valid_json(client):
    assert json.loads(client.get("/openapi.json").text)["info"]["title"] == "RiskPulse ml-serving"
