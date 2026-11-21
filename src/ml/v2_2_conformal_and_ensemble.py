"""
RiskPulse v2.2 — Task 4: Mondrian Split-Conformal Prediction & 5-Seed Ensemble Uncertainty
Evaluates on the 3 disjoint chronological OOT windows ([60%, 73%], [73%, 86%], [86%, 100%])
of the deduplicated 29D ULB dataset.
Outputs:
  - artifacts/conformal.json
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
import xgboost as xgb

warnings.filterwarnings("ignore")

SEEDS = [7, 21, 42, 84, 128]
ALPHA_LEGIT = 0.005  # 99.5% target coverage on class 0 (keeps review rate operational)
ALPHA_FRAUD = 0.150  # 85.0% target coverage on class 1 (fraud)


def conformal_quantile(scores, alpha):
    n = len(scores)
    if n == 0:
        return 1.0
    level = min(1.0, np.ceil((n + 1) * (1.0 - alpha)) / n)
    return float(np.quantile(scores, level, method="higher"))


def fit_calibrated_xgb(X_tr, y_tr, X_cal, y_cal, seed):
    spw = (y_tr == 0).sum() / max((y_tr == 1).sum(), 1)
    model = xgb.XGBClassifier(
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
    model.fit(X_tr, y_tr)
    raw_cal = model.predict_proba(X_cal)[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip").fit(raw_cal, y_cal)
    return model, iso


def main():
    Path("artifacts").mkdir(exist_ok=True)
    df = pd.read_csv("data/creditcard.csv").drop_duplicates().sort_values("Time").reset_index(drop=True)
    feature_cols = ["Amount"] + [f"V{i}" for i in range(1, 29)]
    X_all = df[feature_cols].values
    y_all = df["Class"].values
    n = len(df)

    # Disjoint OOT windows with preceding 10% calibration block
    windows = [
        ("W1 [60%-73%]", int(0.50 * n), int(0.60 * n), int(0.73 * n)),
        ("W2 [73%-86%]", int(0.63 * n), int(0.73 * n), int(0.86 * n)),
        ("W3 [86%-100%]", int(0.76 * n), int(0.86 * n), n),
    ]

    window_results = []
    pooled_y, pooled_in_set, pooled_review, pooled_std = [], [], [], []

    print("Running Mondrian Split-Conformal + 5-Seed Ensemble Uncertainty across 3 OOT windows...")

    for name, tr_end, cal_end, te_end in windows:
        X_tr, y_tr = X_all[:tr_end], y_all[:tr_end]
        X_cal, y_cal = X_all[tr_end:cal_end], y_all[tr_end:cal_end]
        X_te, y_te = X_all[cal_end:te_end], y_all[cal_end:te_end]

        # 5-seed ensemble predictions (calibrated)
        cal_probs_seeds = []
        te_probs_seeds = []
        for s in SEEDS:
            model, iso = fit_calibrated_xgb(X_tr, y_tr, X_cal, y_cal, seed=s)
            cal_probs_seeds.append(iso.predict(model.predict_proba(X_cal)[:, 1]))
            te_probs_seeds.append(iso.predict(model.predict_proba(X_te)[:, 1]))

        cal_probs_seeds = np.vstack(cal_probs_seeds)
        te_probs_seeds = np.vstack(te_probs_seeds)

        p_cal = cal_probs_seeds.mean(axis=0)
        p_te = te_probs_seeds.mean(axis=0)
        epistemic_std = te_probs_seeds.std(axis=0)

        # Mondrian nonconformity scores: s_i = 1 - p(true class)
        s_cal_0 = 1.0 - (1.0 - p_cal[y_cal == 0])  # = p_cal for class 0
        s_cal_1 = 1.0 - p_cal[y_cal == 1]

        q0 = conformal_quantile(s_cal_0, ALPHA_LEGIT)
        q1 = conformal_quantile(s_cal_1, ALPHA_FRAUD)

        # Prediction sets on test window
        include_0 = p_te <= q0
        include_1 = (1.0 - p_te) <= q1
        set_size = include_0.astype(int) + include_1.astype(int)

        # Ambiguous (size == 2) or empty/OOD (size == 0) routed to Human Review
        review_mask = set_size != 1
        in_set = np.where(y_te == 1, include_1, include_0)

        cov_overall = float(np.mean(in_set))
        cov_legit = float(np.mean(in_set[y_te == 0]))
        cov_fraud = float(np.mean(in_set[y_te == 1])) if (y_te == 1).sum() > 0 else 0.0
        review_rate = float(np.mean(review_mask))

        # Ensemble disagreement breakdown
        std_legit = float(np.mean(epistemic_std[y_te == 0]))
        std_fraud = float(np.mean(epistemic_std[y_te == 1]))
        std_review = float(np.mean(epistemic_std[review_mask])) if review_mask.sum() > 0 else 0.0

        window_results.append({
            "window": name,
            "n_test": int(len(y_te)),
            "n_frauds": int(y_te.sum()),
            "q_legit": round(q0, 5),
            "q_fraud": round(q1, 5),
            "empirical_coverage_overall": round(cov_overall, 4),
            "empirical_coverage_legit": round(cov_legit, 4),
            "empirical_coverage_fraud": round(cov_fraud, 4),
            "human_review_count": int(review_mask.sum()),
            "human_review_rate_pct": round(review_rate * 100.0, 3),
            "ensemble_std_legit": round(std_legit, 5),
            "ensemble_std_fraud": round(std_fraud, 5),
            "ensemble_std_review_cases": round(std_review, 5),
        })

        pooled_y.append(y_te)
        pooled_in_set.append(in_set)
        pooled_review.append(review_mask)
        pooled_std.append(epistemic_std)

        print(
            f"  {name} | Frauds: {int(y_te.sum()):3d} | Fraud Cov: {cov_fraud*100:5.1f}% | "
            f"Legit Cov: {cov_legit*100:6.2f}% | Review Rate: {review_rate*100:5.2f}% | "
            f"Ensemble Std (Review vs Legit): {std_review:.4f} vs {std_legit:.5f}"
        )

    pooled_y = np.concatenate(pooled_y)
    pooled_in_set = np.concatenate(pooled_in_set)
    pooled_review = np.concatenate(pooled_review)
    pooled_std = np.concatenate(pooled_std)

    output = {
        "method": "Mondrian (class-conditional) split-conformal prediction + 5-seed calibrated XGBoost ensemble",
        "nonconformity_score": "1 - p_cal(true_class)",
        "seeds": SEEDS,
        "target_coverage": {
            "legit_class_0": 1.0 - ALPHA_LEGIT,
            "fraud_class_1": 1.0 - ALPHA_FRAUD,
        },
        "pooled_oot": {
            "total_txns": int(len(pooled_y)),
            "total_frauds": int(pooled_y.sum()),
            "empirical_coverage_overall": round(float(np.mean(pooled_in_set)), 4),
            "empirical_coverage_legit": round(float(np.mean(pooled_in_set[pooled_y == 0])), 4),
            "empirical_coverage_fraud": round(float(np.mean(pooled_in_set[pooled_y == 1])), 4),
            "total_human_reviews": int(pooled_review.sum()),
            "human_review_rate_pct": round(float(np.mean(pooled_review) * 100.0), 3),
            "ensemble_std_legit": round(float(np.mean(pooled_std[pooled_y == 0])), 5),
            "ensemble_std_fraud": round(float(np.mean(pooled_std[pooled_y == 1])), 5),
            "ensemble_std_review_cases": round(float(np.mean(pooled_std[pooled_review])), 5),
        },
        "windows": window_results,
    }

    with open("artifacts/conformal.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n=== POOLED MONDRIAN CONFORMAL + ENSEMBLE SUMMARY ===")
    print(json.dumps(output["pooled_oot"], indent=2))


if __name__ == "__main__":
    main()
