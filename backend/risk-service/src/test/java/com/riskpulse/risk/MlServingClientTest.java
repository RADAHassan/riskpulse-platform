package com.riskpulse.risk;

import static org.assertj.core.api.Assertions.assertThat;

import com.riskpulse.common.client.ServiceClients;
import com.riskpulse.risk.ml.MlResult;
import com.riskpulse.risk.ml.MlServingClient;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.math.BigDecimal;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class MlServingClientTest {

    private FakeServer server;
    private static final List<Double> FEATURES = Collections.nCopies(28, 0.0);

    @BeforeEach
    void start() throws Exception {
        server = new FakeServer("/predict");
        server.response = () -> FakeServer.ml("APPROVE", 0.001, 0.002, "[\"LEGIT\"]", false);
    }

    @AfterEach
    void stop() {
        server.close();
    }

    private MlServingClient client(long timeoutMs, int attempts, int minCalls) {
        return new MlServingClient(new ServiceClients("svc-key"), new SimpleMeterRegistry(), server.url(), timeoutMs,
                attempts, 10, minCalls, 30);
    }

    @Test
    void parsesTheServingContractAndSendsSnakeCasePayload() {
        Optional<MlResult> r = client(1000, 2, 5).predict(UUID.randomUUID(), new BigDecimal("12.50"), FEATURES);
        assertThat(r).isPresent();
        assertThat(r.get().decision()).isEqualTo("APPROVE");
        assertThat(r.get().conformalSet()).containsExactly("LEGIT");
        assertThat(r.get().registryVersion()).isEqualTo("7");
        assertThat(server.bodies.get(0)).contains("\"transaction_id\"").contains("\"amount\":12.5").contains("\"features\"");
    }

    @Test
    void serverErrorsAreRetriedThenGiveUpWithEmptyResult() {
        server.status = 500;
        Optional<MlResult> r = client(1000, 3, 50).predict(UUID.randomUUID(), BigDecimal.TEN, FEATURES);
        assertThat(r).isEmpty();
        assertThat(server.calls.get()).isEqualTo(3);
    }

    @Test
    void clientErrorsAreNotRetried() {
        server.status = 401;
        assertThat(client(1000, 3, 50).predict(UUID.randomUUID(), BigDecimal.TEN, FEATURES)).isEmpty();
        assertThat(server.calls.get()).isEqualTo(1);
    }

    @Test
    void slowResponsesTimeOut() {
        server.delayMs = 800;
        long start = System.nanoTime();
        assertThat(client(150, 1, 50).predict(UUID.randomUUID(), BigDecimal.TEN, FEATURES)).isEmpty();
        assertThat((System.nanoTime() - start) / 1_000_000).isLessThan(700);
    }

    @Test
    void circuitOpensAfterRepeatedFailuresAndStopsCallingTheService() {
        server.status = 503;
        MlServingClient c = client(1000, 1, 5);
        for (int i = 0; i < 6; i++) {
            c.predict(UUID.randomUUID(), BigDecimal.TEN, FEATURES);
        }
        assertThat(c.circuitState()).isEqualTo(CircuitBreaker.State.OPEN);
        int before = server.calls.get();
        assertThat(c.predict(UUID.randomUUID(), BigDecimal.TEN, FEATURES)).isEmpty();
        assertThat(server.calls.get()).isEqualTo(before); // short-circuited: no call reached the service
    }

    @Test
    void unreachableServiceYieldsEmptyResult() {
        server.close();
        assertThat(client(300, 2, 50).predict(UUID.randomUUID(), BigDecimal.TEN, FEATURES)).isEmpty();
    }
}
