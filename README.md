# RiskPulse Platform — Validated Temporal Baseline for Imbalanced Fraud Detection

A temporally validated, fixed-capacity fraud detection baseline on the ULB Credit Card Fraud dataset. Rather than optimizing on leaked stratified splits, this study evaluates model families, probability calibration, dollar-weighted objectives, and rolling-quantile alert policies under strict disjoint Out-Of-Time (OOT) windows.

> **Core Finding:** Regularized 29D XGBoost reaches **~0.77 pooled OOT PR-AUC** (`0.7689` at seed 42; `0.7742 ± 0.0041` across 5 seeds) and **~78% recall** at a `0.20%` review budget. Extra features, aggressive hyperparameter tuning, amount weighting, and ensembling add no detectable gain under hourly block-bootstrapped CIs, while sustained fraud bursts remain the primary operational weakness.

---

## Disjoint OOT Benchmark Summary

Evaluated across 3 disjoint chronological OOT windows (`[60%, 73%]`, `[73%, 86%]`, `[86%, 100%]`; pooled `N = 113,491` transactions, `131` frauds) using a `6,000`-transaction hourly block bootstrap (`1,000` replicates, seed `42`).

| Model (29D: `Amount` + `V1–V28`) | Pooled OOT PR-AUC | Recall @ 0.20% Budget | Precision @ 0.20% | Dollar Recall @ 0.20% |
| :--- | :---: | :---: | :---: | :---: |
| **Default XGBoost 29D** | `0.7762` | ~78% | ~45% | `64.4%` |
| **Regularized XGBoost 29D (Primary)** | `0.7689` *(5-seed: `0.7742 ± 0.0041`)* | `78.6%` | `45.6%` | `64.4%` |
| **Logistic Regression 29D** | `0.7358` | — | — | — |
| **LightGBM 29D** | `0.7302` | — | — | — |
| **Log-Amount-Weighted XGB 29D (`1–3×`)** | `0.7613` `[0.6785, 0.8268]` | `77.1%` | `44.7%` | `64.4%` |
| **Linear-Amount-Weighted XGB 29D (cap `$1k`)** | `0.7791` `[0.7045, 0.8370]` | `80.2%` | `46.5%` | `65.6%` |

* **Dollar-Recall Ceiling:** Even strong linear dollar-proportional weighting produces no detectable change (`ΔPR-AUC = -0.0094 [-0.0266, +0.0102]`; `+1.2` pp dollar recall, ~1 transaction), indicating the `64.4%–65.6%` ceiling is driven by feature-space separability rather than an unweighted loss artifact.

![Disjoint Pooled OOT Precision-Recall Curves](figures/fig_pr_curves.png)

---

## Probability Calibration

Class weighting (`scale_pos_weight`) makes raw XGBoost probabilities severely overconfident (`BSS = -0.7164`, `ECE = 0.00656`). Fitting monotonic **Isotonic Regression** on the preceding calibration window raises Brier Skill Score to **`+0.6390`** (`ECE = 0.00011`, vs. Platt scaling `BSS = +0.4767`). Because overall ECE is dominated by ~113,300 near-zero-score transactions, high-score calibration is evidenced by BSS and the top probability bin (`n = 73`, `98.6%` observed fraud rate).

![Disjoint OOT Calibration Reliability](figures/fig_reliability.png)

---

## Streaming Alert Policy & Burst Resilience (`0.20%` Budget)

Online threshold adaptation using a `W = 20,000` label-free rolling-score quantile paired with an isotonic high-confidence guard (`P_cal >= 0.80`):

| Stream Scenario | Policy | Alerts (Rate) | Recall (TP / Total) | Precision |
| :--- | :--- | :---: | :---: | :---: |
| **Normal OOT Stream** (`131` frauds) | `quarantine_guard_only` | `269` (`0.237%`) | `79.4%` (`104 / 131`) | `38.7%` |
| **Burst 1** (`+500` jittered @ 20k; `631` total) | `quarantine_guard_only` | `485` (`0.425%`) | `55.2%` (`348 / 631`) | `71.8%` |
| **Burst 2** (`+1,000` jittered @ 65k; `1,131` total) | `standard` | `501` (`0.438%`) | `34.9%` (`395 / 1,131`) | `78.8%` |
| **Burst 2** (`+1,000` jittered @ 65k; `1,131` total) | `quarantine_guard_only` | `634` (`0.554%`) | `44.0%` (`498 / 1,131`) | `78.5%` |

* `quarantine_guard_only` prevents high-confidence (`P_cal >= 0.80`) burst alerts from polluting the rolling buffer—recovering `+103` additional frauds in Burst 2—while avoiding the `7×` alert explosion of `quarantine_all`.
* **Operational Limit:** No tested variant maintains the `0.20%` fixed analyst capacity under a sustained burst (Burst 2 reaches `~2.8×` budget and still misses `56%` of frauds); a hard per-window alert cap is the next operational control.

