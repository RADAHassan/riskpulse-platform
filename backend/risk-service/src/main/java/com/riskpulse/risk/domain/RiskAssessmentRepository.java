package com.riskpulse.risk.domain;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface RiskAssessmentRepository extends JpaRepository<RiskAssessment, UUID> {

    Optional<RiskAssessment> findByTransactionId(UUID transactionId);

    @Query("select a.decision, count(a) from RiskAssessment a group by a.decision")
    List<Object[]> countByDecision();

    long countByFallbackTrue();
}
