# RiskPulse Platform — Enterprise Credit Card Fraud Detection Engine

Production-grade, cost-sensitive hybrid fraud detection system combining an **Undercomplete PyTorch Autoencoder** with a **Bayesian-Tuned XGBoost Classifier**, **Monotonic Isotonic Calibration**, and **TreeSHAP Adverse Action Explainability**.

## Key Engineering Highlights
- **Hybrid Anomaly Defense:** Undercomplete PyTorch Autoencoder (`31 -> 16 -> 8 -> 16 -> 31`) trained on legitimate transactions ($Y=0$) to inject reconstruction error (`AE_Recon_MSE`) and latent encodings into the supervised feature space.
- **Cost-Utility Optimization:** Asymmetric banking cost matrix ($C_{FP} = \$10$, $C_{FN} = \text{Amount} + \$25$, $C_{TP} = \$2$) yielding the optimal decision threshold **$t^* = 0.1442$**, reducing net financial loss by **21.00%**.
- **Probability Calibration:** Expected Calibration Error (**ECE = 0.0002**, **Brier = 0.00048**) via Isotonic Regression.
- **Temporal Integrity:** Validated on a strict chronological Out-Of-Time (OOT) split ($0\text{h} \to 48\text{h}$) with zero look-ahead leakage (**OOT PR-AUC = 0.7335**, **MCC = 0.8151**).
- **Regulatory Compliance:** Local TreeSHAP adverse action reason codes for declined transactions (`artifacts/sample_decline_reasons.json`).

## Master Benchmark Summary (Test Set)

| Model / Engineering Phase | Split Type | Cutoff ($t^*$) | PR-AUC | Net Financial Loss | Frauds Caught | Net Savings vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Baseline XGBoost** | Stratified | $0.5000$ | 0.8260 | \$2,988.64 | 53 / 74 (71.6%) | Baseline (\$0.00) |
| **Phase 1: Calibrated Triage** | Stratified | `[0.005, 0.80]` | 0.8559 | — | 62 / 74 (83.8%) | Requires 54 Manual Reviews |
| **Phase 2: Cost-Tuned XGBoost** | Stratified | $0.1442$ | **0.8559** | \$2,401.72 | 60 / 74 (81.1%) | +\$586.92 (+19.64%) |
| **Phase 2: Champion Hybrid (AE + XGB)** | Stratified | **$0.1442$** | 0.8263 | **\$2,360.93** | **62 / 74 (83.8%)** | **+\$627.71 (+21.00%)** |
| **Phase 2: Stacking (XGB+LGB+CAT)** | Stratified | $0.1442$ | 0.8017 | \$2,401.72 | 60 / 74 (81.1%) | +\$586.92 (+19.64%) |
| **Phase 2: Asymmetric Focal Loss** | Stratified | $0.1442$ | 0.6600 | \$4,146.93 | 51 / 74 (68.9%) | -\$1,158.29 (Hessian Vanishing) |
| **Phase 2: Chronological OOT Test** | Time-Based | $0.1293$ | 0.7335 | \$2,825.40 | 39 / 52 (75.0%) | +\$323.76 (Future Savings) |

## Repository Structure
- `src/` — Modular training, calibration, cost optimization, Autoencoder, OOT, stacking, and SHAP scripts.
- `artifacts/` — Exported `.joblib` models, isotonic calibrators, JSON audit logs, and cost curves.
- `examples_output/` — UMAP projections, confusion maps, and reconstruction separation plots.
- `run_all.sh` — End-to-end master execution pipeline.
