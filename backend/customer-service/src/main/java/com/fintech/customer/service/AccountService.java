package com.fintech.customer.service;

import com.fintech.customer.config.AccountDefaultsProperties;
import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.AccountStatus;
import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.Customer;
import com.fintech.customer.domain.SavingsAccount;
import com.fintech.customer.dto.AccountResponse;
import com.fintech.customer.dto.AccountStatusRequest;
import com.fintech.customer.dto.OpenAccountRequest;
import com.fintech.customer.dto.PageResponse;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.mapper.AccountMapper;
import com.fintech.customer.repository.AccountRepository;
import com.fintech.customer.repository.CustomerRepository;
import com.fintech.customer.security.Role;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AccountService {

    private static final int MAX_NUMBER_ATTEMPTS = 5;

    private final CustomerRepository customerRepository;
    private final AccountRepository accountRepository;
    private final AccountMapper accountMapper;
    private final AccountNumberGenerator numberGenerator;
    private final AccountDefaultsProperties defaults;

    /** C-07 : le client choisit type et devise ; solde initial 0, le reste vient de la configuration. */
    @Transactional
    public AccountResponse open(UUID userId, OpenAccountRequest request) {
        Customer customer = customerRepository.findById(userId)
                .orElseThrow(() -> new BusinessRuleException(ErrorCode.PROFILE_REQUIRED,
                        "Create your customer profile first"));

        String number = generateUniqueNumber();
        Account account = switch (request.type()) {
            case CHECKING -> new CheckingAccount(number, request.currency(), BigDecimal.ZERO,
                    defaults.checkingOverdraftLimit());
            case SAVINGS -> new SavingsAccount(number, request.currency(), BigDecimal.ZERO,
                    defaults.savingsInterestRate(), defaults.savingsMinimumBalance());
        };

        customer.addAccount(account); // refuse si le client n'est pas ACTIVE
        Account saved = accountRepository.saveAndFlush(account);
        log.info("Account opened userId={} accountId={} type={}", userId, saved.getId(), request.type());
        return accountMapper.toResponse(saved);
    }

    /** C-08. */
    public PageResponse<AccountResponse> listMine(UUID userId, Pageable pageable) {
        return PageResponse.from(accountRepository.findByCustomerUserId(userId, pageable)
                .map(accountMapper::toResponse));
    }

    /** C-09 cote CLIENT : un compte d'autrui renvoie 404, comme s'il n'existait pas. */
    public AccountResponse getForClient(UUID userId, UUID accountId) {
        return accountRepository.findByIdAndCustomerUserId(accountId, userId)
                .map(accountMapper::toResponse)
                .orElseThrow(this::accountNotFound);
    }

    /** C-09 cote ANALYST. */
    public AccountResponse getForStaff(UUID accountId) {
        return accountMapper.toResponse(find(accountId));
    }

    /** C-10 : ANALYST peut seulement geler ; ADMIN peut tout. */
    @Transactional
    public AccountResponse changeStatus(UUID accountId, AccountStatusRequest request, Role role) {
        boolean allowed = role == Role.ADMIN
                || (role == Role.ANALYST && request.status() == AccountStatus.FROZEN);
        if (!allowed) {
            throw new BusinessRuleException(ErrorCode.FORBIDDEN, "Insufficient role for this status change");
        }
        Account account = find(accountId);
        switch (request.status()) {
            case FROZEN -> account.freeze();
            case OPEN -> account.unfreeze();
            case CLOSED -> account.close();
        }
        accountRepository.saveAndFlush(account);
        log.info("Account status changed accountId={} status={} by={}", accountId, request.status(), role);
        return accountMapper.toResponse(account);
    }

    private Account find(UUID accountId) {
        return accountRepository.findById(accountId).orElseThrow(this::accountNotFound);
    }

    private BusinessRuleException accountNotFound() {
        return new BusinessRuleException(ErrorCode.ACCOUNT_NOT_FOUND, "Account not found");
    }

    private String generateUniqueNumber() {
        for (int i = 0; i < MAX_NUMBER_ATTEMPTS; i++) {
            String number = numberGenerator.next();
            if (!accountRepository.existsByAccountNumber(number)) {
                return number;
            }
        }
        throw new IllegalStateException("Could not generate a unique account number");
    }
}