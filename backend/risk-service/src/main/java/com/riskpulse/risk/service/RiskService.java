package com.riskpulse.risk.service;

import com.riskpulse.common.audit.AuditClient;
import com.riskpulse.common.audit.AuditEvent;
import com.riskpulse.common.web.ApiException;
import com.riskpulse.risk.client.DownstreamClients;
import com.riskpulse.risk.domain.Decision;
import com.riskpulse.risk.domain.ReviewCase;
import com.riskpulse.risk.domain.ReviewCaseRepository;
import com.riskpulse.risk.domain.RiskAssessment;
import com.riskpulse.risk.domain.RiskAssessmentRepository;
import com.riskpulse.risk.ml.DecisionPolicy;
import com.riskpulse.risk.ml.MlResult;
import com.riskpulse.risk.ml.MlServingClient;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.math.BigDecimal;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RiskService {

    private static final Logger LOG = LoggerFactory.getLogger(RiskService.class);

    public record Assessment(RiskAssessment assessment, UUID reviewId) {
    }

    private final MlServingClient ml;
    private final DecisionPolicy policy;
    private final RiskAssessmentRepository assessments;
    private final ReviewCaseRepository reviews;
    private final TransactionTemplate tx;
    private final AuditClient audit;
    private final DownstreamClients downstream;
    private final MeterRegistry meters;
    private final Counter fallbacks;

    public RiskService(MlServingClient ml, RiskAssessmentRepository assessments, ReviewCaseRepository reviews,
                       TransactionTemplate tx, AuditClient audit, DownstreamClients downstream, MeterRegistry meters,
                       @Value("${riskpulse.ml.uncertainty-review-threshold:0.25}") double uncertaintyThreshold) {
        this.ml = ml;
        this.policy = new DecisionPolicy(uncertaintyThreshold);
        this.assessments = assessments;
        this.reviews = reviews;
        this.tx = tx;
        this.audit = audit;
        this.downstream = downstream;
        this.meters = meters;
        this.fallbacks = Counter.builder("riskpulse.risk.fallbacks")
                .description("Assessments decided by the HUMAN_REVIEW fallback (ml-serving unavailable)").register(meters);
    }

    /** Scores the transaction, applies the decision policy, persists, audits and notifies. Idempotent per transaction. */
    public Assessment assess(UUID transactionId, UUID customerId, BigDecimal amount, List<Double> features, String actor,
                             String actorRole) {
        Optional<RiskAssessment> existing = assessments.findByTransactionId(transactionId);
        if (existing.isPresent()) {
            return new Assessment(existing.get(),
                    reviews.findByTransactionId(transactionId).map(ReviewCase::getId).orElse(null));
        }

        Optional<MlResult> answer = ml.predict(transactionId, amount, features);
        MlResult result = answer.orElse(null);
        DecisionPolicy.Outcome outcome = policy.decide(result);

        RiskAssessment assessment = new RiskAssessment(transactionId, customerId, amount,
                result == null ? null : result.probability(), result == null ? null : result.uncertainty(),
                result == null ? null : result.prediction(), outcome.decision(), outcome.reason(), outcome.fallback(),
                result == null ? null : result.modelVersion(), result == null ? null : result.registryVersion(),
                result == null || result.conformalSet() == null ? null : String.join(",", result.conformalSet()));

        Assessment saved;
        try {
            saved = tx.execute(status -> {
                RiskAssessment a = assessments.save(assessment);
                ReviewCase review = a.getDecision() == Decision.HUMAN_REVIEW ? reviews.save(new ReviewCase(a)) : null;
                return new Assessment(a, review == null ? null : review.getId());
            });
        } catch (DataIntegrityViolationException race) {
            RiskAssessment winner = assessments.findByTransactionId(transactionId).orElseThrow(() -> race);
            return new Assessment(winner, null);
        }

        meters.counter("riskpulse.risk.assessments", "decision", outcome.decision().name()).increment();
        if (outcome.fallback()) {
            fallbacks.increment();
        }
        record(saved, actor, actorRole);
        notifyIfNeeded(saved);
        return saved;
    }

    public ReviewCase resolve(UUID reviewId, ReviewCase.Status outcome, String note, String actor, String actorRole) {
        if (outcome == ReviewCase.Status.OPEN) {
            throw ApiException.badRequest("Resolution must be APPROVE or REJECT");
        }
        ReviewCase resolved = tx.execute(status -> {
            ReviewCase review = reviews.findById(reviewId).orElseThrow(() -> ApiException.notFound("Review case"));
            if (review.getStatus() != ReviewCase.Status.OPEN) {
                throw ApiException.conflict("Review case already resolved");
            }
            review.resolve(outcome, actor, note);
            return review;
        });
        String finalDecision = outcome == ReviewCase.Status.APPROVED ? "APPROVE" : "DECLINE";
        audit.record(AuditEvent.of(actor, actorRole, "REVIEW_RESOLVED", "Transaction",
                resolved.getTransactionId().toString())
                .withDecision(finalDecision, resolved.getModelVersion())
                .withDetails(Map.of("reviewId", resolved.getId(), "resolution", outcome.name(),
                        "note", note == null ? "" : note)));
        downstream.updateTransactionDecision(resolved.getTransactionId(), finalDecision);
        return resolved;
    }

    public Map<String, Object> stats(String circuitState) {
        Map<Decision, Long> byDecision = new EnumMap<>(Decision.class);
        for (Decision d : Decision.values()) {
            byDecision.put(d, 0L);
        }
        for (Object[] row : assessments.countByDecision()) {
            byDecision.put((Decision) row[0], (Long) row[1]);
        }
        Map<String, Object> out = new HashMap<>();
        out.put("decisions", byDecision);
        out.put("fallbacks", assessments.countByFallbackTrue());
        out.put("openReviews", reviews.countByStatus(ReviewCase.Status.OPEN));
        out.put("mlCircuit", circuitState);
        return out;
    }

    private void record(Assessment saved, String actor, String actorRole) {
        RiskAssessment a = saved.assessment();
        Map<String, Object> details = new HashMap<>();
        details.put("probability", a.getProbability());
        details.put("uncertainty", a.getUncertainty());
        details.put("reason", a.getReason());
        details.put("fallback", a.isFallback());
        details.put("conformalSet", a.getConformalSet());
        details.put("registryVersion", a.getRegistryVersion());
        if (saved.reviewId() != null) {
            details.put("reviewId", saved.reviewId());
        }
        audit.record(AuditEvent.of(actor, actorRole, "RISK_DECISION", "Transaction", a.getTransactionId().toString())
                .withDecision(a.getDecision().name(), a.getModelVersion()).withDetails(details));
    }

    private void notifyIfNeeded(Assessment saved) {
        RiskAssessment a = saved.assessment();
        if (a.getDecision() == Decision.APPROVE) {
            return;
        }
        boolean decline = a.getDecision() == Decision.DECLINE;
        boolean sent = downstream.notify(decline ? "TRANSACTION_DECLINED" : "REVIEW_REQUIRED",
                decline ? "CRITICAL" : "WARNING",
                decline ? "Transaction automatically declined" : "Transaction needs a human review",
                "Amount " + a.getAmount() + " — reason: " + a.getReason(), a.getTransactionId(), a.getCustomerId());
        if (!sent) {
            LOG.warn("Notification for transaction {} could not be delivered", a.getTransactionId());
        }
    }
}
