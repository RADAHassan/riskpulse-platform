import numpy as np
from sklearn.isotonic import IsotonicRegression
from src.config import REVIEW_LOWER_BOUND, REVIEW_UPPER_BOUND

class OperationalCalibrator:
    def __init__(self, lower_bound=REVIEW_LOWER_BOUND, upper_bound=REVIEW_UPPER_BOUND):
        self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound

    def fit(self, raw_probs, y_true):
        self.calibrator.fit(raw_probs, y_true)
        return self

    def predict_proba(self, raw_probs):
        return np.clip(self.calibrator.predict(raw_probs), 0.0, 1.0)

    def route_transactions(self, cal_probs, y_true=None):
        preds = (cal_probs >= 0.5).astype(int)
        is_review = (cal_probs >= self.lower_bound) & (cal_probs <= self.upper_bound)
        
        metrics = {
            "total_txns": len(cal_probs),
            "total_reviews": int(np.sum(is_review)),
            "human_review_rate_pct": float(np.mean(is_review) * 100.0)
        }
        
        if y_true is not None:
            total_frauds = int(np.sum(y_true == 1))
            intercepted = int(np.sum(is_review[y_test_mask := (y_true == 1)] | (preds[y_test_mask] == 1)))
            metrics["total_frauds"] = total_frauds
            metrics["frauds_intercepted"] = intercepted
            metrics["fraud_coverage_pct"] = float(intercepted / total_frauds * 100.0) if total_frauds > 0 else 0.0

        return preds, is_review, metrics