---

## Repository Structure & Reproducibility

* `src/ml/predictor.py` — Production inference wrapper with `quarantine_guard_only` rolling buffer logic.
* `src/ml/final_disjoint_reconciliation.py` — Disjoint rolling OOT evaluation & hourly block-bootstrap CIs.
* `src/ml/final_two_checks.py` — Linear vs. log dollar-weighting ablation and independent 1,000-fraud burst check.
* `src/ml/complete_table1_and_plots.py` & `src/ml/update_final_figures.py` — Complete Table 1 metrics and diagnostic plots.
* `figures/` — Final PR-curve (`fig_pr_curves.png`) and bin-count annotated reliability (`fig_reliability.png`) plots.
* `artifacts/` — Exported `.joblib` model bundles and audit outputs.

**Environment (reproducible with fixed seeds):** `Python 3.14.8` · `xgboost 3.4.1` · `scikit-learn 1.9.1` · `lightgbm 4.7.0`

---

## v2 Research Extensions (ULB Policy + IEEE-CIS Cross-Dataset Replication)

Evaluated in release `v2.1.0` (`4d7ec75`, merged to `main`) using the same strict disjoint OOT protocol (`[60%, 73%]`, `[73%, 86%]`, `[86%, 100%]`), post-hoc Isotonic calibration, and block-bootstrapped 95% CIs:

* **IEEE-CIS Disjoint OOT Baseline (`N=590,537`, `20,663` frauds):** Pooled OOT PR-AUC **`0.4835`** (`[0.4576, 0.5087]`); Isotonic calibration repairs raw Brier Skill Score from **`-1.0234` → `+0.2991`**.
* **Strictly Causal Entity & Velocity Features:** Both `card1+addr1` (1h/24h rolling windows, `0.4833`, `ΔPR-AUC = -0.0002`, 95% CI `[-0.0043, +0.0046]`) and `card1+addr1+D1` (`0.4818`) match the static baseline due to IEEE-CIS's pre-engineered `C1–C14` and `D1–D15` features.
* **Expected-Loss Queue Ranking (`P_cal × (Amount + $25)`):** Flat on ULB (`64.4% → 64.4%`, 95% CI `[-2.7%, +6.5%]`), but lifts IEEE-CIS dollar recall by **`+20.2 pp`** at 2% budget (`27.3% → 47.5%`) and **`+15.6 pp`** at 5% budget (`50.4% → 66.1%`).
* **Novel Attack Blind-Spot Test (IEEE-CIS, `ProductCD='C'`):** Holding out 4,412 `ProductCD='C'` frauds drops OOT recall under the global 5% budget to 0.0% (0/3,596). Under an equal-volume channel budget (`k_C = 1,371`, 38.1% recall ceiling), recall progresses from **34.4%** (supervised control) → **14.8%** (held-out supervised, 38.9% precision) → **23.0%** (unsupervised Isolation Forest, 60.2% precision).
* **Two-Tier Streaming Policy (`src/ml/predictor.py`):** Auto-declines (`P_cal >= 0.80`) bypass the human review cap (`89.6%` Tier-1 precision on IEEE-CIS), while the hard-capped human queue stays strictly under budget (`1.89%` vs. `2.0%` cap), delivering **`40.4%` combined recall**.

---

## Machine Learning & Statistical Validation (Tasks 2, 3, 4, 7 — `v2.3.2`)

Full `v2.1` methodology and cross-dataset audit are in [`riskpulse_technical_report_v2.pdf`](riskpulse_technical_report_v2.pdf) (`v2.1.0`, commit `4d7ec75`). All Tasks 2, 3, 4, and 7 artifacts are reproducible from `src/ml/v2_2_*.py` on deduplicated 29D chronological OOT ULB (`v2.3.2`).

### 1. Model Benchmarking & Statistical Validation (Tasks 2 & 3 — `src/ml/v2_2_benchmark_and_stats.py`)
* **Protocol:** 10 expanding chronological OOT windows (`[50%, 100%]`, 0.20% budget) instead of random k-fold CV to prevent future-to-past burst leakage. Stochastic models (RF, XGBoost, MLP) are averaged across **5 seeds** (`{7, 21, 42, 84, 128}`); **all 5 models** receive post-hoc Isotonic calibration on the preceding 10% split before Brier comparison.
* **5-Model PR-AUC (window-level 95% bootstrap CIs):** RF `0.7805` (`[0.6980, 0.8482]`), XGBoost `0.7682` (`[0.6881, 0.8360]`), MLP `0.7663` (`[0.6864, 0.8327]`), LR `0.7613` (`[0.6657, 0.8351]`), SVM (RBF, 15k legit subsample) `0.2535` (`[0.1912, 0.3239]`).
* **Calibrated Brier & Latency:** Post-Isotonic Brier: RF `0.000505`, XGBoost `0.000526` (raw `0.004627`), MLP `0.000543`, LR `0.000544` (raw `0.028812`), SVM `0.001489`. Single-request latency: XGBoost `0.44 ms` (`0.00049 ms/txn` batch) beats RF (`32.04 ms`) by **72x** and ties MLP (`0.42 ms`) and LR (`0.52 ms`).
* **Stats:** Friedman omnibus ($df=4$, 10 window seed means): $\chi^2 = 21.28, p = 0.0002787$. Pairwise Wilcoxon + Holm: XGBoost beats SVM ($p_{\text{adj}}=0.0078, \delta=1.00$) and is **statistically tied** with RF ($p_{\text{adj}}=0.826$), MLP ($p_{\text{adj}}=1.000$), and LR ($p_{\text{adj}}=1.000$). XGBoost is retained for its 72x latency edge over RF, calibrated parity, native class-imbalance handling, and production consistency (note: omnibus significance is driven by subsampled SVM).

