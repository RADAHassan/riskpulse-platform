import json
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, matthews_corrcoef

def run_test_bootstrapping(n_bootstraps=1000, seed=42):
    print("[Stats] Running 1,000 empirical bootstrap iterations on test split...")
    data = np.load("artifacts/data_splits.npz")
    y_test = data["y_test"]
    
    base_xgb = joblib.load("artifacts/base_xgb.joblib")
    calibrator = joblib.load("artifacts/iso_calibrator.joblib")
    
    raw_p1 = base_xgb.predict_proba(data["X_test"])[:, 1]
    cal_p1 = calibrator.predict(raw_p1)
    preds = (cal_p1 >= 0.5).astype(int)

    rng = np.random.default_rng(seed)
    n = len(y_test)
    pr_aucs, f1s, mccs = [], [], []

    for _ in range(n_bootstraps):
        idx = rng.choice(n, size=n, replace=True)
        if len(np.unique(y_test[idx])) < 2:
            continue
        pr_aucs.append(average_precision_score(y_test[idx], cal_p1[idx]))
        f1s.append(f1_score(y_test[idx], preds[idx]))
        mccs.append(matthews_corrcoef(y_test[idx], preds[idx]))

    results = {
        "pr_auc": {
            "mean": round(float(np.mean(pr_aucs)), 4),
            "ci_95": [round(float(np.percentile(pr_aucs, 2.5)), 4), round(float(np.percentile(pr_aucs, 97.5)), 4)]
        },
        "f1_score": {
            "mean": round(float(np.mean(f1s)), 4),
            "ci_95": [round(float(np.percentile(f1s, 2.5)), 4), round(float(np.percentile(f1s, 97.5)), 4)]
        },
        "mcc": {
            "mean": round(float(np.mean(mccs)), 4),
            "ci_95": [round(float(np.percentile(mccs, 2.5)), 4), round(float(np.percentile(mccs, 97.5)), 4)]
        },
        "methodological_caveats": [
            "Nadeau-Bengio (2003): Repeated CV folds violate independence assumptions, so CV p-values are inherently optimistic.",
            "Test set contains 74 positive cases; bootstrap CIs account for finite sample variance in positive class prevalence."
        ]
    }

    with open("artifacts/statistical_summary.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"      PR-AUC 95% CI: {results['pr_auc']['ci_95']}")
    print(f"      F1-Score 95% CI: {results['f1_score']['ci_95']}")
    print(f"      MCC 95% CI: {results['mcc']['ci_95']}")
    print("      Saved to artifacts/statistical_summary.json")

if __name__ == "__main__":
    run_test_bootstrapping()
