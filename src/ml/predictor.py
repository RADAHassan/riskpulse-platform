import joblib
import numpy as np
from collections import deque
from pathlib import Path


class RiskPulseMLPredictor:
    """Canonical 29D ML inference interface for the RiskPulse backend."""

    def __init__(
        self,
        bundle_path: str = "artifacts/riskpulse_29d_bundle.joblib",
        investigation_cost: float = 25.0,
    ):
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
        self.investigation_cost = float(cfg.get("investigation_cost", investigation_cost))
        self.buffer_policy = "quarantine_guard_only"
        self.queue_policy = "two_tier_capped_human"
        self.max_human_alerts = max(1, int(self.W * self.target_rate))
        self.score_buffer = deque(bundle["init_raw_scores"][-self.W :], maxlen=self.W)
        self.human_alert_window = deque(maxlen=self.W)
        self.human_alerts_in_window = 0
        self.live_mse_buffer = deque(maxlen=self.W)

    def score_transaction(self, amount: float, v_features: list[float]) -> dict:
        amt_scaled = self.scaler.transform(np.array([[amount]], dtype=float))[0, 0]
        x = np.array([[amt_scaled, *v_features]], dtype=float)

        raw_score = float(self.clf.predict_proba(x)[0, 1])
        cal_prob = float(self.iso.predict([raw_score])[0])
        ae_mse = float(self.ae.transform(x)[0, 0])
        expected_loss = cal_prob * (float(amount) + self.investigation_cost)

        tau_q = float(np.quantile(self.score_buffer, 1.0 - self.target_rate))
        flag_quantile = raw_score >= tau_q
        flag_guard = cal_prob >= self.guard_prob
        human_cap_reached = self.human_alerts_in_window >= self.max_human_alerts

        # Two-tier policy:
        # 1) AUTO_DECLINE (P_cal >= guard) bypasses both the score buffer and human cap.
        # 2) MANUAL_REVIEW is strictly capped at max_human_alerts per rolling window W.
        if flag_guard:
            decision = "AUTO_DECLINE"
            queued_human = 0
        else:
            self.score_buffer.append(raw_score)
            if flag_quantile and not human_cap_reached:
                decision = "MANUAL_REVIEW"
                queued_human = 1
            else:
                decision = "APPROVE"
                queued_human = 0

        if len(self.human_alert_window) == self.W:
            self.human_alerts_in_window -= self.human_alert_window[0]
        self.human_alert_window.append(queued_human)
        self.human_alerts_in_window += queued_human
        self.live_mse_buffer.append(ae_mse)

        return {
            "model_version": self.version,
            "buffer_policy": self.buffer_policy,
            "queue_policy": self.queue_policy,
            "decision": decision,
            "calibrated_probability": round(cal_prob, 6),
            "expected_loss_usd": round(expected_loss, 2),
            "raw_rank_score": round(raw_score, 6),
            "rolling_cutoff": round(tau_q, 6),
            "human_queue_utilization": round(
                self.human_alerts_in_window / self.max_human_alerts, 4
            ),
            "human_cap_reached": human_cap_reached,
            "ae_recon_mse": round(ae_mse, 6),
        }
