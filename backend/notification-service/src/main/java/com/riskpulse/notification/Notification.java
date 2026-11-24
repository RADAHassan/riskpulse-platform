package com.riskpulse.notification;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "notifications")
public class Notification {

    public enum Severity { INFO, WARNING, CRITICAL }

    @Id
    private UUID id;

    @Column(nullable = false, length = 40)
    private String type;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private Severity severity;

    @Column(nullable = false, length = 200)
    private String subject;

    @Column(nullable = false, length = 1000)
    private String message;

    @Column(name = "transaction_id")
    private UUID transactionId;

    @Column(name = "customer_id")
    private UUID customerId;

    @Column(name = "read", nullable = false)
    private boolean read;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    protected Notification() {
    }

    public Notification(String type, Severity severity, String subject, String message, UUID transactionId,
                        UUID customerId) {
        this.id = UUID.randomUUID();
        this.type = type;
        this.severity = severity;
        this.subject = subject;
        this.message = message;
        this.transactionId = transactionId;
        this.customerId = customerId;
    }

    public void markRead() {
        this.read = true;
    }

    public UUID getId() { return id; }
    public String getType() { return type; }
    public Severity getSeverity() { return severity; }
    public String getSubject() { return subject; }
    public String getMessage() { return message; }
    public UUID getTransactionId() { return transactionId; }
    public UUID getCustomerId() { return customerId; }
    public boolean isRead() { return read; }
    public Instant getCreatedAt() { return createdAt; }
}
