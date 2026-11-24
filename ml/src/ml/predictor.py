import json
import logging
import numpy as np
from collections import deque
from pathlib import Path

from src.ml.bundle_io import load_bundle

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_artifact(path: str | Path) -> Path:
    p = Path(path)
    if p.exists() or p.is_absolute():
        return p
    candidate = _REPO_ROOT / p
    return candidate if candidate.exists() else p


class RiskPulseMLPredictor:
    """Canonical 29D ML inference interface for the RiskPulse backend."""

    def __init__(
        self,
        bundle_path: str = "artifacts/riskpulse_29d_bundle.joblib",
        conformal_path: str = "artifacts/conformal.json",
        investigation_cost: float = 25.0,
        uncertainty_review_threshold: float = 0.25,
        uncertainty_downgrade_only: bool = True,
        use_uncertainty_routing: bool = True,
    ):
        bundle = load_bundle(_resolve_artifact(bundle_path))
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
        self.uncertainty_review_threshold = float(uncertainty_review_threshold)
        self.uncertainty_downgrade_only = bool(uncertainty_downgrade_only)
        self.use_uncertainty_routing = bool(use_uncertainty_routing)
        self.buffer_policy = "quarantine_guard_only"
        self.queue_policy = "two_tier_capped_human"
        self.max_human_alerts = max(1, int(self.W * self.target_rate))
        self.score_buffer = deque(bundle["init_raw_scores"][-self.W :], maxlen=self.W)
        self.human_alert_window = deque(maxlen=self.W)
        self.human_alerts_in_window = 0
        self.live_mse_buffer = deque(maxlen=self.W)

        self.q_legit = 0.23462
        self.q_fraud = 0.95251
        self.review_threshold = 0.322124
        c_path = _resolve_artifact(conformal_path)
        loaded_quantiles = False
        if c_path.exists():
            c_data = json.loads(c_path.read_text())
            sq = c_data.get("serving_quantiles", {})
            if "q_legit" in sq and "q_fraud" in sq:
                self.q_legit = float(sq["q_legit"])
                self.q_fraud = float(sq["q_fraud"])
                loaded_quantiles = True
            ap = c_data.get("abstention_policy", {})
            if "thr_review" in ap:
                self.review_threshold = float(ap["thr_review"])
        if not loaded_quantiles:
            logger.warning(
                "Conformal quantiles not found at %s; falling back to served raw-score defaults "
                "(q_legit=%.5f, q_fraud=%.5f).",
                conformal_path,
                self.q_legit,
                self.q_fraud,
            )

    def score_transaction(self, amount: float, v_features: list[float]) -> dict:
        amt_scaled = self.scaler.transform(np.array([[amount]], dtype=float))[0, 0]
        x = np.array([[amt_scaled, *v_features]], dtype=float)

        raw_score = float(self.clf.predict_proba(x)[0, 1])
        cal_prob = float(self.iso.predict([raw_score])[0])
        ae_mse = float(self.ae.transform(x)[0, 0])
        expected_loss = cal_prob * (float(amount) + self.investigation_cost)

        conformal_set = []
        # Mondrian split-conformal sets computed on continuous raw_score (avoids Isotonic step collapse)
        if raw_score <= self.q_legit:
            conformal_set.append("LEGIT")
        if (1.0 - raw_score) <= self.q_fraud:
            conformal_set.append("FRAUD")
        conformal_review_flag = len(conformal_set) != 1

        uncertainty_score = round(2.0 * min(cal_prob, 1.0 - cal_prob), 6)
        high_uncertainty = self.use_uncertainty_routing and (
            uncertainty_score >= self.uncertainty_review_threshold
        )
        conf_route = (
            self.use_uncertainty_routing
            and (not self.uncertainty_downgrade_only)
            and conformal_review_flag
        )
        mid_band_route = (
            self.use_uncertainty_routing
            and (not self.uncertainty_downgrade_only)
            and high_uncertainty
        )

        tau_q = float(np.quantile(self.score_buffer, 1.0 - self.target_rate))
        flag_quantile = raw_score >= tau_q
        flag_guard = cal_prob >= self.guard_prob
        human_cap_reached = self.human_alerts_in_window >= self.max_human_alerts

        # Guard-only mode (default): downgrades uncertain AUTO_DECLINE to MANUAL_REVIEW
        # without displacing quantile-flagged alerts in the capped queue.
        if flag_guard and not high_uncertainty:
            decision = "AUTO_DECLINE"
            queued_human = 0
        elif flag_guard and high_uncertainty:
            if not human_cap_reached:
                decision = "MANUAL_REVIEW"
                queued_human = 1
            else:
                decision = "AUTO_DECLINE"
                queued_human = 0
        else:
            self.score_buffer.append(raw_score)
            if (mid_band_route or conf_route or flag_quantile) and not human_cap_reached:
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
            "human_review": bool(raw_score >= self.review_threshold),
            "review_reason": "top_0.5pct_raw_score" if raw_score >= self.review_threshold else "none",
            # Diagnostic fields (not primary human-review routers)
            "uncertainty_score": uncertainty_score,
            "conformal_set": conformal_set,
            "conformal_review_flag": conformal_review_flag,
        }
