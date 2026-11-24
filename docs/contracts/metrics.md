# Metrics contract

| Metric | Type | Emitted by | Labels |
| :--- | :--- | :--- | :--- |
| `riskpulse_ml_inference_seconds` | histogram | ml-serving | – |
| `riskpulse_ml_prediction_uncertainty` | histogram | ml-serving | – |
| `riskpulse_ml_predictions_total` | counter | ml-serving | `decision` |
| `riskpulse_ml_human_review_total` | counter | ml-serving | – |
| `riskpulse_ml_model_info` | gauge (=1) | ml-serving | `version`, `source` |
| `riskpulse_transactions_total` | counter | transaction-service | `decision` |
| `riskpulse_review_queue_size` | gauge | risk-service | – |
| `http_server_requests_seconds_*` | histogram | Spring (Micrometer) | `uri`, `status`, `method` |
| `http_request_duration_seconds_*` / `http_requests_total` | histogram/counter | ml-serving | `handler`, `status` |
| `resilience4j_circuitbreaker_*` | gauge | risk-service | `name`, `state` |
