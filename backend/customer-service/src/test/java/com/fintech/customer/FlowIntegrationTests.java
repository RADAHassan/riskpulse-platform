package com.fintech.customer;

import com.fintech.customer.domain.AccountType;
import com.fintech.customer.domain.MovementKind;
import com.fintech.customer.dto.AccountResponse;
import com.fintech.customer.dto.CreateCustomerRequest;
import com.fintech.customer.dto.MovementRequest;
import com.fintech.customer.dto.MovementResponse;
import com.fintech.customer.dto.OpenAccountRequest;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.service.AccountService;
import com.fintech.customer.service.CustomerService;
import com.fintech.customer.service.InternalAccountService;
import com.fintech.customer.service.MovementService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;


import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.fintech.customer.TestcontainersConfiguration;
/** Pas de @Transactional : chaque service ouvre sa propre transaction, comme en production. */
@SpringBootTest(properties = {"DB_PASSWORD=test", "INTERNAL_SERVICE_TOKEN=test-token"})
@Import(TestcontainersConfiguration.class)
class FlowIntegrationTests {

    @Autowired CustomerService customerService;
    @Autowired AccountService accountService;
    @Autowired MovementService movementService;
    @Autowired InternalAccountService internalAccountService;

    private AccountResponse newCustomerWithAccount(UUID userId) {
        customerService.create(userId, userId + "@example.com", new CreateCustomerRequest(
                "Amina", "Benali", "+212612345678", LocalDate.of(1995, 4, 12), "Tanger"));
        return accountService.open(userId, new OpenAccountRequest(AccountType.CHECKING, "MAD"));
    }

    private MovementRequest credit(UUID txId, UUID accountId, String amount) {
        return new MovementRequest(txId, MovementKind.CREDIT, accountId, null, null,
                new BigDecimal(amount), "MAD");
    }

    @Test
    void fullFlow_creditThenReplay_movesMoneyOnlyOnce() {
        AccountResponse account = newCustomerWithAccount(UUID.randomUUID());
        UUID txId = UUID.randomUUID();

        MovementResponse first = movementService.apply(credit(txId, account.id(), "200.00"));
        MovementResponse replay = movementService.apply(credit(txId, account.id(), "200.00"));

        assertThat(first.status()).isEqualTo("APPLIED");
        assertThat(replay.status()).isEqualTo("ALREADY_APPLIED");
        assertThat(internalAccountService.getById(account.id()).balance()).isEqualByComparingTo("200.00");
    }

    @Test
    void sameKeyWithDifferentAmount_isRejected() {
        AccountResponse account = newCustomerWithAccount(UUID.randomUUID());
        UUID txId = UUID.randomUUID();
        movementService.apply(credit(txId, account.id(), "50.00"));

        assertThatThrownBy(() -> movementService.apply(credit(txId, account.id(), "60.00")))
                .isInstanceOfSatisfying(BusinessRuleException.class,
                        e -> assertThat(e.getCode()).isEqualTo(ErrorCode.IDEMPOTENCY_KEY_REUSED));
    }

    @Test
    void transfer_isAtomic_andRespectsFunds() {
        AccountResponse a = newCustomerWithAccount(UUID.randomUUID());
        AccountResponse b = newCustomerWithAccount(UUID.randomUUID());
        movementService.apply(credit(UUID.randomUUID(), a.id(), "100.00"));

        movementService.apply(new MovementRequest(UUID.randomUUID(), MovementKind.TRANSFER, null,
                a.id(), b.id(), new BigDecimal("30.00"), "MAD"));

        assertThat(internalAccountService.getById(a.id()).balance()).isEqualByComparingTo("70.00");
        assertThat(internalAccountService.getById(b.id()).balance()).isEqualByComparingTo("30.00");

        // 1000 depasse solde + decouvert (70 + 500) : rien ne doit bouger
        assertThatThrownBy(() -> movementService.apply(new MovementRequest(UUID.randomUUID(),
                MovementKind.TRANSFER, null, a.id(), b.id(), new BigDecimal("1000.00"), "MAD")))
                .isInstanceOf(BusinessRuleException.class);
        assertThat(internalAccountService.getById(a.id()).balance()).isEqualByComparingTo("70.00");
        assertThat(internalAccountService.getById(b.id()).balance()).isEqualByComparingTo("30.00");
    }

    @Test
    void ownerAndAccountAgeAreExposedToTransactionService() {
        AccountResponse account = newCustomerWithAccount(UUID.randomUUID());

        var internal = internalAccountService.getById(account.id());

        assertThat(internal.customerAgeYears()).isGreaterThanOrEqualTo(18);
        assertThat(internal.accountAgeDays()).isZero();
    }
}