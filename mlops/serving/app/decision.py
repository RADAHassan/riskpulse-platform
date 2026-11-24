"""Map the research predictor output to the platform decision contract.

Invariant (also enforced again in risk-service): an uncertain prediction is never auto-declined.
"""

from __future__ import annotations

DECLINE_BLOCKING_UNCERTAINTY = 0.25  # same value as predictor.uncertainty_review_threshold


def to_platform_decision(res: dict, uncertainty_threshold: float = DECLINE_BLOCKING_UNCERTAINTY) -> tuple[str, str]:
    """Return ``(decision, reason)`` for a ``RiskPulseMLPredictor.score_transaction`` result."""
    raw = res["decision"]
    uncertain = res["uncertainty_score"] >= uncertainty_threshold or res["conformal_set"] != ["FRAUD"]

    if raw == "AUTO_DECLINE":
        if uncertain:
            return "HUMAN_REVIEW", "uncertain_prediction_not_auto_declined"
        return "DECLINE", "high_calibrated_probability_and_conformal_fraud"
    if raw == "MANUAL_REVIEW":
        reason = res.get("review_reason")
        return "HUMAN_REVIEW", reason if reason not in (None, "none") else "model_manual_review"
    if res.get("human_review"):
        return "HUMAN_REVIEW", res.get("review_reason", "top_0.5pct_raw_score")
    return "APPROVE", "low_risk"
