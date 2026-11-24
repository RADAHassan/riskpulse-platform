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
@Table(name = "risk_assessments")
public class RiskAssessment {

    @Id
    private UUID id;

    @Column(name = "transaction_id", nullable = false, unique = true)
    private UUID transactionId;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    private Double probability;

    private Double uncertainty;

    private Integer prediction;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Decision decision;

    @Column(nullable = false, length = 100)
    private String reason;

    @Column(nullable = false)
    private boolean fallback;

    @Column(name = "model_version", length = 80)
    private String modelVersion;

    @Column(name = "registry_version", length = 20)
    private String registryVersion;

    @Column(name = "conformal_set", length = 20)
    private String conformalSet;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    protected RiskAssessment() {
    }

    public RiskAssessment(UUID transactionId, UUID customerId, BigDecimal amount, Double probability, Double uncertainty,
                          Integer prediction, Decision decision, String reason, boolean fallback, String modelVersion,
                          String registryVersion, String conformalSet) {
        this.id = UUID.randomUUID();
        this.transactionId = transactionId;
        this.customerId = customerId;
        this.amount = amount;
        this.probability = probability;
        this.uncertainty = uncertainty;
        this.prediction = prediction;
        this.decision = decision;
        this.reason = reason;
        this.fallback = fallback;
        this.modelVersion = modelVersion;
        this.registryVersion = registryVersion;
        this.conformalSet = conformalSet;
    }

    public UUID getId() { return id; }
    public UUID getTransactionId() { return transactionId; }
    public UUID getCustomerId() { return customerId; }
    public BigDecimal getAmount() { return amount; }
    public Double getProbability() { return probability; }
    public Double getUncertainty() { return uncertainty; }
    public Integer getPrediction() { return prediction; }
    public Decision getDecision() { return decision; }
    public String getReason() { return reason; }
    public boolean isFallback() { return fallback; }
    public String getModelVersion() { return modelVersion; }
    public String getRegistryVersion() { return registryVersion; }
    public String getConformalSet() { return conformalSet; }
    public Instant getCreatedAt() { return createdAt; }
}
