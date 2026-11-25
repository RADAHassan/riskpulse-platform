package com.fintech.customer.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.springframework.data.domain.Persistable;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * Trace d'un mouvement applique. L'id (transactionId) est fourni de l'exterieur : on implemente Persistable
 * pour que Spring Data fasse un INSERT (et non un SELECT puis INSERT).
 */
@Entity
@Table(name = "account_movements")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AccountMovement implements Persistable<UUID> {

    @Id
    @Column(name = "transaction_id", nullable = false, updatable = false)
    private UUID transactionId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private MovementKind kind;

    @Column(nullable = false, length = 64)
    private String fingerprint;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal balanceAfter;

    @CreationTimestamp
    @Column(nullable = false, updatable = false)
    private Instant appliedAt;

    public AccountMovement(UUID transactionId, MovementKind kind, String fingerprint, BigDecimal balanceAfter) {
        this.transactionId = transactionId;
        this.kind = kind;
        this.fingerprint = fingerprint;
        this.status = "APPLIED";
        this.balanceAfter = balanceAfter;
    }

    @Override
    public UUID getId() {
        return transactionId;
    }

    @Override
    public boolean isNew() {
        return appliedAt == null;
    }
}