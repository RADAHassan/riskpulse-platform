package com.fintech.customer.repository;

import com.fintech.customer.domain.Account;
import com.fintech.customer.domain.AccountStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface AccountRepository extends JpaRepository<Account, UUID> {

    boolean existsByAccountNumber(String accountNumber);

    Optional<Account> findByAccountNumber(String accountNumber);

    Page<Account> findByCustomerUserId(UUID customerId, Pageable pageable);

    List<Account> findByCustomerUserIdAndStatus(UUID customerId, AccountStatus status);

    Optional<Account> findByIdAndCustomerUserId(UUID id, UUID customerUserId);

    /** Verrou pessimiste (SELECT ... FOR UPDATE) : deux mouvements sur le meme compte s'executent l'un apres l'autre. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") UUID id);
}