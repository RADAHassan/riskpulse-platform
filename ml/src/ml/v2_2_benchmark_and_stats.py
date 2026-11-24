"""
RiskPulse v2.3 — Unified 5-Model Temporal Benchmark & Statistical Validation
Covers Tasks 2 & 3 on 10 expanding chronological OOT windows (deduplicated 29D ULB)
with 5-seed evaluation for stochastic models, post-hoc Isotonic calibration for all
models, and both batch-amortized and single-transaction latency measurements.
Outputs:
- artifacts/benchmark_results.csv
- artifacts/statistical_tests.csv
- artifacts/statistical_summary.json
"""
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
import xgboost as xgb

warnings.filterwarnings("ignore")

SEEDS = [7, 21, 42, 84, 128]
STOCHASTIC_MODELS = {"Random Forest", "XGBoost", "MLP"}
N_WINDOWS = 10
TRAIN_START_FRAC = 0.50   # First 50% is initial training; remaining 50% split into 10 OOT blocks
CAL_FRAC = 0.10           # Preceding 10% of training history used for post-hoc Isotonic calibration
BUDGET_RATE = 0.0020      # 0.20% fixed alert budget
SVM_MAX_LEGIT = 15000     # Subsample cap for O(N^2) RBF-SVM training tractability
SINGLE_TXN_CALLS = 200    # Number of single-row inference calls for single-request latency


def cliffs_delta(x, y):
    x, y = np.asarray(x), np.asarray(y)
    diff = x[:, None] - y[None, :]
    return float((np.sum(diff > 0) - np.sum(diff < 0)) / (len(x) * len(y)))


def bootstrap_ci(values, n_boot=2000, seed=42):
    rng = np.random.default_rng(seed)
    arr = np.asarray(values)
    means = [np.mean(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)]
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]


def build_model(name, spw, seed):
    if name == "Logistic Regression":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=300, class_weight="balanced", random_state=seed, n_jobs=-1),
        )
    if name == "Random Forest":
        return RandomForestClassifier(
            n_estimators=150, max_depth=12, class_weight="balanced", random_state=seed, n_jobs=-1
        )
    if name == "XGBoost":
        return xgb.XGBClassifier(
            n_estimators=220,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=spw,
            eval_metric="logloss",
            random_state=seed,
            n_jobs=-1,
        )
    if name == "SVM (RBF)":
        return make_pipeline(
            StandardScaler(),
            SVC(kernel="rbf", C=1.0, class_weight="balanced", probability=True, random_state=seed),
        )
    if name == "MLP":
        return make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(64, 32),
                max_iter=30,
                early_stopping=True,
                random_state=seed,
            ),
        )
    raise ValueError(f"Unknown model: {name}")


def measure_single_txn_latency_ms(model, X_te, n_calls=SINGLE_TXN_CALLS):
    orig_jobs = {}
    if hasattr(model, "get_params") and hasattr(model, "set_params"):
        for k, v in model.get_params().items():
            if k == "n_jobs" or k.endswith("__n_jobs"):
                orig_jobs[k] = v
        if orig_jobs:
            model.set_params(**{k: 1 for k in orig_jobs})
    try:
        n_eval = min(n_calls, len(X_te))
        t0 = time.perf_counter()
        for i in range(n_eval):
            _ = model.predict_proba(X_te[i : i + 1])
        return ((time.perf_counter() - t0) * 1000.0) / n_eval
    finally:
        if orig_jobs:
            model.set_params(**orig_jobs)


