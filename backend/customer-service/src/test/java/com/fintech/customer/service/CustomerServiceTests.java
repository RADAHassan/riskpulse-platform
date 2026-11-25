package com.fintech.customer.service;

import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.Customer;
import com.fintech.customer.domain.CustomerStatus;
import com.fintech.customer.dto.CreateCustomerRequest;
import com.fintech.customer.dto.CustomerResponse;
import com.fintech.customer.dto.CustomerStatusRequest;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.mapper.CustomerMapperImpl;
import com.fintech.customer.repository.CustomerRepository;
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
class CustomerServiceTests {

    @Mock CustomerRepository customerRepository;

    CustomerService service;
    final UUID userId = UUID.randomUUID();
    final CreateCustomerRequest request = new CreateCustomerRequest("Amina", "Benali",
            "+212612345678", LocalDate.of(1995, 4, 12), "Tanger");

    @BeforeEach
    void setUp() {
        service = new CustomerService(customerRepository, new CustomerMapperImpl());
    }

    private void assertCode(Throwable t, ErrorCode expected) {
        assertThat(t).isInstanceOfSatisfying(BusinessRuleException.class,
                e -> assertThat(e.getCode()).isEqualTo(expected));
    }

    @Test
    void create_usesUserIdAndEmailFromToken() {
        when(customerRepository.existsById(userId)).thenReturn(false);
        when(customerRepository.existsByEmail("amina@example.com")).thenReturn(false);
        when(customerRepository.saveAndFlush(any(Customer.class))).thenAnswer(i -> i.getArgument(0));

        CustomerResponse r = service.create(userId, "amina@example.com", request);

        assertThat(r.userId()).isEqualTo(userId);
        assertThat(r.email()).isEqualTo("amina@example.com");
        assertThat(r.status()).isEqualTo(CustomerStatus.ACTIVE);
    }

    @Test
    void create_twice_isRejected() {
        when(customerRepository.existsById(userId)).thenReturn(true);

        assertThatThrownBy(() -> service.create(userId, "amina@example.com", request))
                .satisfies(t -> assertCode(t, ErrorCode.PROFILE_ALREADY_EXISTS));
    }

    @Test
    void create_withEmailOfAnotherCustomer_isRejected() {
        when(customerRepository.existsById(userId)).thenReturn(false);
        when(customerRepository.existsByEmail("amina@example.com")).thenReturn(true);

        assertThatThrownBy(() -> service.create(userId, "amina@example.com", request))
                .satisfies(t -> assertCode(t, ErrorCode.EMAIL_ALREADY_USED));
    }

    @Test
    void close_isRefusedWhileAnAccountIsOpen() {
        Customer customer = new Customer(userId, "Amina", "Benali", "amina@example.com",
                "+212612345678", LocalDate.of(1995, 4, 12), "Tanger");
        customer.addAccount(new CheckingAccount("MA0000000000000000000001", "MAD",
                BigDecimal.ZERO, new BigDecimal("500.00")));
        when(customerRepository.findById(userId)).thenReturn(Optional.of(customer));

        assertThatThrownBy(() -> service.changeStatus(userId,
                new CustomerStatusRequest(CustomerStatus.CLOSED, null)))
                .isInstanceOf(BusinessRuleException.class);
    }
}