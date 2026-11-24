package com.riskpulse.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import java.io.IOException;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(properties = {
    "riskpulse.gateway.rate-limit.ip-per-minute=60",
    "riskpulse.gateway.rate-limit.user-per-minute=5",
    "riskpulse.gateway.rate-limit.auth-per-minute=3"
})
@AutoConfigureWebTestClient
class RateLimitTest {

    static FakeUpstream upstream;

    static {
        try {
            upstream = new FakeUpstream();
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void urls(DynamicPropertyRegistry r) {
        r.add("AUTH_SERVICE_URL", upstream::url);
        r.add("CUSTOMER_SERVICE_URL", upstream::url);
    }

    @AfterAll
    static void stop() {
        upstream.close();
    }

    @Autowired
    WebTestClient web;

    @MockitoBean
    ReactiveJwtDecoder decoder;

    @Test
    void perUserLimitReturns429WithRetryAfter() {
        WebTestClient alice = web.mutateWith(mockJwt().jwt(j -> j.subject("alice").claim("roles", List.of("CUSTOMER")))
                .authorities(new SimpleGrantedAuthority("ROLE_CUSTOMER")));
        for (int i = 0; i < 5; i++) {
            alice.get().uri("/api/customers/me").exchange().expectStatus().isOk();
        }
        alice.get().uri("/api/customers/me").exchange().expectStatus().isEqualTo(429)
                .expectHeader().exists("Retry-After")
                .expectBody().jsonPath("$.status").isEqualTo(429);

        // another user is unaffected (per-user buckets)
        web.mutateWith(mockJwt().jwt(j -> j.subject("bob").claim("roles", List.of("CUSTOMER")))
                .authorities(new SimpleGrantedAuthority("ROLE_CUSTOMER")))
                .get().uri("/api/customers/me").exchange().expectStatus().isOk();
    }

    @Test
    void credentialEndpointsHaveATighterPerIpBudget() {
        int ok = 0;
        int limited = 0;
        for (int i = 0; i < 6; i++) {
            int status = web.post().uri("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                    .bodyValue("{\"username\":\"a\",\"password\":\"b\"}").exchange().returnResult(String.class)
                    .getStatus().value();
            if (status == 429) {
                limited++;
            } else {
                ok++;
            }
        }
        assertThat(ok).isEqualTo(3);
        assertThat(limited).isEqualTo(3);
    }
}
