package com.riskpulse.risk.web;

import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.web.PageResponse;
import com.riskpulse.risk.domain.ReviewCase;
import com.riskpulse.risk.domain.ReviewCaseRepository;
import com.riskpulse.risk.service.RiskService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Human review queue: uncertain or high-risk predictions wait here for an analyst decision. */
@RestController
@PreAuthorize("hasAnyRole('ADMIN','ANALYST')")
public class ReviewController {

    public enum Resolution { APPROVE, REJECT }

    public record ResolveRequest(@NotNull Resolution resolution, @Size(max = 500) String note) {
    }

    public record ReviewResponse(UUID id, UUID transactionId, UUID customerId, BigDecimal amount, Double probability,
                                 Double uncertainty, String modelVersion, String reason, ReviewCase.Status status,
                                 String resolvedBy, Instant resolvedAt, String note, Instant createdAt) {
        static ReviewResponse of(ReviewCase r) {
            return new ReviewResponse(r.getId(), r.getTransactionId(), r.getCustomerId(), r.getAmount(),
                    r.getProbability(), r.getUncertainty(), r.getModelVersion(), r.getReason(), r.getStatus(),
                    r.getResolvedBy(), r.getResolvedAt(), r.getNote(), r.getCreatedAt());
        }
    }

    private final ReviewCaseRepository reviews;
    private final RiskService service;

    public ReviewController(ReviewCaseRepository reviews, RiskService service) {
        this.reviews = reviews;
        this.service = service;
    }

    @GetMapping("/api/reviews")
    public PageResponse<ReviewResponse> list(@RequestParam(defaultValue = "OPEN") ReviewCase.Status status,
                                             @RequestParam(defaultValue = "0") int page,
                                             @RequestParam(defaultValue = "20") int size) {
        PageRequest pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100),
                Sort.by("createdAt").ascending());
        return PageResponse.of(reviews.findByStatus(status, pageable), ReviewResponse::of);
    }

    @PostMapping("/api/reviews/{id}/resolve")
    public ReviewResponse resolve(@PathVariable UUID id, @Valid @RequestBody ResolveRequest request, Authentication auth) {
        AuthenticatedUser user = AuthenticatedUser.from(auth);
        ReviewCase.Status outcome = request.resolution() == Resolution.APPROVE
                ? ReviewCase.Status.APPROVED : ReviewCase.Status.REJECTED;
        return ReviewResponse.of(service.resolve(id, outcome, request.note(), String.valueOf(user.username()), user.role()));
    }
}
