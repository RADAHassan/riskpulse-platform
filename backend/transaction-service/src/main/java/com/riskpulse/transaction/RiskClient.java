package com.riskpulse.transaction;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.riskpulse.common.client.ServiceClients;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.decorators.Decorators;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.retry.RetryRegistry;
import io.micrometer.core.instrument.MeterRegistry;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

/** transaction-service → risk-service (JWT propagated, service key, timeout + retry + circuit breaker). */
@Component
public class RiskClient {

    private static final Logger LOG = LoggerFactory.getLogger(RiskClient.class);

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record RiskAnswer(String decision, String reason, Double probability, Double uncertainty,
                             String modelVersion, boolean fallback) {
    }

    private final RestClient client;
    private final CircuitBreaker circuitBreaker;
    private final Retry retry;

    public RiskClient(ServiceClients clients, MeterRegistry meters,
                      @Value("${riskpulse.risk.url}") String url,
                      @Value("${riskpulse.risk.timeout-ms:4000}") long timeoutMs) {
        this.client = clients.create(url, Duration.ofMillis(500), Duration.ofMillis(timeoutMs));
        CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(CircuitBreakerConfig.custom()
                .slidingWindowSize(20).minimumNumberOfCalls(5).failureRateThreshold(50f)
                .waitDurationInOpenState(Duration.ofSeconds(10)).permittedNumberOfCallsInHalfOpenState(3)
                .automaticTransitionFromOpenToHalfOpenEnabled(true)
                .ignoreExceptions(HttpClientErrorException.class).build());
        this.circuitBreaker = registry.circuitBreaker("riskService");
        // risk-service is idempotent per transactionId, so a retry is safe
        this.retry = RetryRegistry.of(RetryConfig.custom().maxAttempts(2).waitDuration(Duration.ofMillis(150))
                .ignoreExceptions(CallNotPermittedException.class, HttpClientErrorException.class).build()).retry("riskService");
        TaggedCircuitBreakerMetrics.ofCircuitBreakerRegistry(registry).bindTo(meters);
    }

    public Optional<RiskAnswer> assess(UUID transactionId, UUID customerId, BigDecimal amount, List<Double> features) {
        Map<String, Object> body = Map.of("transactionId", transactionId, "customerId", customerId,
                "amount", amount, "features", features);
        try {
            RiskAnswer answer = Decorators.ofSupplier(() ->
                            client.post().uri("/internal/risk/assess").body(body).retrieve().body(RiskAnswer.class))
                    .withCircuitBreaker(circuitBreaker).withRetry(retry).decorate().get();
            return Optional.ofNullable(answer);
        } catch (CallNotPermittedException e) {
            LOG.warn("risk-service circuit is OPEN");
            return Optional.empty();
        } catch (RuntimeException e) {
            LOG.warn("risk-service call failed: {}", e.getClass().getSimpleName());
            return Optional.empty();
        }
    }

    public CircuitBreaker.State circuitState() {
        return circuitBreaker.getState();
    }

    public void resetCircuit() {
        circuitBreaker.reset();
    }
}
