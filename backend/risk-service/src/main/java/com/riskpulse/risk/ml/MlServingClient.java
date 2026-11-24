package com.riskpulse.risk.ml;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.riskpulse.common.client.ServiceClients;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.decorators.Decorators;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import io.github.resilience4j.micrometer.tagged.TaggedRetryMetrics;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.retry.RetryRegistry;
import io.micrometer.core.instrument.MeterRegistry;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

/**
 * Calls ml-serving with timeout (HTTP read timeout), retry and a circuit breaker (Resilience4j).
 * The caller turns an empty result into the fallback decision {@code HUMAN_REVIEW} — never {@code APPROVE}.
 */
@Component
public class MlServingClient {

    private static final Logger LOG = LoggerFactory.getLogger(MlServingClient.class);

    record MlRequest(@JsonProperty("transaction_id") String transactionId, double amount, List<Double> features) {
    }

    private final RestClient client;
    private final CircuitBreaker circuitBreaker;
    private final Retry retry;

    public MlServingClient(ServiceClients clients, MeterRegistry meters,
                           @Value("${riskpulse.ml.url}") String url,
                           @Value("${riskpulse.ml.timeout-ms:1500}") long timeoutMs,
                           @Value("${riskpulse.ml.retry-attempts:2}") int attempts,
                           @Value("${riskpulse.ml.circuit.window:20}") int window,
                           @Value("${riskpulse.ml.circuit.min-calls:5}") int minCalls,
                           @Value("${riskpulse.ml.circuit.open-seconds:10}") int openSeconds) {
        this.client = clients.create(url, Duration.ofMillis(500), Duration.ofMillis(timeoutMs));

        CircuitBreakerRegistry cbRegistry = CircuitBreakerRegistry.of(CircuitBreakerConfig.custom()
                .slidingWindowSize(window)
                .minimumNumberOfCalls(minCalls)
                .failureRateThreshold(50f)
                .waitDurationInOpenState(Duration.ofSeconds(openSeconds))
                .permittedNumberOfCallsInHalfOpenState(3)
                .automaticTransitionFromOpenToHalfOpenEnabled(true)
                .ignoreExceptions(HttpClientErrorException.BadRequest.class)
                .build());
        this.circuitBreaker = cbRegistry.circuitBreaker("mlServing");
        RetryRegistry retryRegistry = RetryRegistry.of(RetryConfig.custom()
                .maxAttempts(Math.max(attempts, 1))
                .waitDuration(Duration.ofMillis(100))
                .ignoreExceptions(CallNotPermittedException.class, HttpClientErrorException.class)
                .build());
        this.retry = retryRegistry.retry("mlServing");
        TaggedCircuitBreakerMetrics.ofCircuitBreakerRegistry(cbRegistry).bindTo(meters);
        TaggedRetryMetrics.ofRetryRegistry(retryRegistry).bindTo(meters);
    }

    /** @return the model answer, or empty when ml-serving cannot be reached in time / the circuit is open. */
    public Optional<MlResult> predict(UUID transactionId, BigDecimal amount, List<Double> features) {
        MlRequest body = new MlRequest(transactionId.toString(), amount.doubleValue(), features);
        Supplier<MlResult> call = () -> client.post().uri("/predict").body(body).retrieve().body(MlResult.class);
        try {
            MlResult result = Decorators.ofSupplier(call).withCircuitBreaker(circuitBreaker).withRetry(retry).decorate().get();
            return Optional.ofNullable(result);
        } catch (CallNotPermittedException e) {
            LOG.warn("ml-serving circuit is OPEN: using the human-review fallback");
            return Optional.empty();
        } catch (RuntimeException e) {
            LOG.warn("ml-serving call failed ({}): using the human-review fallback", e.getClass().getSimpleName());
            return Optional.empty();
        }
    }

    /** Forces the circuit closed again (used by tests and by an operator after an incident). */
    public void resetCircuit() {
        circuitBreaker.reset();
    }

    public CircuitBreaker.State circuitState() {
        return circuitBreaker.getState();
    }
}
