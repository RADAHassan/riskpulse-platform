package com.riskpulse.common;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.riskpulse.common.logging.Masking;
import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.security.ServiceKeyFilter;
import com.riskpulse.common.web.ApiException;
import com.riskpulse.common.web.ApiExceptionHandler;
import com.riskpulse.common.web.RequestIdFilter;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

class CommonTests {

    @RestController
    static class Boom {
        @GetMapping("/api-exception")
        String api() {
            throw ApiException.conflict("already exists");
        }

        @GetMapping("/denied")
        String denied() {
            throw new AccessDeniedException("secret internal detail");
        }

        @GetMapping("/crash")
        String crash() {
            throw new IllegalStateException("db password is hunter2");
        }
    }

    private final MockMvc mvc = MockMvcBuilders.standaloneSetup(new Boom())
            .setControllerAdvice(new ApiExceptionHandler()).build();

    @Test
    void businessErrorsAreRfc7807() throws Exception {
        mvc.perform(get("/api-exception"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.detail").value("already exists"))
                .andExpect(jsonPath("$.status").value(409));
    }

    @Test
    void accessDeniedDoesNotLeakDetail() throws Exception {
        mvc.perform(get("/denied"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.detail").value("Access denied"));
    }

    @Test
    void unexpectedErrorsHideInternalsButExposeCorrelationId() throws Exception {
        String body = mvc.perform(get("/crash"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.correlationId").exists())
                .andReturn().getResponse().getContentAsString();
        assertThat(body).doesNotContain("hunter2").doesNotContain("IllegalStateException").doesNotContain("at com.");
        assertThat(mvc.perform(get("/crash")).andReturn().getResponse().getContentType())
                .startsWith(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
    }

    @Test
    void maskingHidesPersonalData() {
        assertThat(Masking.email("alice@example.com")).isEqualTo("a***@example.com");
        assertThat(Masking.email(null)).isEmpty();
        assertThat(Masking.email("nonsense")).isEqualTo("***");
        assertThat(Masking.sanitize("a\nb\r\tc")).isEqualTo("a_b__c");
        assertThat(Masking.id(UUID.fromString("12345678-1234-1234-1234-123456789012"))).startsWith("12345678");
        assertThat(Masking.secret("x")).isEqualTo("[REDACTED]");
    }

    @Test
    void bolaRuleStaffSeesAllCustomerOnlyOwn() {
        UUID mine = UUID.randomUUID();
        AuthenticatedUser customer = new AuthenticatedUser(UUID.randomUUID(), "c", "CUSTOMER", mine);
        AuthenticatedUser analyst = new AuthenticatedUser(UUID.randomUUID(), "a", "ANALYST", null);
        assertThat(customer.canAccessCustomer(mine)).isTrue();
        assertThat(customer.canAccessCustomer(UUID.randomUUID())).isFalse();
        assertThat(customer.canAccessCustomer(null)).isFalse();
        assertThat(analyst.canAccessCustomer(UUID.randomUUID())).isTrue();
        assertThat(analyst.isAdmin()).isFalse();
    }

    @Test
    void userIsParsedFromJwtClaims() {
        UUID uid = UUID.randomUUID();
        UUID cid = UUID.randomUUID();
        Jwt jwt = Jwt.withTokenValue("t").header("alg", "none").subject(uid.toString())
                .claim("roles", List.of("CUSTOMER")).claim("customer_id", cid.toString()).claim("username", "bob")
                .issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60)).build();
        AuthenticatedUser user = AuthenticatedUser.from(jwt);
        assertThat(user.userId()).isEqualTo(uid);
        assertThat(user.customerId()).isEqualTo(cid);
        assertThat(user.role()).isEqualTo("CUSTOMER");
        assertThat(user.isStaff()).isFalse();
    }

    @Test
    void serviceKeyFilterGuardsOnlyInternalPaths() throws Exception {
        ServiceKeyFilter filter = new ServiceKeyFilter("k-0123456789");

        MockHttpServletResponse publicResponse = new MockHttpServletResponse();
        filter.doFilter(new MockHttpServletRequest("GET", "/api/things"), publicResponse, new MockFilterChain());
        assertThat(publicResponse.getStatus()).isEqualTo(200);

        MockHttpServletResponse missing = new MockHttpServletResponse();
        filter.doFilter(new MockHttpServletRequest("POST", "/internal/x"), missing, new MockFilterChain());
        assertThat(missing.getStatus()).isEqualTo(401);

        MockHttpServletRequest wrongKey = new MockHttpServletRequest("POST", "/internal/x");
        wrongKey.addHeader(ServiceKeyFilter.HEADER, "nope");
        MockHttpServletResponse wrong = new MockHttpServletResponse();
        filter.doFilter(wrongKey, wrong, new MockFilterChain());
        assertThat(wrong.getStatus()).isEqualTo(401);

        MockHttpServletRequest good = new MockHttpServletRequest("POST", "/internal/x");
        good.addHeader(ServiceKeyFilter.HEADER, "k-0123456789");
        MockHttpServletResponse ok = new MockHttpServletResponse();
        filter.doFilter(good, ok, new MockFilterChain());
        assertThat(ok.getStatus()).isEqualTo(200);
    }

    @Test
    void serviceKeyFilterFailsClosedWithoutConfiguredKey() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/internal/x");
        request.addHeader(ServiceKeyFilter.HEADER, "");
        MockHttpServletResponse response = new MockHttpServletResponse();
        new ServiceKeyFilter("").doFilter(request, response, new MockFilterChain());
        assertThat(response.getStatus()).isEqualTo(401);
    }

    @Test
    void requestIdIsReusedWhenWellFormedAndReplacedOtherwise() throws Exception {
        RequestIdFilter filter = new RequestIdFilter();
        MockHttpServletRequest ok = new MockHttpServletRequest();
        ok.addHeader(RequestIdFilter.HEADER, "abc12345-def");
        MockHttpServletResponse okResponse = new MockHttpServletResponse();
        filter.doFilter(ok, okResponse, new MockFilterChain());
        assertThat(okResponse.getHeader(RequestIdFilter.HEADER)).isEqualTo("abc12345-def");

        MockHttpServletRequest bad = new MockHttpServletRequest();
        bad.addHeader(RequestIdFilter.HEADER, "x\ninjected");
        MockHttpServletResponse badResponse = new MockHttpServletResponse();
        filter.doFilter(bad, badResponse, new MockFilterChain());
        assertThat(badResponse.getHeader(RequestIdFilter.HEADER)).isNotEqualTo("x\ninjected").hasSize(36);
    }
}