def main():
    Path("artifacts").mkdir(exist_ok=True)
    df = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
    feature_cols = ["Amount"] + [f"V{i}" for i in range(1, 29)]
    X_all = df[feature_cols].values
    y_all = df["Class"].values
    n = len(df)

    split_points = np.linspace(int(n * TRAIN_START_FRAC), n, N_WINDOWS + 1, dtype=int)
    model_names = ["Logistic Regression", "Random Forest", "XGBoost", "SVM (RBF)", "MLP"]

    # Store window-level seed-averaged metrics (10 values per model) + seed-level PR-AUC std
    metric_keys = [
        "precision", "recall", "f1", "roc_auc", "pr_auc", "mcc",
        "brier_raw", "brier_cal", "batch_latency_ms", "single_latency_ms",
    ]
    metrics_store = {m: {k: [] for k in metric_keys} for m in model_names}
    seed_pr_stds = {m: [] for m in model_names}

    rng = np.random.default_rng(42)
    print(f"Running 5-model benchmark across {N_WINDOWS} expanding OOT windows (5 seeds for stochastic models)...")

    for w in range(N_WINDOWS):
        tr_end = split_points[w]
        te_end = split_points[w + 1]

        # Chronological 90% fit / 10% Isotonic calibration split strictly before test window
        cal_start = int(tr_end * (1.0 - CAL_FRAC))
        X_fit, y_fit = X_all[:cal_start], y_all[:cal_start]
        X_cal, y_cal = X_all[cal_start:tr_end], y_all[cal_start:tr_end]
        X_te, y_te = X_all[tr_end:te_end], y_all[tr_end:te_end]

        n_pos_te = int(y_te.sum())
        spw = (y_fit == 0).sum() / max((y_fit == 1).sum(), 1)
        k_alerts = max(1, int(round(len(y_te) * BUDGET_RATE)))

        # Stratified subsample for SVM (RBF)
        fraud_idx = np.where(y_fit == 1)[0]
        legit_idx = np.where(y_fit == 0)[0]
        sampled_legit = rng.choice(legit_idx, size=min(SVM_MAX_LEGIT, len(legit_idx)), replace=False)
        svm_idx = np.concatenate([fraud_idx, sampled_legit])
        X_fit_svm, y_fit_svm = X_fit[svm_idx], y_fit[svm_idx]

        print(f"  Window {w+1:02d}/{N_WINDOWS} | Fit: {len(y_fit):,} | Cal: {len(y_cal):,} | Test: {len(y_te):,} (frauds={n_pos_te})")

        for name in model_names:
            run_seeds = SEEDS if name in STOCHASTIC_MODELS else [42]
            w_vals = {k: [] for k in metric_keys}

            for s_idx, seed in enumerate(run_seeds):
                model = build_model(name, spw, seed)
                if name == "SVM (RBF)":
                    model.fit(X_fit_svm, y_fit_svm)
                else:
                    model.fit(X_fit, y_fit)

                # Post-hoc Isotonic calibration on preceding 10% chronological block
                cal_raw = model.predict_proba(X_cal)[:, 1]
                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(cal_raw, y_cal)

                # Batch inference latency
                t0 = time.perf_counter()
                probs_raw = model.predict_proba(X_te)[:, 1]
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                batch_lat = elapsed_ms / len(X_te)

                # Single-transaction inference latency (measured once per window on first seed)
                if s_idx == 0:
                    single_lat = measure_single_txn_latency_ms(model, X_te)
                    w_vals["single_latency_ms"].append(single_lat)

                probs_cal = iso.predict(probs_raw)

                # Top-0.20% fixed budget binary predictions (ranked by raw score to preserve fine ties)
                top_idx = np.argsort(probs_raw)[::-1][:k_alerts]
                preds = np.zeros(len(y_te), dtype=int)
                preds[top_idx] = 1

                w_vals["precision"].append(precision_score(y_te, preds, zero_division=0))
                w_vals["recall"].append(recall_score(y_te, preds, zero_division=0))
                w_vals["f1"].append(f1_score(y_te, preds, zero_division=0))
                w_vals["roc_auc"].append(roc_auc_score(y_te, probs_raw))
                w_vals["pr_auc"].append(average_precision_score(y_te, probs_raw))
                w_vals["mcc"].append(matthews_corrcoef(y_te, preds))
                w_vals["brier_raw"].append(brier_score_loss(y_te, probs_raw))
                w_vals["brier_cal"].append(brier_score_loss(y_te, probs_cal))
                w_vals["batch_latency_ms"].append(batch_lat)

            for k in metric_keys:
                metrics_store[name][k].append(float(np.mean(w_vals[k])))
            seed_pr_stds[name].append(float(np.std(w_vals["pr_auc"])) if len(run_seeds) > 1 else 0.0)

    # 1. Save benchmark_results.csv
    rows = []
    for name in model_names:
        ms = metrics_store[name]
        ci = bootstrap_ci(ms["pr_auc"])
        rows.append({
            "Model": name,
            "Seeds": len(SEEDS) if name in STOCHASTIC_MODELS else 1,
            "Precision@0.20%": round(float(np.mean(ms["precision"])), 4),
            "Recall@0.20%": round(float(np.mean(ms["recall"])), 4),
            "F1@0.20%": round(float(np.mean(ms["f1"])), 4),
            "ROC-AUC": round(float(np.mean(ms["roc_auc"])), 4),
            "PR-AUC": round(float(np.mean(ms["pr_auc"])), 4),
            "PR-AUC_Seed_Std": round(float(np.mean(seed_pr_stds[name])), 4),
            "PR-AUC_Window_95CI_Low": ci[0],
            "PR-AUC_Window_95CI_High": ci[1],
            "MCC@0.20%": round(float(np.mean(ms["mcc"])), 4),
            "Brier_Calibrated": round(float(np.mean(ms["brier_cal"])), 6),
            "Brier_Raw": round(float(np.mean(ms["brier_raw"])), 6),
            "Batch_Latency_ms_per_txn": round(float(np.mean(ms["batch_latency_ms"])), 5),
            "Single_Txn_Latency_ms": round(float(np.mean(ms["single_latency_ms"])), 4),
        })
    bench_df = pd.DataFrame(rows)
    bench_df.to_csv("artifacts/benchmark_results.csv", index=False)
    print("\n=== BENCHMARK RESULTS (10 Expanding OOT Windows, Multi-Seed, Isotonic-Calibrated) ===")
    print(bench_df.to_string(index=False))

    # 2. Friedman Omnibus Tests (5-model df=4, and 4-model excluding SVM df=3)
    pr_arrays = [metrics_store[m]["pr_auc"] for m in model_names]
    f_stat, f_pval = friedmanchisquare(*pr_arrays)
    four_names = [m for m in model_names if m != "SVM (RBF)"]
    f_stat_4, f_pval_4 = friedmanchisquare(*[metrics_store[m]["pr_auc"] for m in four_names])
    print(f"\n=== FRIEDMAN OMNIBUS (PR-AUC, 10 Windows) ===")
    print(f"5-model (all, df=4):       chi2={f_stat:.4f}, p={f_pval:.6f}")
    print(f"4-model (no SVM, df=3):    chi2={f_stat_4:.4f}, p={f_pval_4:.6f}")
    import json as _json
    Path("artifacts/friedman_summary.json").write_text(_json.dumps({
        "friedman_5_models": {"chi2": round(float(f_stat), 4), "p_value": round(float(f_pval), 6), "df": 4},
        "friedman_4_models_no_svm": {"chi2": round(float(f_stat_4), 4), "p_value": round(float(f_pval_4), 6), "df": 3},
        "per_window_pr_auc": {m: [round(float(x), 6) for x in metrics_store[m]["pr_auc"]] for m in model_names},
    }, indent=2))

    # 3. Pairwise Wilcoxon vs XGBoost + Holm-Bonferroni + Cliff's Delta
    xgb_pr = np.asarray(metrics_store["XGBoost"]["pr_auc"])
    comparisons = []
    for other in [m for m in model_names if m != "XGBoost"]:
        other_pr = np.asarray(metrics_store[other]["pr_auc"])
        w_stat, p_val = wilcoxon(xgb_pr, other_pr, zero_method="wilcox")
        delta = cliffs_delta(xgb_pr, other_pr)
        comparisons.append({
            "Comparison": f"XGBoost vs {other}",
            "XGBoost_Mean_PR_AUC": round(float(np.mean(xgb_pr)), 4),
            "Other_Mean_PR_AUC": round(float(np.mean(other_pr)), 4),
            "Wilcoxon_Stat": float(w_stat),
            "raw_p_value": float(p_val),
            "Cliffs_Delta": round(delta, 4),
        })

    comparisons.sort(key=lambda r: r["raw_p_value"])
    m_tests = len(comparisons)
    running_max = 0.0
    for i, row in enumerate(comparisons):
        factor = m_tests - i
        adj_p = min(1.0, max(running_max, row["raw_p_value"] * factor))
        running_max = adj_p
        row["holm_factor"] = factor
        row["adjusted_p_value"] = round(adj_p, 6)
        row["Significant (alpha=0.05)"] = bool(adj_p < 0.05)

    stats_df = pd.DataFrame(comparisons)
    stats_df.to_csv("artifacts/statistical_tests.csv", index=False)
    print("\n=== PAIRWISE WILCOXON + HOLM + CLIFF'S DELTA (PR-AUC) ===")
    print(stats_df.to_string(index=False))

    # 4. Save unified statistical_summary.json
    summary = {
        "protocol": f"{N_WINDOWS} expanding chronological OOT windows ([50%, 100%] of deduplicated 29D ULB) with 10% pre-window Isotonic calibration",
        "seeds_stochastic_models": SEEDS,
        "stochastic_models": sorted(STOCHASTIC_MODELS),
        "alert_budget_rate": BUDGET_RATE,
        "ci_method": "2,000-replicate bootstrap over the 10 OOT window means (window-level CI, not transaction-level)",
        "friedman_omnibus": {
            "metric": "PR-AUC (window-level seed mean)",
            "models": model_names,
            "df": len(model_names) - 1,
            "n_windows": N_WINDOWS,
            "mean_pr_auc": {m: round(float(np.mean(metrics_store[m]["pr_auc"])), 4) for m in model_names},
            "window_ci_95_pr_auc": {m: bootstrap_ci(metrics_store[m]["pr_auc"]) for m in model_names},
            "friedman_chi2": round(float(f_stat), 4),
            "p_value": float(f"{f_pval:.3e}"),
            "significant_alpha_0_05": bool(f_pval < 0.05),
        },
        "methodological_notes": [
            "Temporal expanding OOT windows are used instead of random k-fold CV to prevent future-to-past fraud burst leakage.",
            "Stochastic models (Random Forest, XGBoost, MLP) are averaged across 5 seeds per window before Friedman/Wilcoxon testing to avoid inflating sample size with correlated seeds.",
            "All 5 models receive post-hoc Isotonic Regression calibration on the preceding 10% chronological split prior to Brier Score comparison.",
            f"SVM (RBF) trained on all window frauds + {SVM_MAX_LEGIT:,} randomly sampled legitimate transactions for O(N^2) tractability.",
            "Both batch-amortized latency (full window predict_proba) and single-transaction latency (200 sequential single-row calls) are reported.",
        ],
    }
    with open("artifacts/statistical_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== FRIEDMAN OMNIBUS (5 MODELS, df=4) ===")
    print(json.dumps(summary["friedman_omnibus"], indent=2))


if __name__ == "__main__":
    main()
