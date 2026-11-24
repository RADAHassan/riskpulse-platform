package com.riskpulse.transaction;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "transactions")
public class Transaction {

    public enum Status { PENDING, APPROVED, DECLINED, UNDER_REVIEW, PENDING_RISK }

    @Id
    private UUID id;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    @Column(nullable = false, length = 3)
    private String currency;

    @Column(length = 100)
    private String merchant;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(nullable = false, columnDefinition = "double precision[]")
    private double[] features;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status = Status.PENDING;

    @Column(length = 20)
    private String decision;

    @Column(length = 100)
    private String reason;

    private Double probability;

    private Double uncertainty;

    @Column(name = "model_version", length = 80)
    private String modelVersion;

    @Column(nullable = false)
    private boolean simulated;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    @Column(name = "decided_at")
    private Instant decidedAt;

    protected Transaction() {
    }

    public Transaction(UUID customerId, BigDecimal amount, String currency, String merchant, double[] features,
                       boolean simulated) {
        this.id = UUID.randomUUID();
        this.customerId = customerId;
        this.amount = amount;
        this.currency = currency;
        this.merchant = merchant;
        this.features = features;
        this.simulated = simulated;
    }

    public void applyDecision(String decision, String reason, Double probability, Double uncertainty,
                              String modelVersion, boolean riskUnavailable) {
        this.decision = decision;
        this.reason = reason;
        this.probability = probability;
        this.uncertainty = uncertainty;
        this.modelVersion = modelVersion;
        this.status = switch (decision) {
            case "APPROVE" -> Status.APPROVED;
            case "DECLINE" -> Status.DECLINED;
            default -> riskUnavailable ? Status.PENDING_RISK : Status.UNDER_REVIEW;
        };
        if (this.status == Status.APPROVED || this.status == Status.DECLINED) {
            this.decidedAt = Instant.now();
        }
    }

    /** Final outcome of a human review (APPROVE or DECLINE). */
    public void applyReviewOutcome(String decision) {
        this.decision = decision;
        this.status = "APPROVE".equals(decision) ? Status.APPROVED : Status.DECLINED;
        this.reason = "human_review_" + decision.toLowerCase();
        this.decidedAt = Instant.now();
    }

    public UUID getId() { return id; }
    public UUID getCustomerId() { return customerId; }
    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }
    public String getMerchant() { return merchant; }
    public double[] getFeatures() { return features; }
    public Status getStatus() { return status; }
    public String getDecision() { return decision; }
    public String getReason() { return reason; }
    public Double getProbability() { return probability; }
    public Double getUncertainty() { return uncertainty; }
    public String getModelVersion() { return modelVersion; }
    public boolean isSimulated() { return simulated; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getDecidedAt() { return decidedAt; }
}
