package com.riskpulse.notification;

import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.web.ApiException;
import com.riskpulse.common.web.PageResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NotificationController {

    public record CreateRequest(
            @NotBlank @Size(max = 40) String type,
            @NotNull Notification.Severity severity,
            @NotBlank @Size(max = 200) String subject,
            @NotBlank @Size(max = 1000) String message,
            UUID transactionId,
            UUID customerId) {
    }

    public record NotificationResponse(UUID id, String type, Notification.Severity severity, String subject,
                                       String message, UUID transactionId, UUID customerId, boolean read,
                                       Instant createdAt) {
        static NotificationResponse of(Notification n) {
            return new NotificationResponse(n.getId(), n.getType(), n.getSeverity(), n.getSubject(), n.getMessage(),
                    n.getTransactionId(), n.getCustomerId(), n.isRead(), n.getCreatedAt());
        }
    }

    private final NotificationRepository repository;

    public NotificationController(NotificationRepository repository) {
        this.repository = repository;
    }

    /** Internal write path (risk-service): JWT + service key. */
    @PostMapping("/internal/notifications")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    public NotificationResponse create(@Valid @RequestBody CreateRequest request) {
        return NotificationResponse.of(repository.save(new Notification(request.type(), request.severity(),
                request.subject(), request.message(), request.transactionId(), request.customerId())));
    }

    /** Staff see every notification; a CUSTOMER only the ones addressed to the customer bound to the token. */
    @GetMapping("/api/notifications")
    public PageResponse<NotificationResponse> list(@RequestParam(defaultValue = "false") boolean unreadOnly,
                                                   @RequestParam(defaultValue = "0") int page,
                                                   @RequestParam(defaultValue = "20") int size,
                                                   Authentication auth) {
        AuthenticatedUser user = AuthenticatedUser.from(auth);
        UUID scope = user.isStaff() ? null : user.customerId();
        if (!user.isStaff() && scope == null) {
            throw ApiException.forbidden();
        }
        PageRequest pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100));
        return PageResponse.of(repository.find(scope, unreadOnly, pageable), NotificationResponse::of);
    }

    @PostMapping("/api/notifications/{id}/read")
    @Transactional
    public NotificationResponse markRead(@PathVariable UUID id, Authentication auth) {
        Notification n = repository.findById(id).orElseThrow(() -> ApiException.notFound("Notification"));
        AuthenticatedUser user = AuthenticatedUser.from(auth);
        if (!user.isStaff() && !(n.getCustomerId() != null && user.canAccessCustomer(n.getCustomerId()))) {
            throw ApiException.forbidden();
        }
        n.markRead();
        return NotificationResponse.of(n);
    }
}
