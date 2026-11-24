package com.riskpulse.risk.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "review_cases")
public class ReviewCase {

    public enum Status { OPEN, APPROVED, REJECTED }

    @Id
    private UUID id;

    @Column(name = "assessment_id", nullable = false)
    private UUID assessmentId;

    @Column(name = "transaction_id", nullable = false, unique = true)
    private UUID transactionId;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    private Double probability;

    private Double uncertainty;

    @Column(name = "model_version", length = 80)
    private String modelVersion;

    @Column(nullable = false, length = 100)
    private String reason;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Status status = Status.OPEN;

    @Column(name = "resolved_by", length = 100)
    private String resolvedBy;

    @Column(name = "resolved_at")
    private Instant resolvedAt;

    @Column(length = 500)
    private String note;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    protected ReviewCase() {
    }

    public ReviewCase(RiskAssessment a) {
        this.id = UUID.randomUUID();
        this.assessmentId = a.getId();
        this.transactionId = a.getTransactionId();
        this.customerId = a.getCustomerId();
        this.amount = a.getAmount();
        this.probability = a.getProbability();
        this.uncertainty = a.getUncertainty();
        this.modelVersion = a.getModelVersion();
        this.reason = a.getReason();
    }

    public void resolve(Status outcome, String by, String note) {
        this.status = outcome;
        this.resolvedBy = by;
        this.resolvedAt = Instant.now();
        this.note = note;
    }

    public UUID getId() { return id; }
    public UUID getAssessmentId() { return assessmentId; }
    public UUID getTransactionId() { return transactionId; }
    public UUID getCustomerId() { return customerId; }
    public BigDecimal getAmount() { return amount; }
    public Double getProbability() { return probability; }
    public Double getUncertainty() { return uncertainty; }
    public String getModelVersion() { return modelVersion; }
    public String getReason() { return reason; }
    public Status getStatus() { return status; }
    public String getResolvedBy() { return resolvedBy; }
    public Instant getResolvedAt() { return resolvedAt; }
    public String getNote() { return note; }
    public Instant getCreatedAt() { return createdAt; }
}
