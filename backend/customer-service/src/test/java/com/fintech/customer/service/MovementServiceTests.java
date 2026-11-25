package com.fintech.customer.service;

import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.AccountMovement;
import com.fintech.customer.domain.CheckingAccount;
import com.fintech.customer.domain.Customer;
import com.fintech.customer.domain.MovementKind;
import com.fintech.customer.dto.MovementRequest;
import com.fintech.customer.dto.MovementResponse;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.repository.AccountMovementRepository;
import com.fintech.customer.repository.AccountRepository;
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
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MovementServiceTests {

    @Mock AccountRepository accountRepository;
    @Mock AccountMovementRepository movementRepository;

    MovementService service;
    final UUID txId = UUID.randomUUID();
    final UUID accountId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        service = new MovementService(accountRepository, movementRepository);
    }

    private Account accountWith(String balance) {
        Customer customer = new Customer(UUID.randomUUID(), "Amina", "Benali", "a@example.com",
                "+212612345678", LocalDate.of(1995, 4, 12), "Tanger");
        Account account = new CheckingAccount("MA0000000000000000000001", "MAD",
                new BigDecimal(balance), new BigDecimal("0.00"));
        customer.addAccount(account);
        return account;
    }

    private MovementRequest debit(String amount) {
        return new MovementRequest(txId, MovementKind.DEBIT, accountId, null, null, new BigDecimal(amount), "MAD");
    }

    @Test
    void debit_isApplied_andRecorded() {
        Account account = accountWith("100.00");
        when(movementRepository.findById(txId)).thenReturn(Optional.empty());
        when(accountRepository.findByIdForUpdate(accountId)).thenReturn(Optional.of(account));
        when(movementRepository.saveAndFlush(any(AccountMovement.class))).thenAnswer(i -> i.getArgument(0));

        MovementResponse r = service.apply(debit("30.00"));

        assertThat(r.status()).isEqualTo("APPLIED");
        assertThat(r.balanceAfter()).isEqualByComparingTo("70.00");
    }

    @Test
    void replayWithSameContent_doesNotMoveMoneyTwice() {
        Account account = accountWith("100.00");
        when(movementRepository.findById(txId)).thenReturn(Optional.empty());
        when(accountRepository.findByIdForUpdate(accountId)).thenReturn(Optional.of(account));
        when(movementRepository.saveAndFlush(any(AccountMovement.class))).thenAnswer(i -> i.getArgument(0));
        service.apply(debit("30.00"));

        AccountMovement stored = new AccountMovement(txId, MovementKind.DEBIT, fingerprintOf(), new BigDecimal("70.00"));
        when(movementRepository.findById(txId)).thenReturn(Optional.of(stored));

        MovementResponse replayed = service.apply(debit("30.00"));

        assertThat(replayed.status()).isEqualTo("ALREADY_APPLIED");
        assertThat(account.getBalance()).isEqualByComparingTo("70.00"); // une seule fois
    }

    @Test
    void sameKeyWithDifferentContent_isRejected() {
        AccountMovement stored = new AccountMovement(txId, MovementKind.DEBIT, "other-fingerprint", BigDecimal.TEN);
        when(movementRepository.findById(txId)).thenReturn(Optional.of(stored));

        assertThatThrownBy(() -> service.apply(debit("30.00")))
                .isInstanceOfSatisfying(BusinessRuleException.class,
                        e -> assertThat(e.getCode()).isEqualTo(ErrorCode.IDEMPOTENCY_KEY_REUSED));
        verify(accountRepository, never()).findByIdForUpdate(any());
    }

    @Test
    void debitAboveAvailableBalance_isRefused() {
        when(movementRepository.findById(txId)).thenReturn(Optional.empty());
        when(accountRepository.findByIdForUpdate(accountId)).thenReturn(Optional.of(accountWith("100.00")));

        assertThatThrownBy(() -> service.apply(debit("500.00")))
                .isInstanceOfSatisfying(BusinessRuleException.class,
                        e -> assertThat(e.getCode()).isEqualTo(ErrorCode.INSUFFICIENT_FUNDS));
    }

    @Test
    void wrongCurrency_isRefused() {
        when(movementRepository.findById(txId)).thenReturn(Optional.empty());
        when(accountRepository.findByIdForUpdate(accountId)).thenReturn(Optional.of(accountWith("100.00")));
        var request = new MovementRequest(txId, MovementKind.DEBIT, accountId, null, null,
                new BigDecimal("10.00"), "EUR");

        assertThatThrownBy(() -> service.apply(request))
                .isInstanceOfSatisfying(BusinessRuleException.class,
                        e -> assertThat(e.getCode()).isEqualTo(ErrorCode.CURRENCY_MISMATCH));
    }

    @Test
    void transferToTheSameAccount_isRefused() {
        when(movementRepository.findById(txId)).thenReturn(Optional.empty());
        var request = new MovementRequest(txId, MovementKind.TRANSFER, null, accountId, accountId,
                new BigDecimal("10.00"), "MAD");

        assertThatThrownBy(() -> service.apply(request))
                .isInstanceOfSatisfying(BusinessRuleException.class,
                        e -> assertThat(e.getCode()).isEqualTo(ErrorCode.SAME_ACCOUNT_TRANSFER));
    }

    /** Meme calcul que le service, pour fabriquer l'empreinte d'un mouvement deja enregistre. */
    private String fingerprintOf() {
        try {
            String content = String.join("|", "DEBIT", accountId.toString(), "null", "null", "30.00", "MAD");
            byte[] hash = java.security.MessageDigest.getInstance("SHA-256")
                    .digest(content.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(hash);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}