package com.fintech.customer.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record MovementResponse(
        UUID transactionId,
        String status,
        Instant appliedAt,
        BigDecimal balanceAfter) {

    public MovementResponse {
        balanceAfter = DtoRules.money(balanceAfter);
    }
}