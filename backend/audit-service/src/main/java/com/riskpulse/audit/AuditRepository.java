package com.riskpulse.audit;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AuditRepository extends JpaRepository<AuditRecord, UUID> {

    Optional<AuditRecord> findFirstByOrderBySeqDesc();

    @Query("""
            select e from AuditRecord e
            where (:action is null or e.action = :action)
              and (:resourceId is null or e.resourceId = :resourceId)
              and (:actor is null or e.actor = :actor)
            order by e.seq desc""")
    Page<AuditRecord> search(@Param("action") String action, @Param("resourceId") String resourceId,
                             @Param("actor") String actor, Pageable pageable);

    @Query("select e from AuditRecord e where e.seq > :afterSeq order by e.seq asc")
    java.util.List<AuditRecord> chunkAfter(@Param("afterSeq") long afterSeq, Pageable pageable);
}
