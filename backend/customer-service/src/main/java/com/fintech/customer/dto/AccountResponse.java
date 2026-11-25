package com.fintech.customer.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fintech.customer.domain.AccountStatus;
import com.fintech.customer.domain.AccountType;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** Les champs nuls ne sont pas envoyes (contrat 4.1) : un compte courant n'a pas de interestRate. */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record AccountResponse(
        UUID id,
        String accountNumber,
        AccountType type,
        String currency,
        BigDecimal balance,
        BigDecimal availableBalance,
        AccountStatus status,
        Instant openedAt,
        BigDecimal overdraftLimit,
        BigDecimal interestRate,
        BigDecimal minimumBalance) {
    public AccountResponse {
        balance = DtoRules.money(balance);
        availableBalance = DtoRules.money(availableBalance);
        overdraftLimit = DtoRules.money(overdraftLimit);
        minimumBalance = DtoRules.money(minimumBalance);
    }
}