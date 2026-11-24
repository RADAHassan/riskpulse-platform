package com.riskpulse.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import java.io.IOException;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(properties = {
    "SERVICE_KEY=gateway-test-service-key-0123",
    "CORS_ALLOWED_ORIGINS=https://app.riskpulse.test",
    "riskpulse.gateway.max-request-bytes=2048"
})
@AutoConfigureWebTestClient
class GatewayTest {

    static FakeUpstream upstream;
    static FakeUpstream dead;

    static {
        try {
            upstream = new FakeUpstream();
            dead = new FakeUpstream();
            dead.close(); // port now refuses connections
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void urls(DynamicPropertyRegistry r) {
        r.add("AUTH_SERVICE_URL", upstream::url);
        r.add("CUSTOMER_SERVICE_URL", upstream::url);
        r.add("TRANSACTION_SERVICE_URL", dead::url);
        r.add("RISK_SERVICE_URL", upstream::url);
        r.add("NOTIFICATION_SERVICE_URL", upstream::url);
        r.add("AUDIT_SERVICE_URL", upstream::url);
        r.add("ML_SERVING_URL", upstream::url);
    }

    @AfterAll
    static void stop() {
        upstream.close();
    }

    @Autowired
    WebTestClient web;

    @MockitoBean
    ReactiveJwtDecoder decoder;

    @BeforeEach
    void reset() {
        upstream.calls.set(0);
    }

    private WebTestClient as(String role) {
        return web.mutateWith(mockJwt()
                .jwt(j -> j.subject("user-" + role).claim("roles", List.of(role)))
                .authorities(new SimpleGrantedAuthority("ROLE_" + role)));
    }

    @Test
    void protectedRoutesRequireAJwtAndAnswerWithProblemJson() {
        web.get().uri("/api/customers").exchange().expectStatus().isUnauthorized()
                .expectHeader().contentTypeCompatibleWith("application/problem+json")
                .expectBody().jsonPath("$.status").isEqualTo(401);
        assertThat(upstream.calls.get()).isZero();
    }

    @Test
    void loginIsPublicAndProxied() {
        web.post().uri("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"username\":\"a\",\"password\":\"b\"}").exchange().expectStatus().isOk();
        assertThat(upstream.lastPath.get()).isEqualTo("/api/auth/login");
    }

    @Test
    void jwtAndRequestIdArePropagatedAndClientServiceKeyIsStripped() {
        as("CUSTOMER").get().uri("/api/customers/me")
                .header("X-Service-Key", "forged-by-client")
                .header("X-Request-Id", "req-12345678").exchange().expectStatus().isOk()
                .expectHeader().valueEquals("X-Request-Id", "req-12345678");
        assertThat(upstream.header("X-Service-Key")).isNull();
        assertThat(upstream.header("X-Request-Id")).isEqualTo("req-12345678");
    }

    @Test
    void unsafeRequestIdsAreReplaced() {
        as("CUSTOMER").get().uri("/api/customers/me").header("X-Request-Id", "bad id with spaces").exchange()
                .expectStatus().isOk().expectHeader().value("X-Request-Id", id -> assertThat(id).hasSize(36));
    }

    @Test
    void roleGatesAtTheEdge() {
        as("CUSTOMER").get().uri("/api/audit/events").exchange().expectStatus().isForbidden();
        as("CUSTOMER").get().uri("/api/reviews").exchange().expectStatus().isForbidden();
        as("CUSTOMER").get().uri("/api/ml/model/info").exchange().expectStatus().isForbidden();
        as("ANALYST").get().uri("/api/audit/events").exchange().expectStatus().isOk();
        as("ANALYST").post().uri("/api/transactions/simulate").contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"count\":1}").exchange().expectStatus().isForbidden();
        as("ANALYST").post().uri("/api/auth/users").contentType(MediaType.APPLICATION_JSON).bodyValue("{}")
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void mlServingGetsTheServiceKeyOnlyForAllowedReadPaths() {
        as("ANALYST").get().uri("/api/ml/model/info").exchange().expectStatus().isOk();
        assertThat(upstream.lastPath.get()).isEqualTo("/model/info");
        assertThat(upstream.header("X-Service-Key")).isEqualTo("gateway-test-service-key-0123");

        // /predict is never reachable from outside, even for an admin
        as("ADMIN").post().uri("/api/ml/predict").contentType(MediaType.APPLICATION_JSON).bodyValue("{}")
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void internalPathsAreNeverExposed() {
        as("ADMIN").get().uri("/internal/audit/events").exchange().expectStatus().isNotFound();
        as("ADMIN").post().uri("/internal/risk/assess").contentType(MediaType.APPLICATION_JSON).bodyValue("{}")
                .exchange().expectStatus().isNotFound();
        assertThat(upstream.calls.get()).isZero();
    }

    @Test
    void securityHeadersAreSetAndServerBannerIsRemoved() {
        as("CUSTOMER").get().uri("/api/customers/me").exchange().expectStatus().isOk().expectHeader()
                .valueEquals("X-Content-Type-Options", "nosniff")
                .expectHeader().valueEquals("X-Frame-Options", "DENY")
                .expectHeader().valueEquals("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                .expectHeader().valueEquals("Referrer-Policy", "no-referrer")
                .expectHeader().valueEquals("Cache-Control", "no-store")
                .expectHeader().doesNotExist("Server");
    }

    @Test
    void corsIsRestrictedToConfiguredOrigins() {
        // an absolute base URL is required for the same-origin computation of the CORS processor
        WebTestClient web = this.web.mutate().baseUrl("http://localhost").build();
        web.options().uri("/api/customers").header(HttpHeaders.ORIGIN, "https://app.riskpulse.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization").exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.riskpulse.test");
        web.options().uri("/api/customers").header(HttpHeaders.ORIGIN, "https://evil.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET").exchange().expectStatus().isForbidden();
    }

    @Test
    void oversizedBodiesAreRejectedBeforeAuthentication() {
        web.post().uri("/api/transactions").contentType(MediaType.APPLICATION_JSON)
                .bodyValue("x".repeat(4096)).exchange().expectStatus().isEqualTo(413)
                .expectBody().jsonPath("$.status").isEqualTo(413);
    }

    @Test
    void downstreamOutageIsReportedAsProblemJsonWithoutInternals() {
        as("ADMIN").get().uri("/api/transactions").exchange().expectStatus().isEqualTo(503)
                .expectHeader().contentTypeCompatibleWith("application/problem+json")
                .expectBody(String.class).value(body -> assertThat(body)
                        .doesNotContain("Connection refused").doesNotContain("127.0.0.1").doesNotContain("Exception"));
    }

    @Test
    void openApiDocumentIsPublicAndActuatorHealthIsOpen() {
        web.get().uri("/openapi.yaml").exchange().expectStatus().isOk().expectBody(String.class)
                .value(b -> assertThat(b).contains("RiskPulse public API").contains("/api/transactions"));
        web.get().uri("/actuator/health/liveness").exchange().expectStatus().isOk();
        web.get().uri("/actuator/prometheus").exchange().expectStatus().isOk();
    }

    @Test
    void unknownPathsAreDenied() {
        as("ADMIN").get().uri("/admin/secret").exchange().expectStatus().isForbidden();
    }
}
