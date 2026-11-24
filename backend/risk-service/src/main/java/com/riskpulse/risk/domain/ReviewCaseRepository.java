package com.riskpulse.risk.domain;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReviewCaseRepository extends JpaRepository<ReviewCase, UUID> {

    Page<ReviewCase> findByStatus(ReviewCase.Status status, Pageable pageable);

    Optional<ReviewCase> findByTransactionId(UUID transactionId);

    long countByStatus(ReviewCase.Status status);
}
