import numpy as np
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    f1_score,
    brier_score_loss,
    matthews_corrcoef
)

def compute_ece(y_true, y_prob, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        mask = (y_prob >= bin_lower) & (y_prob <= bin_upper) if i == n_bins - 1 else (y_prob >= bin_lower) & (y_prob < bin_upper)
        bin_size = np.sum(mask)
        if bin_size > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(y_prob[mask])
            ece += (bin_size / n) * np.abs(bin_acc - bin_conf)
    return float(ece)

def evaluate_predictions(y_true, y_prob, threshold=0.5):
    preds = (y_prob >= threshold).astype(int)
    return {
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "f1_score": float(f1_score(y_true, preds)),
        "mcc": float(matthews_corrcoef(y_true, preds)),
        "brier_score": float(brier_score_loss(y_true, y_prob)),
        "ece": compute_ece(y_true, y_prob)
    }
