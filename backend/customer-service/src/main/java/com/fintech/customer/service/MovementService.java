package com.fintech.customer.service;

import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.AccountMovement;
import com.fintech.customer.domain.CustomerStatus;
import com.fintech.customer.domain.MovementKind;
import com.fintech.customer.dto.MovementRequest;
import com.fintech.customer.dto.MovementResponse;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.repository.AccountMovementRepository;
import com.fintech.customer.repository.AccountRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Optional;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class MovementService {

    private final AccountRepository accountRepository;
    private final AccountMovementRepository movementRepository;

    /** I-02 : tout ou rien, et sans effet double en cas de rejeu. */
    @Transactional
    public MovementResponse apply(MovementRequest request) {
        String fingerprint = fingerprint(request);

        Optional<AccountMovement> existing = movementRepository.findById(request.transactionId());
        if (existing.isPresent()) {
            return replay(existing.get(), fingerprint);
        }

        BigDecimal balanceAfter = switch (request.kind()) {
            case DEBIT -> debit(single(request), request);
            case CREDIT -> credit(single(request), request);
            case TRANSFER -> transfer(request);
        };

        AccountMovement saved = movementRepository.saveAndFlush(
                new AccountMovement(request.transactionId(), request.kind(), fingerprint, balanceAfter));
        log.info("Movement applied transactionId={} kind={}", request.transactionId(), request.kind());
        return new MovementResponse(saved.getTransactionId(), "APPLIED", saved.getAppliedAt(), balanceAfter);
    }

    private MovementResponse replay(AccountMovement movement, String fingerprint) {
        if (!movement.getFingerprint().equals(fingerprint)) {
            throw new BusinessRuleException(ErrorCode.IDEMPOTENCY_KEY_REUSED,
                    "Same transactionId used with a different content");
        }
        return new MovementResponse(movement.getTransactionId(), "ALREADY_APPLIED",
                movement.getAppliedAt(), movement.getBalanceAfter());
    }

    private BigDecimal debit(UUID accountId, MovementRequest request) {
        Account account = lock(accountId);
        checkOwnerAndCurrency(account, request.currency());
        account.debit(request.amount());
        return account.getBalance();
    }

    private BigDecimal credit(UUID accountId, MovementRequest request) {
        Account account = lock(accountId);
        checkOwnerAndCurrency(account, request.currency());
        account.credit(request.amount());
        return account.getBalance();
    }

    private BigDecimal transfer(MovementRequest request) {
        UUID sourceId = request.sourceAccountId();
        UUID destinationId = request.destinationAccountId();
        if (sourceId == null || destinationId == null) {
            throw new BusinessRuleException(ErrorCode.VALIDATION_ERROR,
                    "sourceAccountId and destinationAccountId are required for a TRANSFER");
        }
        if (sourceId.equals(destinationId)) {
            throw new BusinessRuleException(ErrorCode.SAME_ACCOUNT_TRANSFER, "Source and destination are identical");
        }
        // Ordre de verrouillage fixe : evite l'interblocage de deux virements croises.
        Account source;
        Account destination;
        if (sourceId.compareTo(destinationId) < 0) {
            source = lock(sourceId);
            destination = lock(destinationId);
        } else {
            destination = lock(destinationId);
            source = lock(sourceId);
        }
        checkOwnerAndCurrency(source, request.currency());
        checkOwnerAndCurrency(destination, request.currency());
        source.debit(request.amount());
        destination.credit(request.amount());
        return source.getBalance();
    }

    private Account lock(UUID accountId) {
        return accountRepository.findByIdForUpdate(accountId)
                .orElseThrow(() -> new BusinessRuleException(ErrorCode.ACCOUNT_NOT_FOUND, "Account not found"));
    }

    private void checkOwnerAndCurrency(Account account, String currency) {
        if (account.getCustomer().getStatus() != CustomerStatus.ACTIVE) {
            throw new BusinessRuleException(ErrorCode.CUSTOMER_NOT_ACTIVE, "Customer is not active");
        }
        if (!account.getCurrency().equals(currency)) {
            throw new BusinessRuleException(ErrorCode.CURRENCY_MISMATCH, "Currency differs from the account currency");
        }
    }

    private UUID single(MovementRequest request) {
        if (request.accountId() == null) {
            throw new BusinessRuleException(ErrorCode.VALIDATION_ERROR, "accountId is required for DEBIT and CREDIT");
        }
        return request.accountId();
    }

    /** Resume SHA-256 du contenu : sert a distinguer un rejeu d'une reutilisation abusive de la cle. */
    private String fingerprint(MovementRequest r) {
        String content = String.join("|", String.valueOf(r.kind()), String.valueOf(r.accountId()),
                String.valueOf(r.sourceAccountId()), String.valueOf(r.destinationAccountId()),
                r.amount().setScale(2, java.math.RoundingMode.HALF_EVEN).toPlainString(), r.currency());
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}