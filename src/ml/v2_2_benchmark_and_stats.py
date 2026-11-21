"""
RiskPulse v2.2 — Unified 5-Model Temporal Benchmark & Statistical Validation
Covers Tasks 2 & 3 on 10 expanding chronological OOT windows (deduplicated 29D ULB).
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

SEED = 42
N_WINDOWS = 10
TRAIN_START_FRAC = 0.50  # First 50% is initial training; remaining 50% split into 10 OOT blocks
BUDGET_RATE = 0.0020     # 0.20% fixed alert budget
SVM_MAX_LEGIT = 15000    # Subsample cap for O(N^2) RBF-SVM training tractability


def cliffs_delta(x, y):
    x, y = np.asarray(x), np.asarray(y)
    diff = x[:, None] - y[None, :]
    return float((np.sum(diff > 0) - np.sum(diff < 0)) / (len(x) * len(y)))


def bootstrap_ci(values, n_boot=2000, seed=SEED):
    rng = np.random.default_rng(seed)
    arr = np.asarray(values)
    means = [np.mean(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)]
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]


def build_models(spw):
    return {
        "Logistic Regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=300, class_weight="balanced", random_state=SEED, n_jobs=-1),
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=150, max_depth=12, class_weight="balanced", random_state=SEED, n_jobs=-1
        ),
        "XGBoost": xgb.XGBClassifier(
            n_estimators=220,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=spw,
            eval_metric="logloss",
            random_state=SEED,
            n_jobs=-1,
        ),
        "SVM (RBF)": make_pipeline(
            StandardScaler(),
            SVC(kernel="rbf", C=1.0, class_weight="balanced", probability=True, random_state=SEED),
        ),
        "MLP": make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(64, 32),
                max_iter=30,
                early_stopping=True,
                random_state=SEED,
            ),
        ),
    }


def main():
    Path("artifacts").mkdir(exist_ok=True)
    df = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
    feature_cols = ["Amount"] + [f"V{i}" for i in range(1, 29)]
    X_all = df[feature_cols].values
    y_all = df["Class"].values
    n = len(df)

    # 10 expanding temporal OOT blocks across [50%, 100%]
    split_points = np.linspace(int(n * TRAIN_START_FRAC), n, N_WINDOWS + 1, dtype=int)
    model_names = ["Logistic Regression", "Random Forest", "XGBoost", "SVM (RBF)", "MLP"]
    metrics_store = {
        m: {k: [] for k in ["precision", "recall", "f1", "roc_auc", "pr_auc", "mcc", "brier", "latency_ms"]}
        for m in model_names
    }

    rng = np.random.default_rng(SEED)
    print(f"Running 5-model benchmark across {N_WINDOWS} expanding temporal OOT windows (N={n:,})...")

    for w in range(N_WINDOWS):
        tr_end = split_points[w]
        te_end = split_points[w + 1]
        X_tr, y_tr = X_all[:tr_end], y_all[:tr_end]
        X_te, y_te = X_all[tr_end:te_end], y_all[tr_end:te_end]

        n_pos_te = int(y_te.sum())
        spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
        models = build_models(spw)
        k_alerts = max(1, int(round(len(y_te) * BUDGET_RATE)))

        # Prepare stratified subsample for SVM (RBF)
        fraud_idx = np.where(y_tr == 1)[0]
        legit_idx = np.where(y_tr == 0)[0]
        sampled_legit = rng.choice(legit_idx, size=min(SVM_MAX_LEGIT, len(legit_idx)), replace=False)
        svm_idx = np.concatenate([fraud_idx, sampled_legit])
        X_tr_svm, y_tr_svm = X_tr[svm_idx], y_tr[svm_idx]

        print(f"  Window {w+1:02d}/{N_WINDOWS} | Train: {len(y_tr):,} | Test: {len(y_te):,} (frauds={n_pos_te})")

        for name, model in models.items():
            if name == "SVM (RBF)":
                model.fit(X_tr_svm, y_tr_svm)
            else:
                model.fit(X_tr, y_tr)

            t0 = time.perf_counter()
            probs = model.predict_proba(X_te)[:, 1]
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latency_per_txn_ms = elapsed_ms / len(X_te)

            # Top-0.20% fixed budget binary predictions
            top_idx = np.argsort(probs)[::-1][:k_alerts]
            preds = np.zeros(len(y_te), dtype=int)
            preds[top_idx] = 1

            metrics_store[name]["precision"].append(precision_score(y_te, preds, zero_division=0))
            metrics_store[name]["recall"].append(recall_score(y_te, preds, zero_division=0))
            metrics_store[name]["f1"].append(f1_score(y_te, preds, zero_division=0))
            metrics_store[name]["roc_auc"].append(roc_auc_score(y_te, probs))
            metrics_store[name]["pr_auc"].append(average_precision_score(y_te, probs))
            metrics_store[name]["mcc"].append(matthews_corrcoef(y_te, preds))
            metrics_store[name]["brier"].append(brier_score_loss(y_te, probs))
            metrics_store[name]["latency_ms"].append(latency_per_txn_ms)

    # 1. Save benchmark_results.csv (mean across 10 expanding OOT windows)
    rows = []
    for name in model_names:
        ms = metrics_store[name]
        rows.append({
            "Model": name,
            "Precision@0.20%": round(float(np.mean(ms["precision"])), 4),
            "Recall@0.20%": round(float(np.mean(ms["recall"])), 4),
            "F1@0.20%": round(float(np.mean(ms["f1"])), 4),
            "ROC-AUC": round(float(np.mean(ms["roc_auc"])), 4),
            "PR-AUC": round(float(np.mean(ms["pr_auc"])), 4),
            "PR-AUC_95CI_Low": bootstrap_ci(ms["pr_auc"])[0],
            "PR-AUC_95CI_High": bootstrap_ci(ms["pr_auc"])[1],
            "MCC@0.20%": round(float(np.mean(ms["mcc"])), 4),
            "Brier Score": round(float(np.mean(ms["brier"])), 6),
            "Latency (ms/txn)": round(float(np.mean(ms["latency_ms"])), 5),
        })
    bench_df = pd.DataFrame(rows)
    bench_df.to_csv("artifacts/benchmark_results.csv", index=False)
    print("\n=== BENCHMARK RESULTS (10 Expanding Temporal OOT Windows) ===")
    print(bench_df.to_string(index=False))

    # 2. Friedman Omnibus Test (all 5 models, df = 4)
    pr_arrays = [metrics_store[m]["pr_auc"] for m in model_names]
    f_stat, f_pval = friedmanchisquare(*pr_arrays)

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

    # Holm-Bonferroni correction
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
        "protocol": f"{N_WINDOWS} expanding chronological OOT windows ([50%, 100%] of deduplicated 29D ULB)",
        "alert_budget_rate": BUDGET_RATE,
        "friedman_omnibus": {
            "metric": "PR-AUC",
            "models": model_names,
            "df": len(model_names) - 1,
            "n_windows": N_WINDOWS,
            "mean_pr_auc": {m: round(float(np.mean(metrics_store[m]["pr_auc"])), 4) for m in model_names},
            "ci_95_pr_auc": {m: bootstrap_ci(metrics_store[m]["pr_auc"]) for m in model_names},
            "friedman_chi2": round(float(f_stat), 4),
            "p_value": float(f"{f_pval:.3e}"),
            "significant_alpha_0_05": bool(f_pval < 0.05),
        },
        "methodological_notes": [
            "All 5 models evaluated on identical expanding chronological OOT windows (no random-split leakage).",
            f"SVM (RBF) trained on all window frauds + {SVM_MAX_LEGIT:,} randomly sampled legitimate transactions for O(N^2) tractability.",
            "Precision, Recall, F1, and MCC are computed at the fixed 0.20% operational alert budget per window.",
        ],
    }
    with open("artifacts/statistical_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== FRIEDMAN OMNIBUS (5 MODELS, df=4) ===")
    print(json.dumps(summary["friedman_omnibus"], indent=2))


if __name__ == "__main__":
    main()
