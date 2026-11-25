package com.fintech.customer.dto;

import com.fintech.customer.domain.MovementKind;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import java.math.BigDecimal;
import java.util.UUID;

public record MovementRequest(
        @NotNull UUID transactionId,
        @NotNull MovementKind kind,
        UUID accountId,
        UUID sourceAccountId,
        UUID destinationAccountId,
        @NotNull @DecimalMin(value = "0.01") @Digits(integer = 15, fraction = 2) BigDecimal amount,
        @NotBlank @Pattern(regexp = "^(MAD|EUR|USD)$") String currency) {
}