package com.fintech.customer;

import com.fintech.customer.domain.AccountType;
import com.fintech.customer.domain.MovementKind;
import com.fintech.customer.dto.AccountResponse;
import com.fintech.customer.dto.CreateCustomerRequest;
import com.fintech.customer.dto.MovementRequest;
import com.fintech.customer.dto.OpenAccountRequest;
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
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import com.fintech.customer.TestcontainersConfiguration;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {"DB_PASSWORD=test", "INTERNAL_SERVICE_TOKEN=test-token"})
@Import(TestcontainersConfiguration.class)
class ConcurrencyIntegrationTests {

    @Autowired CustomerService customerService;
    @Autowired AccountService accountService;
    @Autowired MovementService movementService;
    @Autowired InternalAccountService internalAccountService;

    /** Disponible = 0 solde + 500 decouvert. 10 debits de 100 lances ensemble : 5 passent, 5 sont refuses. */
    @Test
    void parallelDebits_neverOverdrawBeyondTheLimit() throws Exception {
        UUID userId = UUID.randomUUID();
        customerService.create(userId, userId + "@example.com", new CreateCustomerRequest(
                "Amina", "Benali", "+212612345678", LocalDate.of(1995, 4, 12), "Tanger"));
        AccountResponse account = accountService.open(userId, new OpenAccountRequest(AccountType.CHECKING, "MAD"));

        int attempts = 10;
        ExecutorService pool = Executors.newFixedThreadPool(attempts);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();
        for (int i = 0; i < attempts; i++) {
            results.add(pool.submit(() -> {
                start.await();
                try {
                    movementService.apply(new MovementRequest(UUID.randomUUID(), MovementKind.DEBIT,
                            account.id(), null, null, new BigDecimal("100.00"), "MAD"));
                    return true;
                } catch (Exception e) {
                    return false;
                }
            }));
        }
        start.countDown();
        int succeeded = 0;
        for (Future<Boolean> f : results) {
            if (f.get(30, TimeUnit.SECONDS)) {
                succeeded++;
            }
        }
        pool.shutdown();

        assertThat(succeeded).isEqualTo(5);
        assertThat(internalAccountService.getById(account.id()).balance()).isEqualByComparingTo("-500.00");
    }
}