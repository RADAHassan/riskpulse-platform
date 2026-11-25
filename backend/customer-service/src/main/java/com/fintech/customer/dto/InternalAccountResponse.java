package com.fintech.customer.dto;

import com.fintech.customer.domain.AccountStatus;
import com.fintech.customer.domain.AccountType;
import com.fintech.customer.domain.CustomerStatus;

import java.math.BigDecimal;
import java.util.UUID;

public record InternalAccountResponse(
        UUID accountId,
        String accountNumber,
        UUID ownerUserId,
        AccountType type,
        String currency,
        AccountStatus status,
        CustomerStatus customerStatus,
        BigDecimal balance,
        BigDecimal availableBalance,
        long accountAgeDays,
        int customerAgeYears) {

    public InternalAccountResponse {
        balance = DtoRules.money(balance);
        availableBalance = DtoRules.money(availableBalance);
    }
}