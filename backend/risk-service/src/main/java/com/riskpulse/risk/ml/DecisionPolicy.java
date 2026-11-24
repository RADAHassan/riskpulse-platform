package com.riskpulse.risk.ml;

import com.riskpulse.risk.domain.Decision;
import java.util.List;

/**
 * Final decision rule of the platform (independent of — and stricter than — ml-serving).
 *
 * <ul>
 *   <li>No model answer (timeout, circuit open, error) → {@code HUMAN_REVIEW}. A failure never approves.</li>
 *   <li>{@code DECLINE} needs a calibrated high probability <b>and</b> a singleton conformal set {@code {FRAUD}}
 *       <b>and</b> low uncertainty. An uncertain prediction is never auto-declined: it goes to a human.</li>
 *   <li>Unknown decision strings are treated as {@code HUMAN_REVIEW}.</li>
 * </ul>
 */
public final class DecisionPolicy {

    public record Outcome(Decision decision, String reason, boolean fallback) {
    }

    private final double uncertaintyThreshold;

    public DecisionPolicy(double uncertaintyThreshold) {
        this.uncertaintyThreshold = uncertaintyThreshold;
    }

    public Outcome decide(MlResult ml) {
        if (ml == null) {
            return new Outcome(Decision.HUMAN_REVIEW, "ml_serving_unavailable_fallback", true);
        }
        Decision proposed = parse(ml.decision());
        if (proposed == null) {
            return new Outcome(Decision.HUMAN_REVIEW, "unknown_model_decision", false);
        }
        if (proposed == Decision.DECLINE) {
            boolean singletonFraud = ml.conformalSet() != null && List.of("FRAUD").equals(ml.conformalSet());
            boolean uncertain = ml.uncertainty() >= uncertaintyThreshold || !singletonFraud;
            if (uncertain) {
                return new Outcome(Decision.HUMAN_REVIEW, "uncertain_prediction_not_auto_declined", false);
            }
            return new Outcome(Decision.DECLINE, "high_probability_confident_fraud", false);
        }
        if (proposed == Decision.HUMAN_REVIEW) {
            return new Outcome(Decision.HUMAN_REVIEW, reason(ml, "model_requested_review"), false);
        }
        if (ml.humanReview()) {
            return new Outcome(Decision.HUMAN_REVIEW, reason(ml, "review_router_top_score"), false);
        }
        return new Outcome(Decision.APPROVE, "low_risk", false);
    }

    private static String reason(MlResult ml, String fallback) {
        String r = ml.reviewReason();
        return r == null || r.isBlank() || "none".equals(r) ? fallback : r;
    }

    private static Decision parse(String value) {
        try {
            return value == null ? null : Decision.valueOf(value);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
