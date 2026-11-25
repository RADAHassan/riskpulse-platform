package com.fintech.customer.domain;

import com.fintech.customer.exception.BusinessRuleException;
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Entity
@DiscriminatorValue("SAVINGS")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SavingsAccount extends Account {

    /** Taux annuel en fraction : 0.0350 = 3,5 %. */
    @Column(precision = 7, scale = 4)
    private BigDecimal interestRate;

    @Column(precision = 19, scale = 4)
    private BigDecimal minimumBalance;

    public SavingsAccount(String accountNumber, String currency, BigDecimal initialBalance,
                          BigDecimal interestRate, BigDecimal minimumBalance) {
        super(accountNumber, currency, initialBalance);
        if (interestRate == null || interestRate.signum() < 0) {
            throw new BusinessRuleException("Interest rate must be >= 0");
        }
        if (minimumBalance == null || minimumBalance.signum() < 0) {
            throw new BusinessRuleException("Minimum balance must be >= 0");
        }

        this.interestRate = interestRate;
        this.minimumBalance = minimumBalance;
    }

    @Override
    public boolean canDebit(BigDecimal amount) {
        return isOpenAndPositive(amount)
                && getBalance().subtract(amount).compareTo(minimumBalance) >= 0;
    }
    /** Intérêt annuel = solde × taux. */
    public BigDecimal calculateInterest() {
        return getBalance().multiply(interestRate).setScale(4, RoundingMode.HALF_EVEN);
    }
    /** Solde au-dessus du minimum obligatoire (jamais négatif). */
    @Override
    public BigDecimal getAvailableBalance() {
        return getBalance().subtract(minimumBalance).max(BigDecimal.ZERO);
    }
}