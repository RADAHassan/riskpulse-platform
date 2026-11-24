package com.riskpulse.risk.web;

import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.web.ApiException;
import com.riskpulse.risk.domain.Decision;
import com.riskpulse.risk.domain.RiskAssessment;
import com.riskpulse.risk.domain.RiskAssessmentRepository;
import com.riskpulse.risk.ml.MlServingClient;
import com.riskpulse.risk.service.RiskService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RiskController {

    public record AssessRequest(
            @NotNull UUID transactionId,
            @NotNull UUID customerId,
            @NotNull @DecimalMin("0.00") @DecimalMax("1000000000") BigDecimal amount,
            @NotNull @Size(min = 28, max = 28) List<Double> features) {

        @AssertTrue(message = "features must be finite numbers")
        boolean isFeaturesFinite() {
            return features == null || features.stream().allMatch(f -> f != null && Double.isFinite(f));
        }
    }

    public record AssessmentResponse(UUID transactionId, Decision decision, String reason, Double probability,
                                     Double uncertainty, String modelVersion, String registryVersion,
                                     String conformalSet, boolean fallback, UUID reviewId, Instant createdAt) {
        static AssessmentResponse of(RiskAssessment a, UUID reviewId) {
            return new AssessmentResponse(a.getTransactionId(), a.getDecision(), a.getReason(), a.getProbability(),
                    a.getUncertainty(), a.getModelVersion(), a.getRegistryVersion(), a.getConformalSet(), a.isFallback(),
                    reviewId, a.getCreatedAt());
        }
    }

    private final RiskService service;
    private final RiskAssessmentRepository assessments;
    private final MlServingClient ml;

    public RiskController(RiskService service, RiskAssessmentRepository assessments, MlServingClient ml) {
        this.service = service;
        this.assessments = assessments;
        this.ml = ml;
    }

    /**
     * Internal (transaction-service → risk-service): JWT + service key. A CUSTOMER token may only request an
     * assessment for its own customer (defence in depth on top of the transaction-service check).
     */
    @PostMapping("/internal/risk/assess")
    public AssessmentResponse assess(@Valid @RequestBody AssessRequest request, Authentication auth) {
        AuthenticatedUser caller = AuthenticatedUser.from(auth);
        if (!caller.canAccessCustomer(request.customerId())) {
            throw ApiException.forbidden();
        }
        RiskService.Assessment result = service.assess(request.transactionId(), request.customerId(), request.amount(),
                request.features(), String.valueOf(caller.username()), caller.role());
        return AssessmentResponse.of(result.assessment(), result.reviewId());
    }

    @GetMapping("/api/risk/assessments/{transactionId}")
    public AssessmentResponse get(@PathVariable UUID transactionId, Authentication auth) {
        RiskAssessment a = assessments.findByTransactionId(transactionId)
                .orElseThrow(() -> ApiException.notFound("Assessment"));
        if (!AuthenticatedUser.from(auth).canAccessCustomer(a.getCustomerId())) {
            throw ApiException.forbidden();
        }
        return AssessmentResponse.of(a, null);
    }

    @GetMapping("/api/risk/stats")
    @PreAuthorize("hasAnyRole('ADMIN','ANALYST')")
    public Map<String, Object> stats() {
        return service.stats(ml.circuitState().name());
    }
}
