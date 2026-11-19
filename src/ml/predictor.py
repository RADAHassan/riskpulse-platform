import joblib
import numpy as np
from collections import deque
from pathlib import Path


class RiskPulseMLPredictor:
    """Canonical 29D ML inference interface for the RiskPulse backend."""

    def __init__(self, bundle_path: str = "artifacts/riskpulse_29d_bundle.joblib"):
        bundle = joblib.load(Path(bundle_path))
        self.version = bundle["model_version"]
        self.scaler = bundle["scaler"]
        self.clf = bundle["xgb_model"]
        self.iso = bundle["isotonic_calibrator"]
        self.ae = bundle["ae_drift_monitor"]
        self.ae_ref_mse = bundle["ae_ref_mse"]
        cfg = bundle["policy_config"]
        self.W = cfg["buffer_size_W"]
        self.target_rate = cfg["target_alert_rate"]
        self.guard_prob = cfg["auto_decline_prob_guard"]
        self.buffer_policy = "quarantine_guard_only"
        self.score_buffer = deque(bundle["init_raw_scores"][-self.W :], maxlen=self.W)
        self.live_mse_buffer = deque(maxlen=self.W)

    def score_transaction(self, amount: float, v_features: list[float]) -> dict:
        amt_scaled = self.scaler.transform(np.array([[amount]], dtype=float))[0, 0]
        x = np.array([[amt_scaled, *v_features]], dtype=float)

        raw_score = float(self.clf.predict_proba(x)[0, 1])
        cal_prob = float(self.iso.predict([raw_score])[0])
        ae_mse = float(self.ae.transform(x)[0, 0])

        tau_q = float(np.quantile(self.score_buffer, 1.0 - self.target_rate))
        flag_quantile = raw_score >= tau_q
        flag_guard = cal_prob >= self.guard_prob

        # Guard-only quarantine: exclude high-confidence bursts (P_cal >= 0.80) from
        # poisoning the rolling buffer while allowing normal 0.2% tail scores to refresh it.
        if not flag_guard:
            self.score_buffer.append(raw_score)
        self.live_mse_buffer.append(ae_mse)

        if flag_guard:
            decision = "AUTO_DECLINE"
        elif flag_quantile:
            decision = "MANUAL_REVIEW"
        else:
            decision = "APPROVE"

        return {
            "model_version": self.version,
            "buffer_policy": self.buffer_policy,
            "decision": decision,
            "calibrated_probability": round(cal_prob, 6),
            "raw_rank_score": round(raw_score, 6),
            "rolling_cutoff": round(tau_q, 6),
            "ae_recon_mse": round(ae_mse, 6),
        }
