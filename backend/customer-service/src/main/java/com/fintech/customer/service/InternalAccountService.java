package com.fintech.customer.service;

import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.AccountType;
import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.Customer;
import com.fintech.customer.dto.InternalAccountResponse;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.repository.AccountRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class InternalAccountService {

    private final AccountRepository accountRepository;

    /** I-01 par identifiant. */
    public InternalAccountResponse getById(UUID accountId) {
        return toResponse(accountRepository.findById(accountId).orElseThrow(this::notFound));
    }

    /** I-01 par numero de compte (destinataire d'un virement). */
    public InternalAccountResponse getByNumber(String accountNumber) {
        return toResponse(accountRepository.findByAccountNumber(accountNumber).orElseThrow(this::notFound));
    }

    private InternalAccountResponse toResponse(Account account) {
        Customer owner = account.getCustomer();
        AccountType type = account instanceof CheckingAccount ? AccountType.CHECKING : AccountType.SAVINGS;
        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        long ageDays = ChronoUnit.DAYS.between(account.getOpenedAt().atZone(ZoneOffset.UTC).toLocalDate(), today);
        int customerAge = (int) ChronoUnit.YEARS.between(owner.getBirthDate(), today);
        return new InternalAccountResponse(account.getId(), account.getAccountNumber(), owner.getUserId(),
                type, account.getCurrency(), account.getStatus(), owner.getStatus(),
                account.getBalance(), account.getAvailableBalance(), ageDays, customerAge);
    }

    private BusinessRuleException notFound() {
        return new BusinessRuleException(ErrorCode.ACCOUNT_NOT_FOUND, "Account not found");
    }
}