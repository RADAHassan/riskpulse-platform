package com.fintech.customer.domain;

import com.fintech.customer.exception.BusinessRuleException;
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CHECKING")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CheckingAccount extends Account {

    @Column(precision = 19, scale = 4) // nullable en base : la table est partagée avec SavingsAccount
    private BigDecimal overdraftLimit;

    public CheckingAccount(String accountNumber, String currency,
                           BigDecimal initialBalance, BigDecimal overdraftLimit) {
        super(accountNumber, currency, initialBalance);
        if (overdraftLimit == null || overdraftLimit.signum() < 0) {
            throw new BusinessRuleException("Overdraft limit must be >= 0");
        }
        this.overdraftLimit = overdraftLimit;
    }

    @Override
    public boolean canDebit(BigDecimal amount) {
        return isOpenAndPositive(amount)
                && getAvailableBalance().compareTo(amount) >= 0;
    }
    @Override
    /** Solde + découvert autorisé. */
    public BigDecimal getAvailableBalance() {
        return getBalance().add(overdraftLimit);
    }
}
