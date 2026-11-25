package com.fintech.customer.domain;

import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "accounts")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "account_type", discriminatorType = DiscriminatorType.STRING, length = 20)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public abstract class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true, length = 34)
    private String accountNumber;

    @Column(nullable = false, length = 3)
    private String currency;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal balance;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private AccountStatus status;

    @CreationTimestamp
    @Column(nullable = false, updatable = false)
    private Instant openedAt;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected Account(String accountNumber, String currency, BigDecimal initialBalance) {
        if (initialBalance == null || initialBalance.signum() < 0) {
            throw new BusinessRuleException("Initial balance must be >= 0");
        }
        this.accountNumber = accountNumber;
        this.currency = currency;
        this.balance = initialBalance;
        this.status = AccountStatus.OPEN;
    }

    /** Package-private : seul Customer.addAccount() (meme package) peut rattacher un compte. */
    void assignTo(Customer customer) {
        this.customer = customer;
    }

    public void freeze() {
        if (status != AccountStatus.OPEN) {
            throw new BusinessRuleException(ErrorCode.INVALID_STATE_TRANSITION, "Only an OPEN account can be frozen");
        }
        status = AccountStatus.FROZEN;
    }

    public void unfreeze() {
        if (status != AccountStatus.FROZEN) {
            throw new BusinessRuleException(ErrorCode.INVALID_STATE_TRANSITION, "Only a FROZEN account can be unfrozen");
        }
        status = AccountStatus.OPEN;
    }

    public void close() {
        if (status == AccountStatus.CLOSED) {
            throw new BusinessRuleException(ErrorCode.INVALID_STATE_TRANSITION, "Account is already closed");
        }
        if (balance.signum() != 0) {
            throw new BusinessRuleException("Balance must be zero to close the account");
        }
        status = AccountStatus.CLOSED;
    }

    /** Hypothese H6 du contrat : un compte FROZEN accepte les credits, un compte CLOSED refuse tout. */
    public void credit(BigDecimal amount) {
        requirePositive(amount);
        requireNotClosed();
        balance = balance.add(amount);
    }

    public void debit(BigDecimal amount) {
        requirePositive(amount);
        requireNotClosed();
        if (status == AccountStatus.FROZEN) {
            throw new BusinessRuleException(ErrorCode.ACCOUNT_FROZEN, "Account is frozen");
        }
        if (!canDebit(amount)) {
            throw new BusinessRuleException(ErrorCode.INSUFFICIENT_FUNDS, "Insufficient funds");
        }
        balance = balance.subtract(amount);
    }

    /** La regle de debit differe selon le type de compte : c'est le polymorphisme. */
    public abstract boolean canDebit(BigDecimal amount);

    /** Montant maximal debitable : depend du type de compte. */
    public abstract BigDecimal getAvailableBalance();

    protected boolean isOpenAndPositive(BigDecimal amount) {
        return status == AccountStatus.OPEN && amount != null && amount.signum() > 0;
    }

    private void requireNotClosed() {
        if (status == AccountStatus.CLOSED) {
            throw new BusinessRuleException(ErrorCode.ACCOUNT_CLOSED, "Account is closed");
        }
    }

    private void requirePositive(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new BusinessRuleException("Amount must be > 0");
        }
    }
}