package com.riskpulse.transaction;

import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TransactionRepository extends JpaRepository<Transaction, UUID> {

    @Query("""
            select t from Transaction t
            where (:customerId is null or t.customerId = :customerId)
              and (:status is null or t.status = :status)
            order by t.createdAt desc""")
    Page<Transaction> search(@Param("customerId") UUID customerId, @Param("status") Transaction.Status status,
                             Pageable pageable);
}