### 2. Uncertainty Quantification & Serving Integration (Task 4 — `src/ml/v2_2_conformal_and_ensemble.py` & `src/ml/predictor.py`)
* **Mondrian Split-Conformal — 5-Seed Ensemble Study (`artifacts/conformal.json`):** Pooled OOT ($N=113,491$, 131 frauds) achieves **99.58% legit coverage** (target 99.5%) and **81.68% fraud coverage** (target 85.0%; W1 75.8%, W2 94.3%, W3 71.1%), routing **0.931%** (1,057 cases) to human review. The 3.3 pp fraud shortfall reflects temporal drift breaking exchangeability and small per-window calibration fraud counts (80, 29, 43).
* **5-Seed Variance:** Mean seed-variance std is **25x higher** on review cases (`0.00519`) and **137x higher** on frauds (`0.02884`) than on legit (`0.00021`). This measures seed variance rather than full structural epistemic uncertainty.
* **Serving Integration (`src/ml/predictor.py` & `serving_oot_evaluation` in `conformal.json`):** `v2_2_conformal_and_ensemble.py` reproducibly calibrates canonical-model `serving_quantiles` (`q_legit=0.00962`, `q_fraud=0.9619` on `[76%, 86%]`) and evaluates them on `[86%, 100%]` ($N=39,722$, 45 frauds: **99.64% legit coverage**, **71.11% fraud coverage**, **0.043%** / 17 conformal reviews). `predictor.py` returns both the Mondrian `conformal_set` / `conformal_review_flag` and a continuous `uncertainty_score = 2 * min(p, 1 - p)` (peaking at `p = 0.50`). Transactions with `uncertainty_score >= 0.25` (`0.125 <= p <= 0.875`) route to capped `MANUAL_REVIEW`—including downgrading borderline `AUTO_DECLINE` cases (`0.80 <= p <= 0.875`, with fail-safe fallback if the human cap is full; `0` rows fell in `[0.80, 0.875]` on `[86%, 100%]` due to Isotonic step discretization).

### 3. Latent Space Projections (Task 7 — `src/ml/v2_2_latent_projections.py`)
* **Setup & Disclosure (`artifacts/figures/pca_tsne_umap.png`):** Stratified OOT subsample ($N=2,744$) scaled with `log1p(Amount) + RobustScaler` (with PCA `PC1` clipped at the 1st–99th percentile and the clipped outlier count labeled in the panel title, leaving `PC2` uncropped), colored by a separate single-split `[50%, 60%]` conformal calibration (`0.101%` OOT review rate vs. Task 4's `0.931%` 3-window pooled rate). Both frauds (`4.77%` vs `0.12%` OOT) and conformal review cases (`4.19%` vs `0.10%` OOT) are oversampled for visibility.
* **Metrics & Interpretation:** PCA Trust `0.7064` / Sil `0.7710`; t-SNE Trust `0.9479` / Sil `0.2587`; UMAP Trust `0.9292` / Sil `0.3843`. Most frauds form a dense, isolated cluster (bottom in t-SNE, left in UMAP) and a long tail along negative PC2 in PCA, while a minority of frauds remain scattered among legitimate points. Conformal review cases cluster along the transition boundary between fraud and legitimate regions. Because `V1–V28` are already PCA components, 2D PCA serves as a linear baseline.

### 4. How to Reproduce (Run from Repository Root)
1. Place ULB dataset at `data/creditcard.csv` (gitignored).
2. Run in order:
```bash
python src/ml/v2_2_benchmark_and_stats.py
python src/ml/v2_2_conformal_and_ensemble.py
python src/ml/v2_2_latent_projections.py
```
3. Verify `predictor.py`:
```bash
python -c "import json; from src.ml.predictor import RiskPulseMLPredictor; print(json.dumps(RiskPulseMLPredictor().score_transaction(149.99, [0.0]*28), indent=2))"
```
