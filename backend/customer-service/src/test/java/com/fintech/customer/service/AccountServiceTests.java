package com.fintech.customer.service;

import com.fintech.customer.config.AccountDefaultsProperties;
import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.AccountStatus;
import com.fintech.customer.domain.AccountType;
import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.Customer;
import com.fintech.customer.dto.AccountResponse;
import com.fintech.customer.dto.AccountStatusRequest;
import com.fintech.customer.dto.OpenAccountRequest;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.mapper.AccountMapperImpl;
import com.fintech.customer.repository.AccountRepository;
import com.fintech.customer.repository.CustomerRepository;
import com.fintech.customer.security.Role;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AccountServiceTests {

    static final String NUMBER = "MA0000000000000000000001";

    @Mock CustomerRepository customerRepository;
    @Mock AccountRepository accountRepository;
    @Mock AccountNumberGenerator numberGenerator;

    AccountService service;
    final UUID userId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        var defaults = new AccountDefaultsProperties(new BigDecimal("500.00"),
                new BigDecimal("0.0350"), new BigDecimal("100.00"));
        service = new AccountService(customerRepository, accountRepository,
                new AccountMapperImpl(), numberGenerator, defaults);
    }

    private Customer activeCustomer() {
        return new Customer(userId, "Amina", "Benali", "amina@example.com",
                "+212612345678", LocalDate.of(1995, 4, 12), "Tanger");
    }

    private void assertCode(Throwable t, ErrorCode expected) {
        assertThat(t).isInstanceOfSatisfying(BusinessRuleException.class,
                e -> assertThat(e.getCode()).isEqualTo(expected));
    }

    private void stubNumber() {
        when(numberGenerator.next()).thenReturn(NUMBER);
        when(accountRepository.existsByAccountNumber(NUMBER)).thenReturn(false);
    }

    @Test
    void open_checkingAccount_startsAtZeroWithConfiguredOverdraft() {
        when(customerRepository.findById(userId)).thenReturn(Optional.of(activeCustomer()));
        stubNumber();
        when(accountRepository.saveAndFlush(any(Account.class))).thenAnswer(i -> i.getArgument(0));

        AccountResponse r = service.open(userId, new OpenAccountRequest(AccountType.CHECKING, "MAD"));

        assertThat(r.type()).isEqualTo(AccountType.CHECKING);
        assertThat(r.accountNumber()).isEqualTo(NUMBER);
        assertThat(r.balance()).isEqualByComparingTo("0.00");
        assertThat(r.overdraftLimit()).isEqualByComparingTo("500.00");
        assertThat(r.availableBalance()).isEqualByComparingTo("500.00");
    }

    @Test
    void open_savingsAccount_isAllowedWithZeroBalanceBelowMinimum() {
        when(customerRepository.findById(userId)).thenReturn(Optional.of(activeCustomer()));
        stubNumber();
        when(accountRepository.saveAndFlush(any(Account.class))).thenAnswer(i -> i.getArgument(0));

        AccountResponse r = service.open(userId, new OpenAccountRequest(AccountType.SAVINGS, "EUR"));

        assertThat(r.type()).isEqualTo(AccountType.SAVINGS);
        assertThat(r.minimumBalance()).isEqualByComparingTo("100.00");
        assertThat(r.availableBalance()).isEqualByComparingTo("0.00");
    }

    @Test
    void open_withoutProfile_isRefused() {
        when(customerRepository.findById(userId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.open(userId, new OpenAccountRequest(AccountType.CHECKING, "MAD")))
                .satisfies(t -> assertCode(t, ErrorCode.PROFILE_REQUIRED));
    }

    @Test
    void open_forSuspendedCustomer_isRefused() {
        Customer customer = activeCustomer();
        customer.suspend();
        when(customerRepository.findById(userId)).thenReturn(Optional.of(customer));
        stubNumber();

        assertThatThrownBy(() -> service.open(userId, new OpenAccountRequest(AccountType.CHECKING, "MAD")))
                .satisfies(t -> assertCode(t, ErrorCode.CUSTOMER_NOT_ACTIVE));
    }

    @Test
    void getForClient_ofAnotherCustomersAccount_isNotFound() {
        UUID accountId = UUID.randomUUID();
        when(accountRepository.findByIdAndCustomerUserId(accountId, userId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getForClient(userId, accountId))
                .satisfies(t -> assertCode(t, ErrorCode.ACCOUNT_NOT_FOUND));
    }

    @Test
    void changeStatus_analystCanOnlyFreeze() {
        assertThatThrownBy(() -> service.changeStatus(UUID.randomUUID(),
                new AccountStatusRequest(AccountStatus.CLOSED, "fraud suspected"), Role.ANALYST))
                .satisfies(t -> assertCode(t, ErrorCode.FORBIDDEN));
    }

    @Test
    void changeStatus_analystFreezesAnAccount() {
        UUID accountId = UUID.randomUUID();
        var account = new CheckingAccount(NUMBER, "MAD", BigDecimal.ZERO, new BigDecimal("500.00"));
        when(accountRepository.findById(accountId)).thenReturn(Optional.of(account));

        AccountResponse r = service.changeStatus(accountId,
                new AccountStatusRequest(AccountStatus.FROZEN, "suspicious activity"), Role.ANALYST);

        assertThat(r.status()).isEqualTo(AccountStatus.FROZEN);
    }
}