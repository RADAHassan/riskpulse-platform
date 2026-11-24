package com.riskpulse.audit;

import com.riskpulse.common.web.PageResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuditController {

    public record AuditEventRequest(
            @NotBlank @Size(max = 100) String actor,
            @NotBlank @Size(max = 20) String actorRole,
            @NotBlank @Size(max = 80) String action,
            @NotBlank @Size(max = 60) String resourceType,
            @NotBlank @Size(max = 80) String resourceId,
            @Size(max = 20) String decision,
            @Size(max = 80) String modelVersion,
            @Size(max = 30) Map<@Size(max = 60) String, Object> details) {
    }

    public record AuditEventResponse(long seq, UUID id, Instant occurredAt, String actor, String actorRole, String action,
                                     String resourceType, String resourceId, String decision, String modelVersion,
                                     String details, String hash) {
        static AuditEventResponse of(AuditRecord r) {
            return new AuditEventResponse(r.getSeq() == null ? 0 : r.getSeq(), r.getId(), r.getOccurredAt(), r.getActor(),
                    r.getActorRole(), r.getAction(), r.getResourceType(), r.getResourceId(), r.getDecision(),
                    r.getModelVersion(), r.getDetails(), r.getHash());
        }
    }

    private final AuditService service;
    private final AuditRepository repository;

    public AuditController(AuditService service, AuditRepository repository) {
        this.service = service;
        this.repository = repository;
    }

    /** Internal write path: guarded by the service key (see CommonSecurityConfig / ServiceKeyFilter). */
    @PostMapping("/internal/audit/events")
    @ResponseStatus(HttpStatus.CREATED)
    public AuditEventResponse append(@Valid @RequestBody AuditEventRequest request) {
        return AuditEventResponse.of(service.append(request));
    }

    @GetMapping("/api/audit/events")
    @PreAuthorize("hasAnyRole('ADMIN','ANALYST')")
    public PageResponse<AuditEventResponse> search(@RequestParam(required = false) String action,
                                                   @RequestParam(required = false) String resourceId,
                                                   @RequestParam(required = false) String actor,
                                                   @RequestParam(defaultValue = "0") int page,
                                                   @RequestParam(defaultValue = "50") int size) {
        PageRequest pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 200));
        return PageResponse.of(repository.search(action, resourceId, actor, pageable), AuditEventResponse::of);
    }

    @GetMapping("/api/audit/events/verify")
    @PreAuthorize("hasRole('ADMIN')")
    public AuditService.Verification verify() {
        return service.verify();
    }
}
