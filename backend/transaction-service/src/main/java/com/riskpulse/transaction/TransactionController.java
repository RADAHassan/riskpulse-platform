package com.riskpulse.transaction;

import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.web.ApiException;
import com.riskpulse.common.web.PageResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TransactionController {

    public record TransactionRequest(
            UUID customerId,
            @NotNull @DecimalMin("0.00") @DecimalMax("1000000000") BigDecimal amount,
            @Pattern(regexp = "^[A-Z]{3}$") String currency,
            @Size(max = 100) String merchant,
            @NotNull @Size(min = 28, max = 28) List<Double> features) {

        @AssertTrue(message = "features must be finite numbers")
        boolean isFeaturesFinite() {
            return features == null || features.stream().allMatch(f -> f != null && Double.isFinite(f));
        }
    }

    public record SimulateRequest(@NotNull @Min(1) @Max(1000) Integer count,
                                  @DecimalMin("0.0") @DecimalMax("1.0") Double fraudRatio) {
    }

    public record SimulationSummary(int requested, int processed, int approved, int humanReview, int declined,
                                    int failed) {
    }

    public record DecisionUpdate(@NotNull @Pattern(regexp = "APPROVE|DECLINE") String decision) {
    }

    public record TransactionResponse(UUID id, UUID customerId, BigDecimal amount, String currency, String merchant,
                                      Transaction.Status status, String decision, String reason, Double probability,
                                      Double uncertainty, String modelVersion, boolean simulated, Instant createdAt,
                                      Instant decidedAt) {
        static TransactionResponse of(Transaction t) {
            return new TransactionResponse(t.getId(), t.getCustomerId(), t.getAmount(), t.getCurrency(), t.getMerchant(),
                    t.getStatus(), t.getDecision(), t.getReason(), t.getProbability(), t.getUncertainty(),
                    t.getModelVersion(), t.isSimulated(), t.getCreatedAt(), t.getDecidedAt());
        }
    }

    private final TransactionService service;
    private final TransactionRepository repository;
    private final Simulator simulator;
    private final int simulatorMax;

    public TransactionController(TransactionService service, TransactionRepository repository, Simulator simulator,
                                 @Value("${riskpulse.simulator.max-count:200}") int simulatorMax) {
        this.service = service;
        this.repository = repository;
        this.simulator = simulator;
        this.simulatorMax = simulatorMax;
    }

    /** A CUSTOMER can only submit for the customer bound to its token (BOLA); staff may submit for anyone. */
    @PostMapping("/api/transactions")
    public ResponseEntity<TransactionResponse> create(@Valid @RequestBody TransactionRequest request, Authentication auth) {
        AuthenticatedUser caller = AuthenticatedUser.from(auth);
        UUID customerId = request.customerId() != null ? request.customerId() : caller.customerId();
        if (customerId == null) {
            throw ApiException.badRequest("customerId is required");
        }
        if (!caller.canAccessCustomer(customerId)) {
            throw ApiException.forbidden();
        }
        Transaction t = service.submit(customerId, request.amount(), request.currency() == null ? "EUR" : request.currency(),
                request.merchant(), request.features(), false, caller);
        return ResponseEntity.status(HttpStatus.CREATED).body(TransactionResponse.of(t));
    }

    @GetMapping("/api/transactions")
    public PageResponse<TransactionResponse> list(@RequestParam(required = false) Transaction.Status status,
                                                  @RequestParam(required = false) UUID customerId,
                                                  @RequestParam(defaultValue = "0") int page,
                                                  @RequestParam(defaultValue = "20") int size,
                                                  Authentication auth) {
        AuthenticatedUser caller = AuthenticatedUser.from(auth);
        UUID scope = customerId;
        if (!caller.isStaff()) {
            if (caller.customerId() == null) {
                throw ApiException.forbidden();
            }
            scope = caller.customerId(); // customers never choose the scope
        }
        PageRequest pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100));
        return PageResponse.of(repository.search(scope, status, pageable), TransactionResponse::of);
    }

    @GetMapping("/api/transactions/{id}")
    public TransactionResponse get(@PathVariable UUID id, Authentication auth) {
        Transaction t = repository.findById(id).orElseThrow(() -> ApiException.notFound("Transaction"));
        if (!AuthenticatedUser.from(auth).canAccessCustomer(t.getCustomerId())) {
            throw ApiException.forbidden();
        }
        return TransactionResponse.of(t);
    }

    /** Admin simulator: replays realistic payloads through the whole decision pipeline (demo and load tests). */
    @PostMapping("/api/transactions/simulate")
    @PreAuthorize("hasRole('ADMIN')")
    public SimulationSummary simulate(@Valid @RequestBody SimulateRequest request, Authentication auth) {
        if (request.count() > simulatorMax) {
            throw ApiException.badRequest("count must be <= " + simulatorMax);
        }
        AuthenticatedUser caller = AuthenticatedUser.from(auth);
        int approved = 0;
        int review = 0;
        int declined = 0;
        int failed = 0;
        for (Simulator.Sample s : simulator.draw(request.count(), request.fraudRatio())) {
            try {
                Transaction t = service.submit(simulator.randomCustomer(), s.amount(), "EUR", "simulator", s.features(),
                        true, caller);
                switch (t.getDecision()) {
                    case "APPROVE" -> approved++;
                    case "DECLINE" -> declined++;
                    default -> review++;
                }
            } catch (RuntimeException e) {
                failed++;
            }
        }
        return new SimulationSummary(request.count(), request.count() - failed, approved, review, declined, failed);
    }

    /** Internal callback from risk-service when an analyst resolves a review (JWT + service key). */
    @PutMapping("/internal/transactions/{id}/decision")
    public TransactionResponse decision(@PathVariable UUID id, @Valid @RequestBody DecisionUpdate update) {
        return TransactionResponse.of(service.applyReviewOutcome(id, update.decision()));
    }
}
