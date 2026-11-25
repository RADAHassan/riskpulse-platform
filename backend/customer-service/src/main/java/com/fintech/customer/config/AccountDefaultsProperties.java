package com.fintech.customer.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;

/** Valeurs fixees par la banque a l'ouverture d'un compte (contrat 4.4). Jamais fournies par le client. */
@ConfigurationProperties(prefix = "bank.account")
public record AccountDefaultsProperties(
        BigDecimal checkingOverdraftLimit,
        BigDecimal savingsInterestRate,
        BigDecimal savingsMinimumBalance) {
}