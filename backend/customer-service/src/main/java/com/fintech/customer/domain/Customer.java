package com.fintech.customer.domain;

import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "customers")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED) // requis par JPA, interdit au code métier
public class Customer {

    /** Même UUID que User.id dans l'auth-service : fourni de l'extérieur, donc pas de @GeneratedValue. */
    @Id
    @Column(nullable = false, updatable = false)
    private UUID userId;

    @Column(nullable = false, length = 100)
    private String firstName;

    @Column(nullable = false, length = 100)
    private String lastName;

    @Column(nullable = false, unique = true, length = 255)
    private String email;

    @Column(length = 30)
    private String phone;

    @Column(nullable = false)
    private LocalDate birthDate;

    @Column(length = 500)
    private String address;

    @Enumerated(EnumType.STRING) // stocke "ACTIVE" et non 0/1/2 : robuste si l'enum évolue
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @CreationTimestamp
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(nullable = false)
    private Instant updatedAt;

    @Version
    private Long version;

    @Getter(AccessLevel.NONE) // on expose une vue en lecture seule (voir getAccounts)
    @OneToMany(mappedBy = "customer", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<Account> accounts = new ArrayList<>();

    public Customer(UUID userId, String firstName, String lastName, String email,
                    String phone, LocalDate birthDate, String address) {
        this.userId = userId;
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.phone = phone;
        this.birthDate = birthDate;
        this.address = address;
        this.status = CustomerStatus.ACTIVE;
    }

    public List<Account> getAccounts() {
        return Collections.unmodifiableList(accounts);
    }

    public String getFullName() {
        return firstName + " " + lastName;
    }

    public void updateContact(String phone, String address) {
        requireNotClosed();
        this.phone = phone;
        this.address = address;
    }

    public void suspend() {
        if (status != CustomerStatus.ACTIVE) {
            throw new BusinessRuleException(ErrorCode.INVALID_STATE_TRANSITION, "Only an ACTIVE customer can be suspended");
        }
        status = CustomerStatus.SUSPENDED;
    }

    public void reactivate() {
        if (status != CustomerStatus.SUSPENDED) {
            throw new BusinessRuleException(ErrorCode.INVALID_STATE_TRANSITION, "Only a SUSPENDED customer can be reactivated");
        }
        status = CustomerStatus.ACTIVE;
    }

    public void close() {
        requireNotClosed();
        boolean hasOpenAccount = accounts.stream()
                .anyMatch(a -> a.getStatus() != AccountStatus.CLOSED);
        if (hasOpenAccount) {
            throw new BusinessRuleException("All accounts must be closed before closing the customer");
        }
        status = CustomerStatus.CLOSED;
    }

    public void addAccount(Account account) {
        if (status != CustomerStatus.ACTIVE) {
            throw new BusinessRuleException(ErrorCode.CUSTOMER_NOT_ACTIVE, "Accounts can only be added to an ACTIVE customer");
        }
        accounts.add(account);
        account.assignTo(this);
    }

    private void requireNotClosed() {
        if (status == CustomerStatus.CLOSED) {
            throw new BusinessRuleException(ErrorCode.CUSTOMER_NOT_ACTIVE, "Customer is closed");
        }
    }
}
