package com.fintech.customer.dto;

import com.fintech.customer.domain.AccountType;
import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.Customer;
import com.fintech.customer.domain.SavingsAccount;
import com.fintech.customer.mapper.AccountMapper;
import com.fintech.customer.mapper.AccountMapperImpl;
import com.fintech.customer.mapper.CustomerMapper;
import com.fintech.customer.mapper.CustomerMapperImpl;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class DtoMappingTests {

    private static Validator validator;
    private final AccountMapper accountMapper = new AccountMapperImpl();
    private final CustomerMapper customerMapper = new CustomerMapperImpl();

    @BeforeAll
    static void initValidator() {
        validator = Validation.buildDefaultValidatorFactory().getValidator();
    }

    @Test
    void checkingAccount_isMappedWithOverdraftOnly() {
        var account = new CheckingAccount("MA0000000000000000000001", "MAD",
                new BigDecimal("100.00"), new BigDecimal("500.00"));

        AccountResponse r = accountMapper.toResponse(account);

        assertThat(r.type()).isEqualTo(AccountType.CHECKING);
        assertThat(r.availableBalance()).isEqualByComparingTo("600.00");
        assertThat(r.overdraftLimit()).isEqualByComparingTo("500.00");
        assertThat(r.interestRate()).isNull();
        assertThat(r.minimumBalance()).isNull();
    }

    @Test
    void savingsAccount_isMappedWithRateAndMinimumOnly() {
        var account = new SavingsAccount("MA0000000000000000000002", "MAD",
                new BigDecimal("1000.00"), new BigDecimal("0.0350"), new BigDecimal("100.00"));

        AccountResponse r = accountMapper.toResponse(account);

        assertThat(r.type()).isEqualTo(AccountType.SAVINGS);
        assertThat(r.availableBalance()).isEqualByComparingTo("900.00");
        assertThat(r.overdraftLimit()).isNull();
        assertThat(r.interestRate()).isEqualByComparingTo("0.0350");
    }

    @Test
    void customer_isMappedWithoutExposingAccountsOrVersion() {
        var id = UUID.randomUUID();
        var customer = new Customer(id, "Amina", "Benali", "amina@example.com",
                "+212612345678", LocalDate.of(1995, 4, 12), "Tanger");

        CustomerResponse r = customerMapper.toResponse(customer);

        assertThat(r.userId()).isEqualTo(id);
        assertThat(r.email()).isEqualTo("amina@example.com");
        assertThat(r.status().name()).isEqualTo("ACTIVE");
    }

    @Test
    void validRequest_hasNoViolation_andIsTrimmed() {
        var request = new CreateCustomerRequest("  Amina ", "Benali", "+212612345678",
                LocalDate.of(1995, 4, 12), "Tanger");

        assertThat(request.firstName()).isEqualTo("Amina");
        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void invalidRequest_reportsAllViolationsTogether() {
        var request = new CreateCustomerRequest("", "Benali", "0612345678",
                LocalDate.now().minusYears(10), "Tanger");

        Set<ConstraintViolation<CreateCustomerRequest>> violations = validator.validate(request);

        assertThat(violations).extracting(v -> v.getPropertyPath().toString())
                .contains("firstName", "phone", "birthDate");
    }
}