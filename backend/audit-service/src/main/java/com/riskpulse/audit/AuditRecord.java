package com.riskpulse.audit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

/** Immutable row of the audit chain: there is deliberately no setter and no update path. */
@Entity
@Table(name = "audit_events")
public class AuditRecord {

    @Id
    private UUID id;

    @Generated(event = EventType.INSERT)
    @Column(insertable = false, updatable = false)
    private Long seq;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private Instant occurredAt;

    @Column(nullable = false, updatable = false)
    private String actor;

    @Column(name = "actor_role", nullable = false, updatable = false)
    private String actorRole;

    @Column(nullable = false, updatable = false)
    private String action;

    @Column(name = "resource_type", nullable = false, updatable = false)
    private String resourceType;

    @Column(name = "resource_id", nullable = false, updatable = false)
    private String resourceId;

    @Column(updatable = false)
    private String decision;

    @Column(name = "model_version", updatable = false)
    private String modelVersion;

    @Column(nullable = false, updatable = false)
    private String details;

    @Column(name = "prev_hash", nullable = false, updatable = false)
    private String prevHash;

    @Column(nullable = false, updatable = false)
    private String hash;

    protected AuditRecord() {
    }

    public AuditRecord(UUID id, Instant occurredAt, String actor, String actorRole, String action, String resourceType,
                       String resourceId, String decision, String modelVersion, String details, String prevHash,
                       String hash) {
        this.id = id;
        this.occurredAt = occurredAt;
        this.actor = actor;
        this.actorRole = actorRole;
        this.action = action;
        this.resourceType = resourceType;
        this.resourceId = resourceId;
        this.decision = decision;
        this.modelVersion = modelVersion;
        this.details = details;
        this.prevHash = prevHash;
        this.hash = hash;
    }

    public UUID getId() { return id; }
    public Long getSeq() { return seq; }
    public Instant getOccurredAt() { return occurredAt; }
    public String getActor() { return actor; }
    public String getActorRole() { return actorRole; }
    public String getAction() { return action; }
    public String getResourceType() { return resourceType; }
    public String getResourceId() { return resourceId; }
    public String getDecision() { return decision; }
    public String getModelVersion() { return modelVersion; }
    public String getDetails() { return details; }
    public String getPrevHash() { return prevHash; }
    public String getHash() { return hash; }
}
