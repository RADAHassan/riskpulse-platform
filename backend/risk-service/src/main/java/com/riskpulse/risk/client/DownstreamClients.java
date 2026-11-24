package com.riskpulse.risk.client;

import com.riskpulse.common.client.ServiceClients;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Best-effort calls to notification-service and transaction-service (JWT of the caller is propagated). */
@Component
public class DownstreamClients {

    private static final Logger LOG = LoggerFactory.getLogger(DownstreamClients.class);

    private final RestClient notification;
    private final RestClient transaction;

    public DownstreamClients(ServiceClients clients,
                             @Value("${riskpulse.notification.url}") String notificationUrl,
                             @Value("${riskpulse.transaction.url}") String transactionUrl) {
        this.notification = clients.create(notificationUrl, Duration.ofMillis(500), Duration.ofSeconds(2));
        this.transaction = clients.create(transactionUrl, Duration.ofMillis(500), Duration.ofSeconds(3));
    }

    public boolean notify(String type, String severity, String subject, String message, UUID transactionId,
                          UUID customerId) {
        Map<String, Object> body = new java.util.HashMap<>();
        body.put("type", type);
        body.put("severity", severity);
        body.put("subject", subject);
        body.put("message", message);
        body.put("transactionId", transactionId);
        body.put("customerId", customerId);
        try {
            notification.post().uri("/internal/notifications").body(body).retrieve().toBodilessEntity();
            return true;
        } catch (RuntimeException e) {
            LOG.warn("Notification not delivered: {}", e.getClass().getSimpleName());
            return false;
        }
    }

    public boolean updateTransactionDecision(UUID transactionId, String decision) {
        try {
            transaction.put().uri("/internal/transactions/{id}/decision", transactionId)
                    .body(Map.of("decision", decision)).retrieve().toBodilessEntity();
            return true;
        } catch (RuntimeException e) {
            LOG.warn("Transaction {} not updated after review: {}", transactionId, e.getClass().getSimpleName());
            return false;
        }
    }
}
