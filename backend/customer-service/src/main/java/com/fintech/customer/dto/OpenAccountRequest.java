package com.fintech.customer.dto;

import com.fintech.customer.domain.AccountType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/** Taux, decouvert et solde minimum sont fixes par la banque : le client ne les envoie jamais. */
public record OpenAccountRequest(
        @NotNull AccountType type,
        @NotBlank @Pattern(regexp = "^(MAD|EUR|USD)$", message = "unsupported currency (MAD, EUR, USD)")
        String currency) {

    public OpenAccountRequest {
        currency = DtoRules.clean(currency);
    }
}