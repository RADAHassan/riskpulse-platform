package com.riskpulse.transaction;

import com.riskpulse.common.audit.AuditClient;
import com.riskpulse.common.audit.AuditEvent;
import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.web.ApiException;
import io.micrometer.core.instrument.MeterRegistry;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TransactionService {

    private final TransactionRepository repository;
    private final RiskClient risk;
    private final TransactionTemplate tx;
    private final AuditClient audit;
    private final MeterRegistry meters;

    public TransactionService(TransactionRepository repository, RiskClient risk, TransactionTemplate tx,
                              AuditClient audit, MeterRegistry meters) {
        this.repository = repository;
        this.risk = risk;
        this.tx = tx;
        this.audit = audit;
        this.meters = meters;
    }

    /** Persist → ask risk-service → store the decision. An unreachable risk-service never approves. */
    public Transaction submit(UUID customerId, BigDecimal amount, String currency, String merchant, List<Double> features,
                              boolean simulated, AuthenticatedUser caller) {
        double[] raw = features.stream().mapToDouble(Double::doubleValue).toArray();
        Transaction created = tx.execute(s -> repository.save(new Transaction(customerId, amount, currency, merchant, raw,
                simulated)));

        var answer = risk.assess(created.getId(), customerId, amount, features);
        Transaction decided = tx.execute(s -> {
            Transaction t = repository.findById(created.getId()).orElseThrow();
            if (answer.isPresent()) {
                var a = answer.get();
                t.applyDecision(a.decision(), a.reason(), a.probability(), a.uncertainty(), a.modelVersion(), false);
            } else {
                t.applyDecision("HUMAN_REVIEW", "risk_service_unavailable", null, null, null, true);
            }
            return t;
        });
        meters.counter("riskpulse.transactions", "decision", decided.getDecision()).increment();
        audit.record(AuditEvent.of(String.valueOf(caller.username()), caller.role(), "TRANSACTION_SUBMITTED", "Transaction",
                decided.getId().toString()).withDecision(decided.getDecision(), decided.getModelVersion())
                .withDetails(Map.of("status", decided.getStatus().name(), "simulated", decided.isSimulated(),
                        "riskUnavailable", answer.isEmpty())));
        return decided;
    }

    public Transaction applyReviewOutcome(UUID id, String decision) {
        if (!"APPROVE".equals(decision) && !"DECLINE".equals(decision)) {
            throw ApiException.badRequest("decision must be APPROVE or DECLINE");
        }
        return tx.execute(s -> {
            Transaction t = repository.findById(id).orElseThrow(() -> ApiException.notFound("Transaction"));
            t.applyReviewOutcome(decision);
            return t;
        });
    }
}
