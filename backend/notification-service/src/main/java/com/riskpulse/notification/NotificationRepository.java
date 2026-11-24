package com.riskpulse.notification;

import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface NotificationRepository extends JpaRepository<Notification, UUID> {

    @Query("""
            select n from Notification n
            where (:customerId is null or n.customerId = :customerId)
              and (:unreadOnly = false or n.read = false)
            order by n.createdAt desc""")
    Page<Notification> find(@Param("customerId") UUID customerId, @Param("unreadOnly") boolean unreadOnly,
                            Pageable pageable);
}
