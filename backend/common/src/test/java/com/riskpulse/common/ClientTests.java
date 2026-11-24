package com.riskpulse.common;

import static org.assertj.core.api.Assertions.assertThat;

import com.riskpulse.common.audit.AuditClient;
import com.riskpulse.common.audit.AuditEvent;
import com.riskpulse.common.client.ServiceClients;
import com.riskpulse.common.web.PageResponse;
import com.sun.net.httpserver.HttpServer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

class ClientTests {

    private HttpServer server;
    private final AtomicReference<com.sun.net.httpserver.Headers> seen = new AtomicReference<>();
    private final AtomicReference<String> body = new AtomicReference<>();
    private int status = 201;

    @BeforeEach
    void start() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/audit/events", ex -> {
            seen.set(ex.getRequestHeaders());
            body.set(new String(ex.getRequestBody().readAllBytes()));
            ex.sendResponseHeaders(status, -1);
            ex.close();
        });
        server.start();
    }

    @AfterEach
    void stop() {
        server.stop(0);
        SecurityContextHolder.clearContext();
    }

    private String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @Test
    void outboundCallsCarryServiceKeyAndPropagatedJwt() {
        Jwt jwt = Jwt.withTokenValue("the-user-token").header("alg", "none").subject("u")
                .issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60)).build();
        SecurityContextHolder.getContext().setAuthentication(new JwtAuthenticationToken(jwt));

        AuditClient audit = new AuditClient(new ServiceClients("svc-key-123"), new SimpleMeterRegistry(), url());
        audit.record(AuditEvent.of("alice", "ANALYST", "REVIEW_RESOLVED", "ReviewCase", "42")
                .withDecision("APPROVE", "m1").withDetails(Map.of("note", "ok")));

        assertThat(seen.get().getFirst("X-Service-Key")).isEqualTo("svc-key-123");
        assertThat(seen.get().getFirst("Authorization")).isEqualTo("Bearer the-user-token");
        assertThat(body.get()).contains("REVIEW_RESOLVED").contains("\"modelVersion\":\"m1\"");
    }

    @Test
    void auditFailuresAreCountedAndNeverThrown() {
        status = 500;
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AuditClient audit = new AuditClient(new ServiceClients("k"), registry, url());
        audit.record(AuditEvent.of("a", "ADMIN", "X", "T", "1"));
        assertThat(registry.get("riskpulse.audit.failures").counter().count()).isEqualTo(1.0);
    }

    @Test
    void auditIsDisabledWithoutUrl() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        new AuditClient(new ServiceClients("k"), registry, "").record(AuditEvent.of("a", "ADMIN", "X", "T", "1"));
        assertThat(registry.get("riskpulse.audit.failures").counter().count()).isZero();
    }

    @Test
    void clientBuildsWithTimeouts() {
        assertThat(new ServiceClients("k").create(url(), Duration.ofMillis(100), Duration.ofMillis(100))).isNotNull();
    }

    @Test
    void pageResponseMapsContent() {
        var page = new PageImpl<>(List.of(1, 2, 3), PageRequest.of(0, 3), 7);
        PageResponse<String> response = PageResponse.of(page, i -> "n" + i);
        assertThat(response.content()).containsExactly("n1", "n2", "n3");
        assertThat(response.totalElements()).isEqualTo(7);
        assertThat(response.totalPages()).isEqualTo(3);
    }
}
