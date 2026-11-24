package com.riskpulse.common.audit;

import java.util.Map;

/** Payload of {@code POST /internal/audit/events}. */
public record AuditEvent(
        String actor,
        String actorRole,
        String action,
        String resourceType,
        String resourceId,
        String decision,
        String modelVersion,
        Map<String, Object> details) {

    public static AuditEvent of(String actor, String actorRole, String action, String resourceType, String resourceId) {
        return new AuditEvent(actor, actorRole, action, resourceType, resourceId, null, null, Map.of());
    }

    public AuditEvent withDecision(String decision, String modelVersion) {
        return new AuditEvent(actor, actorRole, action, resourceType, resourceId, decision, modelVersion, details);
    }

    public AuditEvent withDetails(Map<String, Object> details) {
        return new AuditEvent(actor, actorRole, action, resourceType, resourceId, decision, modelVersion, details);
    }
}
