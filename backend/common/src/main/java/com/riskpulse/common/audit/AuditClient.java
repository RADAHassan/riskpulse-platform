package com.riskpulse.common.audit;

import com.riskpulse.common.client.ServiceClients;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Sends audit events to audit-service. A failure never breaks the business flow but is counted
 * ({@code riskpulse_audit_failures_total}) so that monitoring can alert on gaps in the audit trail.
 */
@Component
public class AuditClient {

    private static final Logger LOG = LoggerFactory.getLogger(AuditClient.class);

    private final RestClient client;
    private final Counter failures;
    private final boolean enabled;

    public AuditClient(ServiceClients clients, MeterRegistry registry,
                       @Value("${riskpulse.audit.url:}") String url) {
        this.enabled = url != null && !url.isBlank();
        this.client = enabled ? clients.create(url, Duration.ofMillis(500), Duration.ofSeconds(2)) : null;
        this.failures = Counter.builder("riskpulse.audit.failures")
                .description("Audit events that could not be delivered").register(registry);
    }

    public void record(AuditEvent event) {
        if (!enabled) {
            return;
        }
        try {
            client.post().uri("/internal/audit/events").body(event).retrieve().toBodilessEntity();
        } catch (RuntimeException e) {
            failures.increment();
            LOG.warn("Audit event {} not delivered: {}", event.action(), e.getClass().getSimpleName());
        }
    }
}
